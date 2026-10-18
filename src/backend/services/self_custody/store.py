"""Self-custody intents in the shared storage engine (SQLite locally, Postgres in prod).

An *intent* is one prepared action for one player: exactly which calls their
smart account is asked to sign (lock a stake, withdraw), bound to the profile,
the account, the amount and the match. Its approve link is a ``channel_tokens``
row (``withdraw_links``: SHA-256 at rest, short TTL, single use); the intent
only ever reaches ``confirmed`` after the chain shows the matching event.

Passkey accounts themselves live in ``payment_wallets`` (paycrest store), the
existing per-player wallet table, under the chain key ``<chain>/passkey``.

Same pattern as ``src/channels/core/store.py``; Postgres rendering in
``supabase/migrations/20261018130000_self_custody_intents.sql`` (kept in sync
by tests/test_self_custody.py).
"""
from __future__ import annotations

import textwrap
import threading
import time
import uuid
import weakref
from typing import Any, Iterable, Optional

from gaming.src.stack.agentic.db.engine import Database, get_db

TEMPLATE = [
    """
    CREATE TABLE IF NOT EXISTS self_custody_intents (
      id TEXT PRIMARY KEY,
      profile_id TEXT NOT NULL,
      action TEXT NOT NULL,
      chain TEXT NOT NULL,
      account TEXT NOT NULL,
      challenge_id TEXT,
      amount_micro BIGINT NOT NULL,
      to_address TEXT,
      calls {JSON} NOT NULL,
      detail {JSON} NOT NULL,
      status TEXT NOT NULL,
      token_hash TEXT,
      user_op_hash TEXT,
      tx_hash TEXT,
      from_block BIGINT,
      created_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL,
      expires_at_ms BIGINT NOT NULL,
      confirmed_at_ms BIGINT
    )
    """,
    "CREATE INDEX IF NOT EXISTS self_custody_intents_profile_idx ON self_custody_intents (profile_id, created_at_ms)",
    "CREATE INDEX IF NOT EXISTS self_custody_intents_status_idx ON self_custody_intents (status, updated_at_ms)",
    "CREATE INDEX IF NOT EXISTS self_custody_intents_match_idx ON self_custody_intents (challenge_id, profile_id)",
    # One transaction can confirm one intent, never two.
    "CREATE UNIQUE INDEX IF NOT EXISTS self_custody_intents_tx_idx ON self_custody_intents (tx_hash)",
]

TABLES = ("self_custody_intents",)

# prepared → submitted → confirmed | failed; prepared → expired | superseded;
# prepared → confirmed when the watcher finds the event without a client report.
OPEN = ("prepared", "submitted")
TERMINAL = ("confirmed", "failed", "expired", "superseded")

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
                tx.execute("SELECT pg_advisory_xact_lock(724100319)")
            for stmt in render(db.dialect):
                tx.execute(stmt)
            if db.is_postgres:
                for t in TABLES:
                    tx.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _ready.add(db)


def db() -> Database:
    d = get_db()
    _ensure(d)
    return d


def now_ms() -> int:
    return int(time.time() * 1000)


