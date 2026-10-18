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

# Wallet link / change requests (the setup proof). Separate migration:
# supabase/migrations/20261018150000_self_custody_wallet_requests.sql.
REQUEST_TEMPLATE = [
    """
    CREATE TABLE IF NOT EXISTS self_custody_wallet_requests (
      id TEXT PRIMARY KEY,
      profile_id TEXT NOT NULL,
      kind TEXT NOT NULL,
      chain TEXT NOT NULL,
      evm_chain_id BIGINT NOT NULL,
      address TEXT NOT NULL,
      credential_id TEXT,
      previous_address TEXT,
      token_hash TEXT,
      message TEXT NOT NULL,
      confirm_hash TEXT,
      status TEXT NOT NULL,
      created_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL,
      expires_at_ms BIGINT NOT NULL,
      proved_at_ms BIGINT,
      confirmed_at_ms BIGINT,
      active_at_ms BIGINT
    )
    """,
    "CREATE INDEX IF NOT EXISTS self_custody_wallet_requests_profile_idx "
    "ON self_custody_wallet_requests (profile_id, status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS self_custody_wallet_requests_confirm_idx "
    "ON self_custody_wallet_requests (confirm_hash)",
]

REQUEST_TABLES = ("self_custody_wallet_requests",)

# challenge → verifying → pending_confirm → active            (setup)
#                                         → cooling → active  (change, after the cool-down)
# other ends: failed (bad proof), expired, superseded, declined (chat "No"), cancelled.

# prepared → submitted → confirmed | failed; prepared → expired | superseded;
# prepared → confirmed when the watcher finds the event without a client report.
OPEN = ("prepared", "submitted")
TERMINAL = ("confirmed", "failed", "expired", "superseded")

_ready: "weakref.WeakSet[Database]" = weakref.WeakSet()
_ready_lock = threading.Lock()


def render(dialect: Any, *, pretty: bool = False, template: Optional[list[str]] = None) -> list[str]:
    out = []
    for stmt in TEMPLATE if template is None else template:
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
            for stmt in render(db.dialect) + render(db.dialect, template=REQUEST_TEMPLATE):
                tx.execute(stmt)
            if db.is_postgres:
                for t in TABLES + REQUEST_TABLES:
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


# ── wallet link / change requests ────────────────────────────────────────────

_REQ_FIELDS = {"credential_id", "confirm_hash", "expires_at_ms", "proved_at_ms", "confirmed_at_ms", "active_at_ms"}


def create_request(*, request_id: str, profile_id: str, kind: str, chain: str, evm_chain_id: int, address: str,
                   previous_address: Optional[str], token_hash: Optional[str], message: str,
                   created_at_ms: int, expires_at_ms: int) -> dict:
    """A fresh challenge; older unsigned challenges of this profile are superseded."""
    with db().transaction() as tx:
        tx.lock_key("self_custody_wallet_request", profile_id)
        tx.execute(
            "UPDATE self_custody_wallet_requests SET status = 'superseded', updated_at_ms = ? "
            "WHERE profile_id = ? AND status = 'challenge'",
            (created_at_ms, profile_id),
        )
        tx.execute(
            "INSERT INTO self_custody_wallet_requests (id, profile_id, kind, chain, evm_chain_id, address, "
            "previous_address, token_hash, message, status, created_at_ms, updated_at_ms, expires_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'challenge', ?, ?, ?)",
            (request_id, profile_id, kind, chain, int(evm_chain_id), address, previous_address, token_hash,
             message, created_at_ms, created_at_ms, expires_at_ms),
        )
    return get_request(request_id)  # type: ignore[return-value]


def get_request(request_id: str) -> Optional[dict]:
    with db().transaction(readonly=True) as tx:
        return tx.one("SELECT * FROM self_custody_wallet_requests WHERE id = ?", (request_id,))


def request_by_confirm(confirm_hash: str) -> Optional[dict]:
    with db().transaction(readonly=True) as tx:
        return tx.one("SELECT * FROM self_custody_wallet_requests WHERE confirm_hash = ?", (confirm_hash,))


def requests_for(profile_id: str, statuses: Iterable[str], chain: Optional[str] = None) -> list[dict]:
    sts = list(statuses)
    sql = (f"SELECT * FROM self_custody_wallet_requests WHERE profile_id = ? "
           f"AND status IN ({', '.join('?' for _ in sts)})")
    params: list[Any] = [profile_id, *sts]
    if chain is not None:
        sql += " AND chain = ?"
        params.append(chain)
    sql += " ORDER BY created_at_ms DESC"
    with db().transaction(readonly=True) as tx:
        return tx.all(sql, params)


def move_request(request_id: str, to: str, *, expect: Iterable[str], **fields: Any) -> bool:
    """Compare-and-set on a request's status (plus a few allowed fields)."""
    exp = list(expect)
    sets, params = ["status = ?", "updated_at_ms = ?"], [to, now_ms()]
    for k, v in fields.items():
        if k not in _REQ_FIELDS:
            raise ValueError(k)
        sets.append(f"{k} = ?")
        params.append(v)
    params.append(request_id)
    params.extend(exp)
    with db().transaction() as tx:
        return tx.rowcount(
            f"UPDATE self_custody_wallet_requests SET {', '.join(sets)} WHERE id = ? "
            f"AND status IN ({', '.join('?' for _ in exp)})", params) == 1


