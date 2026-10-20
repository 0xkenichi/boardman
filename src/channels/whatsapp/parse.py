"""Cloud API webhook payload → ``Inbound`` events and delivery statuses.

Shape (``object: whatsapp_business_account``):
``entry[].changes[].value`` with ``metadata.phone_number_id``,
``contacts[].{wa_id, profile.name}``, ``messages[]`` and ``statuses[]``.

Message types handled: ``text``; ``interactive`` (``button_reply`` /
``list_reply``: the id we sent); ``button`` (a template quick reply: its
``payload``); ``image`` / ``document`` (a media id, downloaded later);
``location``. Anything else becomes ``unsupported``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from gaming.src.channels.core.events import Inbound, Media


@dataclass
class Status:
    message_id: str
    status: str  # sent | delivered | read | failed
    recipient_id: str = ""
    error: Optional[str] = None


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def parse(payload: dict, *, phone_number_id: str = "") -> tuple[list[Inbound], list[Status]]:
    """``phone_number_id``: when set, changes addressed to any other business
    number (another number on the same Meta app, whose deliveries are signed
    with the same app secret) are ignored instead of being answered from ours."""
    events: list[Inbound] = []
    statuses: list[Status] = []
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return events, statuses
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            if not isinstance(value, dict):
                continue
            if phone_number_id:
                got = str((value.get("metadata") or {}).get("phone_number_id") or "")
                if got != phone_number_id:
                    continue
            names = {
                str(c.get("wa_id")): ((c.get("profile") or {}).get("name") or "")
                for c in value.get("contacts") or []
                if isinstance(c, dict)
            }
            for m in value.get("messages") or []:
                ev = _message(m, names)
                if ev is not None:
                    events.append(ev)
            for s in value.get("statuses") or []:
                errs = s.get("errors") or []
                err = None
                if errs:
                    e = errs[0] or {}
                    err = f"{e.get('code')}: {e.get('title') or e.get('message') or ''}".strip()
                statuses.append(Status(str(s.get("id") or ""), str(s.get("status") or ""),
                                       str(s.get("recipient_id") or ""), err))
    return events, statuses


def _message(m: dict, names: dict[str, str]) -> Optional[Inbound]:
    if not isinstance(m, dict) or not m.get("from") or not m.get("id"):
        return None
    sender = str(m["from"])
    ev = Inbound(
        channel="whatsapp",
        external_id=sender,
        kind="unsupported",
        message_id=str(m["id"]),
        phone=sender,  # wa_id is the phone today; BSUIDs may replace it [?]
        address=sender,
        profile_name=names.get(sender, ""),
        context_id=str((m.get("context") or {}).get("id") or ""),
        timestamp=_int(m.get("timestamp")),
    )
    t = m.get("type")
    if t == "text":
        ev.kind, ev.text = "text", str((m.get("text") or {}).get("body") or "")
    elif t == "interactive":
        it = m.get("interactive") or {}
        reply = it.get("button_reply") or it.get("list_reply") or {}
        if reply.get("id"):
            ev.kind, ev.button_id = "button", str(reply["id"])
            ev.text = str(reply.get("title") or "")
    elif t == "button":
        b = m.get("button") or {}
        if b.get("payload"):
            ev.kind, ev.button_id = "button", str(b["payload"])
            ev.text = str(b.get("text") or "")
        elif b.get("text"):
            ev.kind, ev.text = "text", str(b["text"])
    elif t in ("image", "document"):
        body = m.get(t) or {}
        if body.get("id"):
            ev.kind = "media"
            ev.media = Media(
                kind=t,
                ref=str(body["id"]),
                mime=str(body.get("mime_type") or ""),
                sha256=str(body.get("sha256") or ""),
                caption=str(body.get("caption") or ""),
            )
    elif t == "location":
        ev.kind = "location"
    return ev
