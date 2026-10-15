"""Persistent sliding-window rate limits shared by every process.

``safety.check_rate`` is in memory per process; the webhook, the bot and the
API are separate processes, so anything a stranger can hammer from a chat
(link-code redemption, withdraw-link issuing, PIN attempts) is counted here.
"""
from __future__ import annotations

from typing import Optional

from gaming.src.channels.core import store


def hit(bucket: str, *, limit: int, window_sec: int, now_ms: Optional[int] = None) -> bool:
    """Record one event in ``bucket``; False (and nothing recorded) if over ``limit``."""
    now = now_ms if now_ms is not None else store.now_ms()
    since = now - window_sec * 1000
    with store.db().transaction() as tx:
        tx.lock_key("channel_rate", bucket)
        tx.execute("DELETE FROM channel_rate_events WHERE bucket = ? AND at_ms < ?", (bucket, since))
        n = int(tx.scalar("SELECT COUNT(*) FROM channel_rate_events WHERE bucket = ?", (bucket,)) or 0)
        if n >= limit:
            return False
        tx.execute("INSERT INTO channel_rate_events (bucket, at_ms) VALUES (?, ?)", (bucket, now))
    return True


def count(bucket: str, *, window_sec: int, now_ms: Optional[int] = None) -> int:
    now = now_ms if now_ms is not None else store.now_ms()
    with store.db().transaction(readonly=True) as tx:
        return int(
            tx.scalar(
                "SELECT COUNT(*) FROM channel_rate_events WHERE bucket = ? AND at_ms >= ?",
                (bucket, now - window_sec * 1000),
            )
            or 0
        )
