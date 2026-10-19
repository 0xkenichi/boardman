"""Naira-rail tables in the shared storage engine (SQLite locally, Postgres in prod).

* ``paycrest_orders``: one row per on-ramp or off-ramp, driven by an explicit
  state machine (``TRANSITIONS``). ``idempotency_key`` is unique and is also
  the ``reference`` we send Paycrest, so a retried request can never create a
  second order on our side, and an ambiguous submit can be found on theirs.
* ``paycrest_webhook_events``: webhook dedupe (SHA-256 of the raw body).
* ``payment_wallets``: per-player wallets on chains the play wallet does not
  live on (the Base wallet that receives Paycrest USDC). Kept apart from the
  profile's ``gaming_deposit_address`` so the play address never changes.
* ``bridge_transfers``: one row per CCTP transfer with every leg recorded.

Same pattern as ``src/channels/core/store.py``: DDL applied idempotently on
first use, Postgres rendering in
``supabase/migrations/20261018120000_paycrest_naira.sql`` (kept in sync by
tests/test_paycrest_store.py). No KYC data has a column here, by design.
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
    CREATE TABLE IF NOT EXISTS paycrest_orders (
      id TEXT PRIMARY KEY,
      idempotency_key TEXT NOT NULL UNIQUE,
      direction TEXT NOT NULL,
      profile_id TEXT NOT NULL,
      channel TEXT,
      external_id TEXT,
      status TEXT NOT NULL,
      paycrest_id TEXT,
      paycrest_status TEXT,
      amount_ngn TEXT,
      amount_usdc TEXT,
      rate TEXT,
      quote {JSON},
      provider_account {JSON},
      details {JSON},
      bridge_id TEXT,
      error TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt_at_ms BIGINT,
      created_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL,
      expires_at_ms BIGINT,
      settled_at_ms BIGINT
    )
    """,
    "CREATE INDEX IF NOT EXISTS paycrest_orders_profile_idx ON paycrest_orders (profile_id, created_at_ms)",
    "CREATE INDEX IF NOT EXISTS paycrest_orders_status_idx ON paycrest_orders (status, updated_at_ms)",
    "CREATE INDEX IF NOT EXISTS paycrest_orders_pcid_idx ON paycrest_orders (paycrest_id)",
    """
    CREATE TABLE IF NOT EXISTS paycrest_webhook_events (
      event_key TEXT PRIMARY KEY,
      paycrest_id TEXT,
      event TEXT,
      status TEXT,
      outcome TEXT,
      received_at_ms BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_wallets (
      profile_id TEXT NOT NULL,
      chain TEXT NOT NULL,
      wallet_id TEXT NOT NULL,
      address TEXT NOT NULL,
      account_type TEXT NOT NULL,
      created_at_ms BIGINT NOT NULL,
      PRIMARY KEY (profile_id, chain)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bridge_transfers (
      id TEXT PRIMARY KEY,
      idempotency_key TEXT NOT NULL UNIQUE,
      kind TEXT NOT NULL,
      profile_id TEXT NOT NULL,
      src_chain TEXT NOT NULL,
      dst_chain TEXT NOT NULL,
      amount_usdc TEXT NOT NULL,
      from_wallet_id TEXT NOT NULL,
      mint_recipient TEXT NOT NULL,
      fast INTEGER NOT NULL DEFAULT 0,
      max_fee_usdc TEXT,
      status TEXT NOT NULL,
      approve_tx_id TEXT,
      burn_tx_id TEXT,
      burn_tx_hash TEXT,
      message TEXT,
      attestation TEXT,
      mint_tx_id TEXT,
      mint_tx_hash TEXT,
      minted_usdc TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt_at_ms BIGINT,
      error TEXT,
      created_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS bridge_transfers_status_idx ON bridge_transfers (status, next_attempt_at_ms)",
]

TABLES = ("paycrest_orders", "paycrest_webhook_events", "payment_wallets", "bridge_transfers")

# ── order state machine ──────────────────────────────────────────────────────
#
# On-ramp (naira in):
#   quoted → submitting → awaiting_deposit → processing → settled → bridging → completed
#   failures: cancelled (link unused), failed (KYC refused, no provider),
#             expired (virtual account never funded), refunding → refunded (naira back)
# Off-ramp (cash out):
#   confirmed → bridging_out → on_base → submitting → awaiting_settlement →
#   processing → completed
#   failures: refunding → refunded_on_base → refund_bridging → refunded (USDC
#             back in the play wallet); needs_review for anything a human must see.
TRANSITIONS: dict[str, frozenset[str]] = {
    "quoted": frozenset({"submitting", "cancelled", "failed"}),
    "submitting": frozenset({"awaiting_deposit", "awaiting_settlement", "submit_unknown", "failed", "on_base",
                             "quoted", "refunded_on_base", "needs_review"}),
    "submit_unknown": frozenset({"awaiting_deposit", "awaiting_settlement", "failed", "on_base", "needs_review"}),
    "awaiting_deposit": frozenset({"processing", "settled", "expired", "refunding", "refunded", "cancelled"}),
    "processing": frozenset({"settled", "refunding", "refunded", "refunded_on_base", "expired", "completed",
                             "needs_review"}),
    "settled": frozenset({"bridging", "completed"}),
    "bridging": frozenset({"completed", "needs_review"}),
    "confirmed": frozenset({"bridging_out", "failed"}),
    "bridging_out": frozenset({"on_base", "needs_review", "failed"}),
    "on_base": frozenset({"submitting", "needs_review"}),
    "awaiting_settlement": frozenset({"processing", "completed", "refunding", "refunded_on_base", "expired",
                                      "needs_review"}),
    "refunding": frozenset({"refunded", "refunded_on_base", "settled", "completed", "needs_review"}),
    "refunded_on_base": frozenset({"refund_bridging", "needs_review"}),
    "refund_bridging": frozenset({"refunded", "needs_review"}),
    "needs_review": frozenset({"completed", "refunded", "failed", "on_base", "refunded_on_base"}),
}
TERMINAL = frozenset({"completed", "refunded", "expired", "failed", "cancelled"})
ORDER_COLUMNS = frozenset({
    "channel", "external_id", "paycrest_id", "paycrest_status", "amount_ngn", "amount_usdc", "rate",
    "quote", "provider_account", "details", "bridge_id", "error", "attempts", "next_attempt_at_ms",
    "expires_at_ms", "settled_at_ms",
})
JSON_COLUMNS = frozenset({"quote", "provider_account", "details"})

BRIDGE_STATUSES = ("pending", "approve_submitted", "burn_submitted", "burned", "attested", "mint_submitted",
                   "minted", "failed")
BRIDGE_OPEN = BRIDGE_STATUSES[:-2]
BRIDGE_COLUMNS = frozenset({
    "status", "approve_tx_id", "burn_tx_id", "burn_tx_hash", "message", "attestation", "mint_tx_id",
    "mint_tx_hash", "minted_usdc", "attempts", "next_attempt_at_ms", "error", "max_fee_usdc",
})


class IllegalTransition(RuntimeError):
    pass


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
                tx.execute("SELECT pg_advisory_xact_lock(724100318)")
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


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _decode(d: Database, row: Optional[dict], cols: Iterable[str]) -> Optional[dict]:
    if row is None:
        return None
    for c in cols:
        if c in row:
            row[c] = d.dialect.unjson(row[c]) if row[c] is not None else ({} if c != "quote" else None)
    return row


# ── orders ──────────────────────────────────────────────────────────────────


def create_order(*, idempotency_key: str, direction: str, profile_id: str, status: str,
                 **fields: Any) -> tuple[dict, bool]:
    """Insert once per idempotency key. Returns (row, created?)."""
    bad = set(fields) - ORDER_COLUMNS
    if bad:
        raise ValueError(f"unknown order columns: {sorted(bad)}")
    d = db()
    now = now_ms()
    oid = new_id("pc")
    with d.transaction() as tx:
        tx.lock_key("paycrest_order", idempotency_key)
        cur = tx.one("SELECT id FROM paycrest_orders WHERE idempotency_key = ?", (idempotency_key,))
        if cur is not None:
            existing = cur["id"]
        else:
            cols = ["id", "idempotency_key", "direction", "profile_id", "status", "created_at_ms", "updated_at_ms"]
            vals: list[Any] = [oid, idempotency_key, direction, profile_id, status, now, now]
            for k, v in fields.items():
                cols.append(k)
                vals.append(tx.json(v) if k in JSON_COLUMNS else v)
            for k in JSON_COLUMNS - set(fields):
                cols.append(k)
                vals.append(tx.json({}) if k != "quote" else None)
            tx.execute(f"INSERT INTO paycrest_orders ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                       vals)
            existing = None
    if existing is not None:
        return get_order(existing), False  # type: ignore[return-value]
    return get_order(oid), True  # type: ignore[return-value]


def get_order(order_id: str) -> Optional[dict]:
    d = db()
    with d.transaction(readonly=True) as tx:
        row = tx.one("SELECT * FROM paycrest_orders WHERE id = ?", (order_id,))
    return _decode(d, row, JSON_COLUMNS)


def get_order_by_paycrest_id(paycrest_id: str) -> Optional[dict]:
    d = db()
    with d.transaction(readonly=True) as tx:
        row = tx.one("SELECT * FROM paycrest_orders WHERE paycrest_id = ?", (paycrest_id,))
    return _decode(d, row, JSON_COLUMNS)


def get_order_by_key(idempotency_key: str) -> Optional[dict]:
    d = db()
    with d.transaction(readonly=True) as tx:
        row = tx.one("SELECT * FROM paycrest_orders WHERE idempotency_key = ?", (idempotency_key,))
    return _decode(d, row, JSON_COLUMNS)


def list_orders(*, statuses: Iterable[str] = (), profile_id: Optional[str] = None,
                direction: Optional[str] = None, limit: int = 200) -> list[dict]:
    where, params = [], []
    sts = list(statuses)
    if sts:
        where.append(f"status IN ({', '.join('?' * len(sts))})")
        params.extend(sts)
    if profile_id:
        where.append("profile_id = ?")
        params.append(profile_id)
    if direction:
        where.append("direction = ?")
        params.append(direction)
    sql = "SELECT * FROM paycrest_orders"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at_ms ASC LIMIT ?"
    params.append(int(limit))
    d = db()
    with d.transaction(readonly=True) as tx:
        rows = tx.all(sql, params)
    return [_decode(d, r, JSON_COLUMNS) for r in rows]  # type: ignore[misc]


def _set_clause(tx: Any, fields: dict[str, Any], allowed: frozenset[str]) -> tuple[str, list[Any]]:
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"unknown columns: {sorted(bad)}")
    parts, vals = [], []
    for k, v in fields.items():
        parts.append(f"{k} = ?")
        vals.append(tx.json(v) if k in JSON_COLUMNS else v)
    return ", ".join(parts), vals


def transition(order_id: str, to: str, *, expect: Optional[str | Iterable[str]] = None,
               details: Optional[dict] = None, **fields: Any) -> bool:
    """Move an order to ``to`` if the state machine allows it from where it is.

    ``expect`` narrows the allowed predecessors (compare-and-set). Returns
    False, writing nothing, when the order is elsewhere (a replayed or late
    webhook, a second worker); raises on a transition the machine forbids.
    ``details`` is merged into the JSON ``details`` column.
    """
    d = db()
    with d.transaction() as tx:
        row = tx.one("SELECT status, details FROM paycrest_orders WHERE id = ?", (order_id,))
        if row is None:
            return False
        cur = row["status"]
        if expect is not None:
            allowed_from = {expect} if isinstance(expect, str) else set(expect)
            if cur not in allowed_from:
                return False
        if cur == to:
            return False
        if to not in TRANSITIONS.get(cur, frozenset()):
            if cur in TERMINAL or expect is None:
                return False
            raise IllegalTransition(f"{order_id}: {cur} -> {to}")
        if details:
            merged = dict(d.dialect.unjson(row["details"]) or {})
            merged.update(details)
            fields["details"] = merged
        set_sql, vals = _set_clause(tx, fields, ORDER_COLUMNS)
        sql = "UPDATE paycrest_orders SET status = ?, updated_at_ms = ?"
        params: list[Any] = [to, now_ms()]
        if set_sql:
            sql += ", " + set_sql
            params.extend(vals)
        sql += " WHERE id = ? AND status = ?"
        params.extend([order_id, cur])
        return tx.rowcount(sql, params) == 1


def update_order(order_id: str, *, details: Optional[dict] = None, **fields: Any) -> None:
    """Write non-status fields (attempt counters, Paycrest status echo)."""
    d = db()
    with d.transaction() as tx:
        if details:
            row = tx.one("SELECT details FROM paycrest_orders WHERE id = ?", (order_id,))
            merged = dict(d.dialect.unjson((row or {}).get("details")) or {})
            merged.update(details)
            fields["details"] = merged
        set_sql, vals = _set_clause(tx, fields, ORDER_COLUMNS)
        if not set_sql:
            return
        tx.execute(f"UPDATE paycrest_orders SET {set_sql}, updated_at_ms = ? WHERE id = ?",
                   [*vals, now_ms(), order_id])


def sum_recent(profile_id: str, direction: str, column: str, since_ms: int,
               *, exclude_statuses: Iterable[str] = ("failed", "cancelled", "expired")) -> list[str]:
    """Amounts (as strings) a player moved recently, for daily caps."""
    if column not in ("amount_ngn", "amount_usdc"):
        raise ValueError(column)
    ex = list(exclude_statuses)
    sql = (f"SELECT {column} AS v FROM paycrest_orders WHERE profile_id = ? AND direction = ? "
           f"AND created_at_ms >= ?")
    params: list[Any] = [profile_id, direction, since_ms]
    if ex:
        sql += f" AND status NOT IN ({', '.join('?' * len(ex))})"
        params.extend(ex)
    with db().transaction(readonly=True) as tx:
        return [r["v"] for r in tx.all(sql, params) if r["v"] is not None]


# ── webhook dedupe ──────────────────────────────────────────────────────────


def record_event(event_key: str, *, paycrest_id: str, event: str, status: str) -> bool:
    """True the first time we see this delivery; False for a replay."""
    with db().transaction() as tx:
        tx.lock_key("paycrest_event", event_key)
        if tx.one("SELECT 1 AS x FROM paycrest_webhook_events WHERE event_key = ?", (event_key,)):
            return False
        tx.execute(
            "INSERT INTO paycrest_webhook_events (event_key, paycrest_id, event, status, outcome, received_at_ms) "
            "VALUES (?, ?, ?, ?, 'received', ?)",
            (event_key, paycrest_id, event, status, now_ms()),
        )
        return True


def forget_event(event_key: str) -> None:
    """Un-see a delivery whose processing failed, so Paycrest's retry of the
    same body is processed instead of answered 'duplicate'."""
    with db().transaction() as tx:
        tx.execute("DELETE FROM paycrest_webhook_events WHERE event_key = ? AND outcome = 'received'", (event_key,))


def set_event_outcome(event_key: str, outcome: str) -> None:
    with db().transaction() as tx:
        tx.execute("UPDATE paycrest_webhook_events SET outcome = ? WHERE event_key = ?", (outcome[:200], event_key))


# ── wallets on non-play chains ──────────────────────────────────────────────


def get_wallet(profile_id: str, chain: str) -> Optional[dict]:
    with db().transaction(readonly=True) as tx:
        return tx.one("SELECT * FROM payment_wallets WHERE profile_id = ? AND chain = ?", (profile_id, chain))


def put_wallet(profile_id: str, chain: str, wallet_id: str, address: str, account_type: str) -> dict:
    """Insert once; an existing wallet always wins (never replace an address)."""
    with db().transaction() as tx:
        tx.lock_key("payment_wallet", profile_id, chain)
        cur = tx.one("SELECT * FROM payment_wallets WHERE profile_id = ? AND chain = ?", (profile_id, chain))
        if cur is not None:
            return cur
        tx.execute(
            "INSERT INTO payment_wallets (profile_id, chain, wallet_id, address, account_type, created_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (profile_id, chain, wallet_id, address, account_type, now_ms()),
        )
        return {"profile_id": profile_id, "chain": chain, "wallet_id": wallet_id, "address": address,
                "account_type": account_type}


def wallet_by_id(wallet_id: str) -> Optional[dict]:
    with db().transaction(readonly=True) as tx:
        return tx.one("SELECT * FROM payment_wallets WHERE wallet_id = ?", (wallet_id,))


def wallet_owner(chain: str, address: str) -> Optional[str]:
    with db().transaction(readonly=True) as tx:
        row = tx.one("SELECT profile_id FROM payment_wallets WHERE chain = ? AND lower(address) = ?",
                     (chain, (address or "").lower()))
    return row["profile_id"] if row else None


# ── bridge transfers ────────────────────────────────────────────────────────


def create_bridge(*, idempotency_key: str, kind: str, profile_id: str, src_chain: str, dst_chain: str,
                  amount_usdc: str, from_wallet_id: str, mint_recipient: str, fast: bool,
                  max_fee_usdc: str = "0") -> tuple[dict, bool]:
    d = db()
    now = now_ms()
    bid = new_id("br")
    with d.transaction() as tx:
        tx.lock_key("bridge", idempotency_key)
        cur = tx.one("SELECT * FROM bridge_transfers WHERE idempotency_key = ?", (idempotency_key,))
        if cur is not None:
            return cur, False
        tx.execute(
            "INSERT INTO bridge_transfers (id, idempotency_key, kind, profile_id, src_chain, dst_chain, amount_usdc, "
            "from_wallet_id, mint_recipient, fast, max_fee_usdc, status, attempts, next_attempt_at_ms, "
            "created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)",
            (bid, idempotency_key, kind, profile_id, src_chain, dst_chain, amount_usdc, from_wallet_id,
             mint_recipient, 1 if fast else 0, max_fee_usdc, now, now, now),
        )
    return get_bridge(bid), True  # type: ignore[return-value]


def get_bridge(bridge_id: str) -> Optional[dict]:
    with db().transaction(readonly=True) as tx:
        return tx.one("SELECT * FROM bridge_transfers WHERE id = ?", (bridge_id,))


def update_bridge(bridge_id: str, *, expect: Optional[str] = None, **fields: Any) -> bool:
    with db().transaction() as tx:
        set_sql, vals = _set_clause(tx, fields, BRIDGE_COLUMNS)
        sql = f"UPDATE bridge_transfers SET {set_sql}, updated_at_ms = ? WHERE id = ?"
        params: list[Any] = [*vals, now_ms(), bridge_id]
        if expect is not None:
            sql += " AND status = ?"
            params.append(expect)
        return tx.rowcount(sql, params) == 1


def list_bridges(*, statuses: Iterable[str], due_before_ms: Optional[int] = None, limit: int = 100) -> list[dict]:
    sts = list(statuses)
    sql = f"SELECT * FROM bridge_transfers WHERE status IN ({', '.join('?' * len(sts))})"
    params: list[Any] = list(sts)
    if due_before_ms is not None:
        sql += " AND (next_attempt_at_ms IS NULL OR next_attempt_at_ms <= ?)"
        params.append(due_before_ms)
    sql += " ORDER BY created_at_ms ASC LIMIT ?"
    params.append(int(limit))
    with db().transaction(readonly=True) as tx:
        return tx.all(sql, params)


def postgres_migration_sql() -> str:
    from gaming.src.stack.agentic.db.engine import PostgresDialect

    head = (
        "-- Boardman naira rail (Paycrest on/off-ramp) and CCTP bridge legs.\n"
        "-- Lives in the agentic store's database. No KYC columns, by design.\n"
        "-- Generated from src/backend/services/paycrest/store.py — edit there, then regenerate:\n"
        "-- python -m gaming.src.backend.services.paycrest.store > <this file>\n\n"
        "BEGIN;\n\n"
    )
    body = ";\n\n".join(render(PostgresDialect(), pretty=True)) + ";\n\n"
    body += "-- Never reachable with the anon/authenticated keys.\n"
    body += ";\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in TABLES) + ";\n\n"
    return head + body + "COMMIT;\n"


if __name__ == "__main__":  # pragma: no cover
    print(postgres_migration_sql(), end="")