def supersede_pending(profile_id: str, keep: str) -> int:
    """A newer proven request replaces older ones still waiting for the chat
    or in their cool-down: only the newest one can ever win."""
    with db().transaction() as tx:
        return tx.rowcount(
            "UPDATE self_custody_wallet_requests SET status = 'superseded', updated_at_ms = ? "
            "WHERE profile_id = ? AND id <> ? AND status IN ('pending_confirm', 'cooling')",
            (now_ms(), profile_id, keep))


def _ensure_wallet_table() -> None:
    from gaming.src.backend.services.paycrest import store as pstore

    pstore.db()


def activate_setup(request_id: str, *, wallet_key: str, wallet_id: str, account_type: str,
                   now: int) -> tuple[bool, str]:
    """``pending_confirm`` → ``active`` and the first ``payment_wallets`` row,
    in one transaction. Returns (ok, reason)."""
    _ensure_wallet_table()
    with db().transaction() as tx:
        req = tx.one("SELECT * FROM self_custody_wallet_requests WHERE id = ?", (request_id,))
        if req is None or req["status"] != "pending_confirm":
            return False, "state"
        tx.lock_key("payment_wallet", req["profile_id"], wallet_key)
        owner = tx.one("SELECT profile_id FROM payment_wallets WHERE chain = ? AND lower(address) = ?",
                       (wallet_key, req["address"].lower()))
        if owner is not None and str(owner["profile_id"]) != str(req["profile_id"]):
            return False, "taken"
        cur = tx.one("SELECT address FROM payment_wallets WHERE profile_id = ? AND chain = ?",
                     (req["profile_id"], wallet_key))
        if cur is not None and cur["address"].lower() != req["address"].lower():
            return False, "exists"
        if tx.rowcount("UPDATE self_custody_wallet_requests SET status = 'active', updated_at_ms = ?, "
                       "confirmed_at_ms = ?, active_at_ms = ? WHERE id = ? AND status = 'pending_confirm'",
                       (now, now, now, request_id)) != 1:
            return False, "state"
        if cur is None:
            tx.execute(
                "INSERT INTO payment_wallets (profile_id, chain, wallet_id, address, account_type, created_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (req["profile_id"], wallet_key, wallet_id, req["address"], account_type, now),
            )
    return True, "ok"


def promote_change(request_id: str, *, wallet_key: str, wallet_id: str, account_type: str, now: int) -> bool:
    """``cooling`` → ``active`` once ``active_at_ms`` has passed, swapping the
    ``payment_wallets`` address only if it is still the one the change was
    made against. One transaction; anything unexpected fails the change."""
    _ensure_wallet_table()
    with db().transaction() as tx:
        req = tx.one("SELECT * FROM self_custody_wallet_requests WHERE id = ?", (request_id,))
        if req is None or req["status"] != "cooling" or int(req["active_at_ms"] or 0) > now:
            return False
        tx.lock_key("payment_wallet", req["profile_id"], wallet_key)
        owner = tx.one("SELECT profile_id FROM payment_wallets WHERE chain = ? AND lower(address) = ?",
                       (wallet_key, req["address"].lower()))
        moved = 0
        if owner is None or str(owner["profile_id"]) == str(req["profile_id"]):
            moved = tx.rowcount(
                "UPDATE payment_wallets SET wallet_id = ?, address = ?, account_type = ? "
                "WHERE profile_id = ? AND chain = ? AND lower(address) = ?",
                (wallet_id, req["address"], account_type, req["profile_id"], wallet_key,
                 (req["previous_address"] or "").lower()))
        tx.execute("UPDATE self_custody_wallet_requests SET status = ?, updated_at_ms = ? WHERE id = ?",
                   ("active" if moved == 1 else "failed", now, request_id))
    return moved == 1


def postgres_requests_migration_sql() -> str:
    from gaming.src.stack.agentic.db.engine import PostgresDialect

    head = (
        "-- Boardman self-custody passkey wallets: wallet link / change requests\n"
        "-- (signed setup proof, in-chat confirmation, change cool-down).\n"
        "-- Generated from src/backend/services/self_custody/store.py — edit there, then regenerate:\n"
        "-- python -m gaming.src.backend.services.self_custody.store requests > <this file>\n\n"
        "BEGIN;\n\n"
    )
    body = ";\n\n".join(render(PostgresDialect(), pretty=True, template=REQUEST_TEMPLATE)) + ";\n\n"
    body += "-- Never reachable with the anon/authenticated keys.\n"
    body += ";\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in REQUEST_TABLES) + ";\n\n"
    return head + body + "COMMIT;\n"


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
    import sys

    print(postgres_requests_migration_sql() if sys.argv[1:] == ["requests"] else postgres_migration_sql(), end="")