def _decode(d: Database, row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    for c in ("calls", "detail"):
        row[c] = d.dialect.unjson(row.get(c)) if row.get(c) is not None else ([] if c == "calls" else {})
    return row


def create(*, profile_id: str, action: str, chain: str, account: str, challenge_id: Optional[str],
           amount_micro: int, to_address: Optional[str], calls: list[dict], detail: dict,
           expires_at_ms: int, from_block: Optional[int]) -> dict:
    """Insert a prepared intent; older *prepared* ones for the same action and
    match are superseded (a newer link replaces the old one)."""
    d = db()
    now = now_ms()
    iid = f"sci_{uuid.uuid4().hex[:24]}"
    with d.transaction() as tx:
        tx.lock_key("self_custody_intent", profile_id, action, challenge_id or "")
        tx.execute(
            "UPDATE self_custody_intents SET status = 'superseded', updated_at_ms = ? "
            "WHERE profile_id = ? AND action = ? AND status = 'prepared' AND "
            "COALESCE(challenge_id, '') = ?",
            (now, profile_id, action, challenge_id or ""),
        )
        tx.execute(
            "INSERT INTO self_custody_intents (id, profile_id, action, chain, account, challenge_id, "
            "amount_micro, to_address, calls, detail, status, created_at_ms, updated_at_ms, expires_at_ms, "
            "from_block) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?, ?, ?)",
            (iid, profile_id, action, chain, account, challenge_id, int(amount_micro), to_address,
             tx.json(calls), tx.json(detail), now, now, int(expires_at_ms), from_block),
        )
    return get(iid)  # type: ignore[return-value]


def get(intent_id: str) -> Optional[dict]:
    d = db()
    with d.transaction(readonly=True) as tx:
        return _decode(d, tx.one("SELECT * FROM self_custody_intents WHERE id = ?", (intent_id,)))


def set_token(intent_id: str, token_hash: str) -> None:
    with db().transaction() as tx:
        tx.execute("UPDATE self_custody_intents SET token_hash = ? WHERE id = ?", (token_hash, intent_id))


def find(*, profile_id: Optional[str] = None, challenge_id: Optional[str] = None,
         action: Optional[str] = None, statuses: Iterable[str] = (), limit: int = 50) -> list[dict]:
    sql = "SELECT * FROM self_custody_intents WHERE 1 = 1"
    params: list[Any] = []
    for col, val in (("profile_id", profile_id), ("challenge_id", challenge_id), ("action", action)):
        if val is not None:
            sql += f" AND {col} = ?"
            params.append(val)
    sts = list(statuses)
    if sts:
        sql += f" AND status IN ({', '.join('?' for _ in sts)})"
        params.extend(sts)
    sql += " ORDER BY created_at_ms DESC LIMIT ?"
    params.append(int(limit))
    d = db()
    with d.transaction(readonly=True) as tx:
        return [_decode(d, r) for r in tx.all(sql, params)]  # type: ignore[misc]


def transition(intent_id: str, to: str, *, expect: Iterable[str], **fields: Any) -> bool:
    """Compare-and-set: only from one of ``expect``. Returns True if it moved."""
    allowed = {"user_op_hash", "tx_hash", "confirmed_at_ms", "detail"}
    exp = list(expect)
    d = db()
    with d.transaction() as tx:
        sets = ["status = ?", "updated_at_ms = ?"]
        params: list[Any] = [to, now_ms()]
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(k)
            sets.append(f"{k} = ?")
            params.append(tx.json(v) if k == "detail" else v)
        sql = (f"UPDATE self_custody_intents SET {', '.join(sets)} WHERE id = ? "
               f"AND status IN ({', '.join('?' for _ in exp)})")
        params.append(intent_id)
        params.extend(exp)
        return tx.rowcount(sql, params) == 1


def tx_hash_taken(tx_hash: str, other_than: str) -> bool:
    with db().transaction(readonly=True) as tx:
        return tx.one("SELECT id FROM self_custody_intents WHERE tx_hash = ? AND id <> ?",
                      (tx_hash, other_than)) is not None


def postgres_migration_sql() -> str:
    from gaming.src.stack.agentic.db.engine import PostgresDialect

    head = (
        "-- Boardman self-custody passkey wallets: prepared intents (lock / withdraw)\n"
        "-- that the player approves with a passkey. Accounts live in payment_wallets.\n"
        "-- Generated from src/backend/services/self_custody/store.py — edit there, then regenerate:\n"
        "-- python -m gaming.src.backend.services.self_custody.store > <this file>\n\n"
        "BEGIN;\n\n"
    )
    body = ";\n\n".join(render(PostgresDialect(), pretty=True)) + ";\n\n"
    body += "-- Never reachable with the anon/authenticated keys.\n"
    body += ";\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in TABLES) + ";\n\n"
    return head + body + "COMMIT;\n"


if __name__ == "__main__":  # pragma: no cover
    print(postgres_migration_sql(), end="")
