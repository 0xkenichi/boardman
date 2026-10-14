"""Portable DDL for the agentic store.

One template renders for both backends: ``{AUTOID}`` and ``{JSON}`` are the only
dialect differences. ``supabase/migrations/*_agentic_ledger.sql`` is the
Postgres rendering of this file (tests/test_storage_schema.py keeps them in
sync); the app also applies it idempotently on first connect.

Money columns are integer micro-USDC (6 decimals). ``ledger_balances`` refuses
a negative balance at the database level.
"""
from __future__ import annotations

import re
import textwrap
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
_INDEX_RE = re.compile(r"CREATE INDEX IF NOT EXISTS (\w+)")

TEMPLATE = [
    """
    CREATE TABLE IF NOT EXISTS storage_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    # ── ledger ──
    """
    CREATE TABLE IF NOT EXISTS ledger_balances (
      wallet TEXT PRIMARY KEY,
      balance_micro BIGINT NOT NULL DEFAULT 0 CHECK (balance_micro >= 0),
      scale SMALLINT NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ledger_txs (
      id {AUTOID},
      ts TEXT NOT NULL,
      type TEXT NOT NULL,
      wallet TEXT,
      ref TEXT,
      reason TEXT,
      amount_micro BIGINT,
      balance_after_micro BIGINT,
      doc {JSON} NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ledger_txs_wallet_idx ON ledger_txs (wallet, id)",
    "CREATE INDEX IF NOT EXISTS ledger_txs_ref_idx ON ledger_txs (ref)",
    "CREATE INDEX IF NOT EXISTS ledger_txs_reason_idx ON ledger_txs (reason)",
    """
    CREATE TABLE IF NOT EXISTS ledger_escrows (
      match_id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      stake_micro BIGINT NOT NULL CHECK (stake_micro >= 0),
      agent_a_wallet TEXT NOT NULL,
      agent_b_wallet TEXT NOT NULL,
      result TEXT,
      created_at TEXT NOT NULL,
      settled_at TEXT,
      doc {JSON} NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ledger_escrows_status_idx ON ledger_escrows (status)",
    # ── documents (matches, spectator books, LP pools) ──
    """
    CREATE TABLE IF NOT EXISTS agentic_matches (
      match_id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      created_at TEXT,
      updated_at TEXT,
      settled_at TEXT,
      version BIGINT NOT NULL DEFAULT 1,
      doc {JSON} NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS agentic_matches_status_idx ON agentic_matches (status, settled_at)",
    "CREATE INDEX IF NOT EXISTS agentic_matches_updated_idx ON agentic_matches (updated_at)",
    """
    CREATE TABLE IF NOT EXISTS spectator_books (
      match_id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      created_at TEXT,
      updated_at TEXT,
      settled_at TEXT,
      version BIGINT NOT NULL DEFAULT 1,
      doc {JSON} NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS spectator_books_status_idx ON spectator_books (status, settled_at)",
    """
    CREATE TABLE IF NOT EXISTS lp_pools (
      agent_id TEXT PRIMARY KEY,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT,
      updated_at TEXT,
      settled_at TEXT,
      version BIGINT NOT NULL DEFAULT 1,
      doc {JSON} NOT NULL
    )
    """,
    # ── settlement state ──
    """
    CREATE TABLE IF NOT EXISTS settlement_journal (
      match_id TEXT NOT NULL,
      step TEXT NOT NULL,
      owner TEXT,
      created_at TEXT NOT NULL,
      detail {JSON},
      PRIMARY KEY (match_id, step)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_leases (
      match_id TEXT PRIMARY KEY,
      owner TEXT NOT NULL,
      epoch BIGINT NOT NULL DEFAULT 1,
      acquired_at_ms BIGINT NOT NULL,
      heartbeat_at_ms BIGINT NOT NULL,
      expires_at_ms BIGINT NOT NULL
    )
    """,
    # ── on-chain sends (nonce reservations + tx outcomes) ──
    """
    CREATE TABLE IF NOT EXISTS signer_locks (
      chain_key TEXT NOT NULL,
      signer TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (chain_key, signer)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS onchain_txs (
      id {AUTOID},
      chain_key TEXT NOT NULL,
      signer TEXT NOT NULL,
      nonce BIGINT NOT NULL CHECK (nonce >= 0),
      label TEXT NOT NULL,
      status TEXT NOT NULL,
      tx_hash TEXT,
      created_at TEXT NOT NULL,
      updated_at_ms BIGINT NOT NULL,
      block_number BIGINT,
      error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS onchain_txs_status_idx ON onchain_txs (status)",
    "CREATE INDEX IF NOT EXISTS onchain_txs_signer_idx ON onchain_txs (chain_key, signer, nonce)",
    "CREATE INDEX IF NOT EXISTS onchain_txs_hash_idx ON onchain_txs (tx_hash)",
    # ── tournament payouts ──
    """
    CREATE TABLE IF NOT EXISTS tournament_payouts (
      tournament_key TEXT NOT NULL,
      place INTEGER NOT NULL,
      profile_id TEXT NOT NULL,
      amount_micro BIGINT NOT NULL CHECK (amount_micro >= 0),
      idempotency_key TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL,
      claimed_by TEXT,
      claimed_at_ms BIGINT,
      transaction_id TEXT,
      tx_hash TEXT,
      error TEXT,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (tournament_key, place)
    )
    """,
    # ── house log (was data/agentic/house_log.db) ──
    """
    CREATE TABLE IF NOT EXISTS house_log_games (
      match_id TEXT PRIMARY KEY,
      game_id TEXT,
      status TEXT,
      stake_usdc TEXT,
      white_agent_id TEXT,
      black_agent_id TEXT,
      agent_a_id TEXT,
      agent_b_id TEXT,
      winner_agent_id TEXT,
      result TEXT,
      settlement_mode TEXT,
      created_at TEXT,
      settled_at TEXT,
      updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS house_log_txs (
      tx_hash TEXT PRIMARY KEY,
      step TEXT,
      match_id TEXT,
      agent_id TEXT,
      explorer TEXT,
      created_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS house_log_txs_match_idx ON house_log_txs (match_id)",
]

TABLES = (
    "storage_meta",
    "ledger_balances",
    "ledger_txs",
    "ledger_escrows",
    "agentic_matches",
    "spectator_books",
    "lp_pools",
    "settlement_journal",
    "match_leases",
    "signer_locks",
    "onchain_txs",
    "tournament_payouts",
    "house_log_games",
    "house_log_txs",
)


def render(dialect: Any, *, pretty: bool = False) -> list[str]:
    out = []
    for stmt in TEMPLATE:
        text = textwrap.dedent(stmt).strip() if pretty else " ".join(stmt.split())
        out.append(text.replace("{AUTOID}", dialect.autoid).replace("{JSON}", dialect.json_type))
    return out


def postgres_rls() -> list[str]:
    """Supabase exposes public tables over PostgREST: enable row-level
    security with no policies, so only the owner / service role (the API's
    DATABASE_URL) can read or write these tables, never the anon key."""
    return [f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in TABLES]


def _index_names() -> list[str]:
    return [m.group(1) for stmt in TEMPLATE for m in [_INDEX_RE.search(stmt)] if m]


def _pg_relations(conn: Any) -> dict[str, bool]:
    """{table or index name: row security on?} in the current schema.

    Catalog reads only, so no table locks: safe while other processes write.
    """
    cur = conn.execute(
        "SELECT c.relname AS name, c.relrowsecurity AS rls FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relname = ANY(%s)",
        (list(TABLES) + _index_names(),),
    )
    out: dict[str, bool] = {}
    for row in cur.fetchall():
        name, rls = (row["name"], row["rls"]) if isinstance(row, dict) else (row[0], row[1])
        out[str(name)] = bool(rls)
    return out


def _pg_schema_current(conn: Any) -> bool:
    rels = _pg_relations(conn)
    if any(name not in rels for name in _index_names()):
        return False
    if any(not rels.get(t) for t in TABLES):
        return False  # missing, or row security still off
    cur = conn.execute("SELECT value FROM storage_meta WHERE key = %s", ("schema_version",))
    row = cur.fetchone()
    value = (row["value"] if isinstance(row, dict) else row[0]) if row is not None else None
    return value == str(SCHEMA_VERSION)


def ensure_schema(db: Any, conn: Any) -> None:
    """Idempotent CREATE ... IF NOT EXISTS on first connect."""
    stmts = render(db.dialect)
    now = datetime.now(timezone.utc).isoformat()
    if db.is_postgres:
        # Every process runs this on its first connection. Re-running the DDL
        # on a live database is not free on Postgres: ALTER TABLE ... ENABLE
        # ROW LEVEL SECURITY takes an ACCESS EXCLUSIVE lock and CREATE INDEX IF
        # NOT EXISTS a SHARE lock even when there is nothing to do, so a
        # replica starting up stalled (and could deadlock) the money writes of
        # the processes already running. Check the catalog first, lock-free.
        if _pg_schema_current(conn):
            return
        conn.execute("BEGIN")
        try:
            # One process at a time on a fresh database.
            conn.execute("SELECT pg_advisory_xact_lock(724100231)")
            # Never queue behind long transactions holding everyone else up.
            conn.execute("SET LOCAL lock_timeout = '15s'")
            for s in stmts:
                conn.execute(s)
            rels = _pg_relations(conn)
            for t, stmt in zip(TABLES, postgres_rls()):
                if not rels.get(t):
                    conn.execute(stmt)
            conn.execute(
                "INSERT INTO storage_meta (key, value, updated_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                ("schema_version", str(SCHEMA_VERSION), now),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        for s in stmts:
            conn.execute(s)
        conn.execute(
            "INSERT INTO storage_meta (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO NOTHING",
            ("schema_version", str(SCHEMA_VERSION), now),
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def postgres_migration_sql() -> str:
    """The Supabase migration body (kept in sync by a test)."""
    from gaming.src.stack.agentic.db.engine import PostgresDialect

    head = (
        "-- Boardman agentic ledger v2: ledger, matches, spectator books, LP pools,\n"
        "-- settlement journal, match leases, on-chain tx/nonce records,\n"
        "-- tournament payouts and the house log.\n"
        "-- Generated from src/stack/agentic/db/schema.py — edit there, then\n"
        "-- regenerate: python -m gaming.src.stack.agentic.db.schema > <this file>\n"
        "-- Money columns are integer micro-USDC (6 decimals).\n\n"
        "BEGIN;\n\n"
    )
    body = ";\n\n".join(render(PostgresDialect(), pretty=True)) + ";\n\n"
    body += "-- Never reachable with the anon/authenticated keys.\n"
    body += ";\n".join(postgres_rls()) + ";\n\n"
    tail = (
        "INSERT INTO storage_meta (key, value, updated_at)\n"
        f"VALUES ('schema_version', '{SCHEMA_VERSION}', now()::text)\n"
        "ON CONFLICT (key) DO NOTHING;\n\n"
        "COMMIT;\n"
    )
    return head + body + tail


if __name__ == "__main__":  # pragma: no cover
    print(postgres_migration_sql(), end="")
