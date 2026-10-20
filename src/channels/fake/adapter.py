"""A fake chat app that drives the real engine and renderers.

``FakeChannel("wa")`` runs every event through the WhatsApp pipeline (dedupe,
resolve, engine, WhatsApp renderer) and validates each outbound message
against WhatsApp's limits: 3 reply buttons, 10 list rows, one CTA URL, title
lengths, no HTML. ``FakeChannel("tg")`` does the same with the Telegram
renderer (64-byte callback data). Tests "type" text and "tap" only buttons
that were actually offered, the way a user can.
"""
from __future__ import annotations

import itertools
from typing import Any, Optional

from gaming.src.channels.core.engine import Engine
from gaming.src.channels.core.events import Inbound, Media
from gaming.src.channels.core.identity.repo import Identity
from gaming.src.channels.core.messages import Out

_seq = itertools.count(1)


class NotOffered(AssertionError):
    pass


class _Recorder:
    def __init__(self, fake: "FakeChannel") -> None:
        self.fake = fake

    def send(self, to: str, message: dict[str, Any]) -> str:
        from gaming.src.channels.whatsapp import render as wa

        wa.validate(message)
        wamid = f"wamid.FAKE{next(_seq)}"
        self.fake.inbox.setdefault(to, []).append(message)
        self.fake.wamids.setdefault(to, []).append(wamid)
        return wamid


class FakeMedia:
    """Stands in for the Graph media endpoints."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, str]] = {}

    def add(self, media_id: str, data: bytes, mime: str = "image/png") -> None:
        self.blobs[media_id] = (data, mime)

    def media_info(self, media_id: str) -> dict:
        import hashlib

        data, mime = self.blobs[media_id]
        return {"url": f"https://lookaside.fbsbx.com/media/{media_id}", "mime_type": mime,
                "sha256": hashlib.sha256(data).hexdigest(), "file_size": len(data)}

    def download(self, url: str, *, max_bytes: int) -> bytes:
        data, _ = self.blobs[url.rsplit("/", 1)[-1]]
        return data


class FakeChannel:
    def __init__(self, profile: str = "wa", *, engine: Optional[Engine] = None) -> None:
        if profile not in ("wa", "tg"):
            raise ValueError("profile is 'wa' or 'tg'")
        self.profile = profile
        self.channel = "whatsapp" if profile == "wa" else "telegram"
        self.engine = engine or Engine(notifier=_NullNotifier())
        self.inbox: dict[str, list[dict[str, Any]]] = {}
        self.wamids: dict[str, list[str]] = {}  # parallel to inbox (WhatsApp)
        self.media = FakeMedia()

    # -- user actions --

    async def text(self, user: str, body: str, *, name: str = "") -> list[dict[str, Any]]:
        return await self._send(Inbound(self.channel, user, "text", text=body, profile_name=name))

    async def tap(self, user: str, label_or_id: str) -> list[dict[str, Any]]:
        """Tap a button of the latest message offering any, replying to it
        (WhatsApp sets ``context.id`` to that message's wamid)."""
        idx, offered = self._offering(user)
        match = [i for i, label in offered if label_or_id in (i, label)]
        if not match:
            raise NotOffered(f"{label_or_id!r} not offered; offered: {[l for _, l in offered]}")
        ctx = self.wamid_at(user, idx)
        return await self._send(Inbound(self.channel, user, "button", button_id=match[0], context_id=ctx))

    async def tap_id(self, user: str, button_id: str, *, context_id: str = "") -> list[dict[str, Any]]:
        """Tap a raw id (a stale or forged button); no offer check."""
        return await self._send(Inbound(self.channel, user, "button", button_id=button_id,
                                        context_id=context_id))

    def wamid_at(self, user: str, idx: int) -> str:
        ids_ = self.wamids.get(user) or []
        return ids_[idx] if 0 <= idx < len(ids_) else ""

    def last_wamid(self, user: str) -> str:
        ids_ = self.wamids.get(user) or []
        return ids_[-1] if ids_ else ""

    async def image(self, user: str, data: bytes, mime: str = "image/png",
                    caption: str = "") -> list[dict[str, Any]]:
        mid = f"media{next(_seq)}"
        self.media.add(mid, data, mime)
        return await self._send(Inbound(self.channel, user, "media",
                                        media=Media("image", mid, mime, caption=caption)))

    # -- inspection --

    def messages(self, user: str) -> list[dict[str, Any]]:
        return list(self.inbox.get(user, []))

    def last_text(self, user: str) -> str:
        return text_of(self.messages(user)[-1])

    def offered(self, user: str) -> list[tuple[str, str]]:
        """(id, label) of the options in the latest message that had any."""
        return self._offering(user)[1]

    def _offering(self, user: str) -> tuple[int, list[tuple[str, str]]]:
        msgs = self.messages(user)
        for i in range(len(msgs) - 1, -1, -1):
            opts = options_of(msgs[i])
            if opts:
                return i, opts
        return -1, []

    def links(self, user: str) -> list[str]:
        return [u for m in self.messages(user) for u in urls_of(m)]

    def all_text(self, user: str) -> str:
        return "\n".join(text_of(m) for m in self.messages(user))

    # -- plumbing --

    async def _send(self, ev: Inbound) -> list[dict[str, Any]]:
        ev.message_id = ev.message_id or f"wamid.IN{next(_seq)}"
        before = len(self.inbox.get(ev.external_id, []))
        if self.profile == "wa":
            from gaming.src.channels.whatsapp import inbound

            ev.phone = ev.external_id
            ev.address = ev.external_id
            assert inbound.enqueue(ev) and inbound.claim(ev.message_id)
            await inbound.handle_event(ev, _Recorder(self), engine=self.engine, media_client=self.media)
        else:
            await self._send_tg(ev)
        return self.inbox.get(ev.external_id, [])[before:]

    async def _send_tg(self, ev: Inbound) -> None:
        import asyncio

        from gaming.src.channels.core.identity.service import resolve
        from gaming.src.channels.telegram import render as tg

        ev.address = ev.external_id
        principal = await asyncio.to_thread(resolve, "telegram", ev.external_id, address=ev.address)
        outs = await self.engine.handle(ev, principal)
        for msg in tg.render_dicts(outs):
            tg.validate(msg)
            self.inbox.setdefault(ev.external_id, []).append(msg)


class _NullNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Any, dict]] = []

    async def notify(self, profile_id: str, notice: Any, **kw: Any):
        self.sent.append((profile_id, notice, kw))
        return []


