"""Channels tables in the shared storage engine (SQLite locally, Postgres in prod).

Conversation state, one-time tokens, rate-limit events, inbound dedupe and the
notification outbox all live here, in ``src/stack/agentic/db/engine.py``'s
database, so a restart or a second webhook worker sees the same state
(CHANNELS_DESIGN §3.2). The DDL is applied idempotently on first use; the
Postgres rendering is ``supabase/migrations/20261016120100_channels_state.sql``
(kept in sync by tests/test_channels_store.py).

Identities live with the profiles in Supabase instead (``identity/repo.py``).
"""
from __future__ import annotations

import logging
import textwrap
import threading
import time
import weakref
from typing import Any

from gaming.src.stack.agentic.db.engine import Database, get_db

logger = logging.getLogger(__name__)

TEMPLATE = [
    """
    CREATE TABLE IF NOT EXISTS channel_conversations (
      channel TEXT NOT NULL,
      external_id TEXT NOT NULL,
      flow TEXT,
      step TEXT,
      data {JSON} NOT NULL,
      version BIGINT NOT NULL DEFAULT 1,
      expires_at_ms BIGINT,
      updated_at_ms BIGINT NOT NULL,
      PRIMARY KEY (channel, external_id)
    )
    """,
    # One-time tokens (withdraw links, PIN resets). Only the SHA-256 of the
    # token is stored; the plain token exists only in the link we send.
    """
    CREATE TABLE IF NOT EXISTS channel_tokens (
      token_hash TEXT PRIMARY KEY,
      purpose TEXT NOT NULL,
      profile_id TEXT NOT NULL,
      channel TEXT NOT NULL,
      external_id TEXT,
      amount_micro BIGINT,
      payload {JSON} NOT NULL,
      status TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0,
      created_at_ms BIGINT NOT NULL,
      expires_at_ms BIGINT NOT NULL,
      consumed_at_ms BIGINT,
      result {JSON}
    )
    """,
    "CREATE INDEX IF NOT EXISTS channel_tokens_profile_idx ON channel_tokens (profile_id, created_at_ms)",
    """
    CREATE TABLE IF NOT EXISTS channel_rate_events (
      id {AUTOID},
      bucket TEXT NOT NULL,
      at_ms BIGINT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS channel_rate_bucket_idx ON channel_rate_events (bucket, at_ms)",
    # Webhooks are at-least-once: the provider message id is the dedupe key.
    """
    CREATE TABLE IF NOT EXISTS channel_inbound (
      channel TEXT NOT NULL,
      message_id TEXT NOT NULL,
      external_id TEXT,
      status TEXT NOT NULL,
      payload {JSON},
      received_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL,
      PRIMARY KEY (channel, message_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS channel_inbound_status_idx ON channel_inbound (status, received_at_ms)",
    """
    CREATE TABLE IF NOT EXISTS channel_outbox (
      id {AUTOID},
      channel TEXT NOT NULL,
      external_id TEXT NOT NULL,
      profile_id TEXT,
      kind TEXT NOT NULL,
      mode TEXT NOT NULL,
      template TEXT,
      provider_message_id TEXT,
      status TEXT NOT NULL,
      error TEXT,
      created_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS channel_outbox_provider_idx ON channel_outbox (provider_message_id)",
]

TABLES = (
    "channel_conversations",
    "channel_tokens",
    "channel_rate_events",
    "channel_inbound",
    "channel_outbox",
)

# Weak, so a handle closed by reset_databases() (and a new one that happens to
# reuse its id) is never mistaken for one that already has the tables.
_ready: "weakref.WeakSet[Database]" = weakref.WeakSet()
_ready_lock = threading.Lock()


def render(dialect: Any, *, pretty: bool = False) -> list[str]:
    out = []
    for stmt in TEMPLATE:
        text = textwrap.dedent(stmt).strip() if pretty else " ".join(stmt.split())
        out.append(text.replace("{AUTOID}", dialect.autoid).replace("{JSON}", dialect.json_type))
    return out


def _ensure(db: Database) -> None:
    if db in _ready:
        return
    with _ready_lock:
        if db in _ready:
            return
        with db.transaction() as tx:
            if db.is_postgres:
                tx.execute("SELECT pg_advisory_xact_lock(724100317)")
            for stmt in render(db.dialect):
                tx.execute(stmt)
            if db.is_postgres:
                for t in TABLES:
                    tx.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _ready.add(db)


def db() -> Database:
    """The engine database with the channels tables present."""
    d = get_db()
    _ensure(d)
    return d


def now_ms() -> int:
    return int(time.time() * 1000)


def postgres_migration_sql() -> str:
    from gaming.src.stack.agentic.db.engine import PostgresDialect

    head = (
        "-- Boardman channels state: conversation state machines, one-time tokens\n"
        "-- (withdraw links, PIN resets), rate-limit events, inbound webhook dedupe\n"
        "-- and the notification outbox. Lives in the agentic store's database.\n"
        "-- Generated from src/channels/core/store.py — edit there, then regenerate:\n"
        "-- python -m gaming.src.channels.core.store > <this file>\n\n"
        "BEGIN;\n\n"
    )
    body = ";\n\n".join(render(PostgresDialect(), pretty=True)) + ";\n\n"
    body += "-- Never reachable with the anon/authenticated keys.\n"
    body += ";\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in TABLES) + ";\n\n"
    return head + body + "COMMIT;\n"


if __name__ == "__main__":  # pragma: no cover
    print(postgres_migration_sql(), end="")
