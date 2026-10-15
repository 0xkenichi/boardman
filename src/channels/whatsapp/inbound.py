"""Inbound pipeline shared by the webhook and the fake adapter.

dedupe (``channel_inbound``, keyed by wamid) → claim → media copy → resolve
the sender → engine → render → validate limits → send.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, Protocol

from gaming.src.channels import config
from gaming.src.channels.core import store
from gaming.src.channels.core.engine import Engine, default_engine
from gaming.src.channels.core.events import Inbound
from gaming.src.channels.core.identity.service import resolve
from gaming.src.channels.whatsapp import render

logger = logging.getLogger(__name__)


class Sender(Protocol):
    def send(self, to: str, message: dict[str, Any]) -> str: ...


def max_age_sec() -> int:
    # Meta retries undelivered webhooks for days [?]; anything older than this
    # is dropped rather than acted on (a stale "yes" must not move money).
    return config.int_env("CHANNELS_WA_MAX_AGE_SEC", 3 * 24 * 3600)


def enqueue(ev: Inbound, *, now_ms: Optional[int] = None) -> bool:
    """Record ``ev``; False if this wamid was seen before (a retry or a replay)."""
    now = now_ms if now_ms is not None else store.now_ms()
    if ev.timestamp and (now // 1000) - ev.timestamp > max_age_sec():
        logger.info("[whatsapp] dropped stale message (age > %ss)", max_age_sec())
        return False
    with store.db().transaction() as tx:
        tx.lock_key("channel_inbound", "whatsapp", ev.message_id)
        seen = tx.scalar(
            "SELECT status FROM channel_inbound WHERE channel = ? AND message_id = ?",
            ("whatsapp", ev.message_id),
        )
        if seen is not None:
            return False
        tx.execute(
            "INSERT INTO channel_inbound (channel, message_id, external_id, status, payload, "
            "received_at_ms, updated_at_ms) VALUES (?, ?, ?, 'queued', NULL, ?, ?)",
            ("whatsapp", ev.message_id, ev.external_id, now, now),
        )
    return True


def _set(message_id: str, status: str, *, only_if: Optional[str] = None) -> bool:
    with store.db().transaction() as tx:
        sql = "UPDATE channel_inbound SET status = ?, updated_at_ms = ? WHERE channel = 'whatsapp' AND message_id = ?"
        params: list[Any] = [status, store.now_ms(), message_id]
        if only_if:
            sql += " AND status = ?"
            params.append(only_if)
        return tx.rowcount(sql, params) == 1


def claim(message_id: str) -> bool:
    return _set(message_id, "processing", only_if="queued")


async def handle_event(ev: Inbound, sender: Sender, *, engine: Optional[Engine] = None,
                       media_client: Any = None) -> list[dict[str, Any]]:
    """Run one already-deduplicated event; returns the messages sent."""
    engine = engine or default_engine()
    if ev.kind == "media" and ev.media is not None and media_client is not None:
        from gaming.src.channels.whatsapp.media import MediaRejected, copy_to_storage

        try:
            ref, mime, digest = await asyncio.to_thread(copy_to_storage, media_client, ev.media.ref)
            ev.media.ref, ev.media.mime, ev.media.sha256 = ref, mime, digest
        except MediaRejected as exc:
            logger.info("[whatsapp] media rejected: %s", exc)
            ev.kind = "unsupported"
        except Exception:
            logger.warning("[whatsapp] media copy failed", exc_info=True)
            ev.kind = "unsupported"
    principal = await asyncio.to_thread(
        resolve, "whatsapp", ev.external_id, phone=ev.phone, address=ev.address,
        handle=ev.profile_name or None, inbound=True,
    )
    outs = await engine.handle(ev, principal)
    sent = []
    for out in outs:
        wamid = None
        for msg in render.render(out):
            render.validate(msg)
            wamid = await asyncio.to_thread(sender.send, ev.address or ev.external_id, msg)
            sent.append(msg)
        bind = getattr(out, "bind", "")
        if bind and wamid:
            from gaming.src.channels.core import approvals

            await asyncio.to_thread(approvals.bind_message, bind, str(wamid))
    return sent


def process(events: list[Inbound], sender: Sender, *, media_client: Any = None,
            engine: Optional[Engine] = None) -> None:
    """Background worker body (sync: FastAPI runs it in the threadpool)."""
    for ev in events:
        if not claim(ev.message_id):
            continue
        started = time.monotonic()
        try:
            asyncio.run(handle_event(ev, sender, engine=engine, media_client=media_client))
            _set(ev.message_id, "done")
        except Exception:
            logger.exception("[whatsapp] processing failed")
            _set(ev.message_id, "failed")
        finally:
            logger.debug("[whatsapp] handled in %.2fs", time.monotonic() - started)
