"""Per-user conversation state, persisted (CHANNELS_DESIGN §3.2).

One row per ``(channel, external_id)``: the active flow, its step, a JSON
``data`` bag and a ``version`` for optimistic concurrency. A second webhook
worker (or a restart) continues the same conversation; two workers racing on
one user cannot both win: ``save`` only writes when the version it read is
still current.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from gaming.src.channels.core import store

logger = logging.getLogger(__name__)

DEFAULT_TTL_MS = 30 * 60 * 1000  # a wizard left alone for 30 min starts over


@dataclass
class ConversationState:
    channel: str
    external_id: str
    flow: Optional[str] = None
    step: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 0  # 0 = no row yet
    expires_at_ms: Optional[int] = None

    @property
    def active(self) -> bool:
        return bool(self.flow)

    def set(self, flow: Optional[str], step: Optional[str] = None, **data: Any) -> None:
        """Move to ``flow``/``step``; keeps generic keys (``_``-prefixed) only."""
        keep = {k: v for k, v in self.data.items() if k.startswith("_")}
        self.flow, self.step = flow, step
        self.data = {**keep, **data}

    def clear(self) -> None:
        self.set(None, None)


class StaleState(RuntimeError):
    """Someone else saved this conversation since we loaded it."""


def load(channel: str, external_id: str, *, now_ms: Optional[int] = None) -> ConversationState:
    now = now_ms if now_ms is not None else store.now_ms()
    d = store.db()
    with d.transaction(readonly=True) as tx:
        row = tx.one(
            "SELECT flow, step, data, version, expires_at_ms FROM channel_conversations "
            "WHERE channel = ? AND external_id = ?",
            (channel, str(external_id)),
        )
    if row is None:
        return ConversationState(channel, str(external_id))
    data = d.dialect.unjson(row["data"]) or {}
    st = ConversationState(
        channel,
        str(external_id),
        row["flow"],
        row["step"],
        data,
        int(row["version"]),
        row["expires_at_ms"],
    )
    if st.expires_at_ms is not None and st.expires_at_ms <= now and st.flow:
        st.flow, st.step = None, None
        st.data = {k: v for k, v in st.data.items() if k.startswith("_")}
    return st


def save(st: ConversationState, *, ttl_ms: int = DEFAULT_TTL_MS, now_ms: Optional[int] = None) -> None:
    """Write ``st`` if nobody else did since it was loaded (else ``StaleState``)."""
    now = now_ms if now_ms is not None else store.now_ms()
    expires = now + ttl_ms if st.flow else None
    d = store.db()
    with d.transaction() as tx:
        if st.version == 0:
            tx.lock_key("channel_conversation", st.channel, st.external_id)
            exists = tx.scalar(
                "SELECT version FROM channel_conversations WHERE channel = ? AND external_id = ?",
                (st.channel, st.external_id),
            )
            if exists is not None:
                raise StaleState(f"{st.channel}:{st.external_id} created concurrently")
            tx.execute(
                "INSERT INTO channel_conversations "
                "(channel, external_id, flow, step, data, version, expires_at_ms, updated_at_ms) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (st.channel, st.external_id, st.flow, st.step, tx.json(st.data), expires, now),
            )
            st.version = 1
        else:
            n = tx.rowcount(
                "UPDATE channel_conversations SET flow = ?, step = ?, data = ?, "
                "version = version + 1, expires_at_ms = ?, updated_at_ms = ? "
                "WHERE channel = ? AND external_id = ? AND version = ?",
                (st.flow, st.step, tx.json(st.data), expires, now,
                 st.channel, st.external_id, st.version),
            )
            if n != 1:
                raise StaleState(f"{st.channel}:{st.external_id} changed since version {st.version}")
            st.version += 1
    st.expires_at_ms = expires


def reset(channel: str, external_id: str) -> None:
    with store.db().transaction() as tx:
        tx.execute(
            "DELETE FROM channel_conversations WHERE channel = ? AND external_id = ?",
            (channel, str(external_id)),
        )


def has_active_flow(channel: str, external_id: str) -> bool:
    try:
        return load(channel, external_id).active
    except Exception:  # never let a state read break the legacy bot
        logger.warning("[channels] state read failed for %s", channel, exc_info=True)
        return False
