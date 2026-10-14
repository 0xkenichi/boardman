"""The Supabase migration really applies, and builds what the app builds.

tests/test_storage_engine.py checks the migration file is the text
schema.py renders. This runs it: on Postgres (BOARDMAN_TEST_DATABASE_URL)
the file is applied to an empty schema and the catalog is compared with a
schema the app created itself on first connect — columns, types, defaults,
constraints, indexes, row-level security. It also checks that row security
really shuts out a role that is neither owner nor BYPASSRLS (Supabase's
anon / authenticated), and that the app's startup sees a migrated database
as current and runs no DDL against it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db import engine, schema

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20261014120000_agentic_ledger.sql"


@pytest.fixture
def pg():
    if not engine.get_db().is_postgres:
        pytest.skip("needs Postgres (set BOARDMAN_TEST_DATABASE_URL)")
    import psycopg  # type: ignore

    return psycopg


def _store_url(monkeypatch, path: Path) -> str:
    """URL of the (empty) test schema that belongs to data dir ``path``."""
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(path))
    return engine.get_db().url


def _catalog(conn) -> dict:
    """Everything about this schema's tables that the app relies on."""
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    cols = q(
        "SELECT table_name, column_name, data_type, is_nullable, column_default, ordinal_position "
        "FROM information_schema.columns WHERE table_schema = current_schema() "
        "ORDER BY table_name, ordinal_position"
    )
    cons = q(
        "SELECT c.relname, k.contype, pg_get_constraintdef(k.oid) FROM pg_constraint k "
        "JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() ORDER BY 1, 2, 3"
    )
    idx = q(
        "SELECT tablename, indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = current_schema() ORDER BY 1, 2"
    )
    rls = q(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relkind = 'r' ORDER BY 1"
    )
    schema_name = conn.execute("SELECT current_schema()").fetchone()[0]
    strip = lambda s: re.sub(rf'\b"?{re.escape(schema_name)}"?\.', "", s or "")  # noqa: E731
    return {
        "columns": [tuple(strip(str(v)) if isinstance(v, str) else v for v in r) for r in cols],
        "constraints": [(r[0], r[1], r[2]) for r in cons],
        "indexes": [(r[0], r[1], strip(r[2])) for r in idx],
        "rls": [tuple(r) for r in rls],
    }


def test_migration_applies_cleanly_and_matches_the_app_schema(pg, monkeypatch, tmp_path):
    sql = MIGRATION.read_text()
    migrated_url = _store_url(monkeypatch, tmp_path / "migrated")
    with pg.connect(migrated_url, autocommit=True) as conn:
        conn.execute(sql)
        conn.execute(sql)  # idempotent: a re-run is a no-op, not an error
        migrated = _catalog(conn)
        assert conn.execute(
            "SELECT value FROM storage_meta WHERE key = 'schema_version'"
        ).fetchone()[0] == str(schema.SCHEMA_VERSION)

    app_url = _store_url(monkeypatch, tmp_path / "app")
    engine.get_db().connection()  # the app's own CREATE ... IF NOT EXISTS
    with pg.connect(app_url, autocommit=True) as conn:
        built = _catalog(conn)

    assert {r[0] for r in built["rls"]} == set(schema.TABLES)
    assert all(on for _t, on, _force in built["rls"]), "row-level security off somewhere"
    for key in ("columns", "constraints", "indexes", "rls"):
        assert migrated[key] == built[key], f"migration and app schema differ in {key}"
    money = {(r[0], r[1]): r[2] for r in built["columns"] if r[1].endswith("_micro")}
    assert money and set(money.values()) == {"bigint"}, money


def test_app_starts_on_a_migrated_database_without_ddl(pg, monkeypatch, tmp_path):
    url = _store_url(monkeypatch, tmp_path / "migrated")
    with pg.connect(url, autocommit=True) as conn:
        conn.execute(MIGRATION.read_text())
        assert schema._pg_schema_current(conn)
    ledger.credit("0xmig", 2, reason="x")  # the app on the migrated schema
    assert ledger.balance("0xmig") == 2


def test_row_level_security_shuts_out_the_api_keys(pg, monkeypatch, tmp_path, request):
    """No policies + RLS on: a role without BYPASSRLS sees no rows and can
    write none, even with table grants (what Supabase's anon role has)."""
    url = _store_url(monkeypatch, tmp_path / "rls")
    with pg.connect(url, autocommit=True) as conn:
        conn.execute(MIGRATION.read_text())
        conn.execute(
            "INSERT INTO ledger_balances (wallet, balance_micro, scale, updated_at) "
            "VALUES ('0xsecret', 5, 0, 'now')"
        )
        role = f"anon_{abs(hash(request.node.nodeid)) % 10**8}"
        sch = conn.execute("SELECT current_schema()").fetchone()[0]
        conn.execute(f'DROP ROLE IF EXISTS "{role}"')
        conn.execute(f'CREATE ROLE "{role}" NOLOGIN NOBYPASSRLS')
        try:
            conn.execute(f'GRANT USAGE ON SCHEMA "{sch}" TO "{role}"')
            conn.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{sch}" TO "{role}"')
            conn.execute(f'SET ROLE "{role}"')
            for t in schema.TABLES:
                assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
            assert conn.execute("UPDATE ledger_balances SET balance_micro = 0").rowcount == 0
            with pytest.raises(pg.errors.InsufficientPrivilege, match="row-level security"):
                conn.execute(
                    "INSERT INTO ledger_balances (wallet, balance_micro, scale, updated_at) "
                    "VALUES ('0xanon', 1, 0, 'now')"
                )
            conn.execute("RESET ROLE")
            assert conn.execute("SELECT balance_micro FROM ledger_balances").fetchone()[0] == 5
        finally:
            conn.execute("RESET ROLE")
            conn.execute(f'DROP OWNED BY "{role}"')
            conn.execute(f'DROP ROLE "{role}"')