class RecordingDeliverer:
    """A deliverer for ``NotificationService`` that records instead of sending."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.session: list[tuple[str, list[Out]]] = []
        self.templates: list[tuple[str, dict]] = []

    async def send_session(self, ident: Identity, outs: list[Out]) -> Optional[str]:
        if self.channel == "whatsapp":
            from gaming.src.channels.whatsapp import render as wa

            for m in wa.render_all(outs):
                wa.validate(m)
        self.session.append((ident.external_id, outs))
        return f"wamid.N{next(_seq)}"

    async def send_template(self, ident: Identity, notice: Any):
        from gaming.src.channels.whatsapp import templates

        tpl = templates.for_kind(notice.kind)
        if tpl is None:
            return None, None
        msg = templates.message(tpl, notice.params, notice.payloads(len(tpl.buttons)))
        self.templates.append((ident.external_id, msg))
        return tpl.name, f"wamid.T{next(_seq)}"


# ── message inspection helpers (WhatsApp payloads or Telegram dicts) ─────────


def text_of(msg: dict[str, Any]) -> str:
    if "buttons" in msg and "text" in msg and isinstance(msg["text"], str):
        return msg["text"]
    if msg.get("type") == "text":
        return msg["text"]["body"]
    if msg.get("type") == "interactive":
        return msg["interactive"]["body"]["text"]
    return ""


def options_of(msg: dict[str, Any]) -> list[tuple[str, str]]:
    if "buttons" in msg and isinstance(msg.get("text"), str):
        return [(b["callback"], b["label"]) for b in msg["buttons"] if "callback" in b]
    if msg.get("type") != "interactive":
        return []
    it = msg["interactive"]
    if it["type"] == "button":
        return [(b["reply"]["id"], b["reply"]["title"]) for b in it["action"]["buttons"]]
    if it["type"] == "list":
        return [(r["id"], r["title"]) for s in it["action"]["sections"] for r in s["rows"]]
    return []


def urls_of(msg: dict[str, Any]) -> list[str]:
    if "buttons" in msg and isinstance(msg.get("text"), str):
        return [b["url"] for b in msg["buttons"] if "url" in b]
    if msg.get("type") == "interactive" and msg["interactive"]["type"] == "cta_url":
        return [msg["interactive"]["action"]["parameters"]["url"]]
    return []
