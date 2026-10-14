"""Storage engine: backend selection, dialect shim, schema sync, store hardening."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path

import pytest

from gaming.src.stack.agentic import store
from gaming.src.stack.agentic.db import engine, schema

ROOT = Path(__file__).resolve().parents[1]


def test_supabase_migration_matches_the_schema_module():
    files = sorted((ROOT / "supabase" / "migrations").glob("*_agentic_ledger.sql"))
    assert files, "missing supabase/migrations/<timestamp>_agentic_ledger.sql"
    assert files[-1].read_text() == schema.postgres_migration_sql(), (
        "regenerate: python -m gaming.src.stack.agentic.db.schema > " + files[-1].name
    )
    text = files[-1].read_text()
    for t in schema.TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {t} " in text
        assert f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" in text
    assert "balance_micro BIGINT NOT NULL DEFAULT 0 CHECK (balance_micro >= 0)" in text


def test_postgres_dialect_shim():
    d = engine.PostgresDialect()
    assert d.sql("SELECT x FROM t WHERE a = ? AND b = ?") == "SELECT x FROM t WHERE a = %s AND b = %s"
    assert d.for_update == " FOR UPDATE" and engine.SQLiteDialect.for_update == ""
    assert engine._pg_safe({"e": float("nan"), "l": [float("inf"), 1.5]}) == {"e": None, "l": [None, 1.5]}
    rendered = schema.render(d)
    assert any("BIGSERIAL PRIMARY KEY" in s for s in rendered)
    assert all("{JSON}" not in s and "{AUTOID}" not in s for s in rendered)


@pytest.mark.parametrize(
    "env,expect",
    [
        ({}, "sqlite"),
        ({"DATABASE_URL": "sqlite:///custom.sqlite3"}, "custom.sqlite3"),
        ({"DATABASE_URL": "postgresql://u@h/db"}, "pg:postgresql://u@h/db"),
        ({"DATABASE_URL": "postgres://u@h/db", "BOARDMAN_DATABASE_URL": "sqlite:///over.sqlite3"}, "over.sqlite3"),
    ],
)
def test_backend_is_selected_by_url(monkeypatch, env, expect):
    # The real selection logic, not the Postgres test-mode default (conftest).
    monkeypatch.setattr(engine, "database_url", getattr(engine.database_url, "__wrapped__", engine.database_url))
    for k in ("DATABASE_URL", "BOARDMAN_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    key, _spec = engine._resolve()
    assert expect in key


def test_unknown_url_scheme_is_refused(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://x")
    with pytest.raises(engine.StorageError):
        engine._resolve()


def test_postgres_without_psycopg_fails_loudly(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_psycopg(name, *a, **k):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ImportError("no psycopg")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_psycopg)
    db = engine.Database("pg:test", url="postgresql://nobody@127.0.0.1:1/x")
    with pytest.raises(engine.StorageError, match="psycopg"):
        db.connection()


@pytest.mark.sqlite_only("opens a read-only copy of the SQLite file")
def test_read_only_transaction_can_read_but_not_write():
    from gaming.src.stack.agentic import ledger

    ledger.credit("0xro", 1, reason="x")
    db = engine.get_db()
    ro = engine.Database("ro", sqlite_path=db.sqlite_path, readonly=True)
    ro._schema_ready = True
    with ro.transaction() as tx:
        assert tx.scalar("SELECT balance_micro FROM ledger_balances WHERE wallet = ?", ("0xro",)) == 1_000_000
        with pytest.raises(engine.StorageReadOnly):
            tx.execute("UPDATE ledger_balances SET balance_micro = 0")
    ro.close_all()


# ── store.py hardening ───────────────────────────────────────────────────────


def test_corrupt_json_is_copied_aside_not_silently_replaced():
    p = store.data_dir() / "agents.json"
    p.write_text('{"agents": {"a": ')
    assert store.load_json("agents.json", {"agents": {}}) == {"agents": {}}
    backups = list(store.data_dir().glob("agents.json.corrupt-*"))
    assert len(backups) == 1 and backups[0].read_text() == '{"agents": {"a": '


def test_failed_write_leaves_no_tmp(monkeypatch):
    def boom(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        store.save_json("agents.json", {"x": 1})
    assert list(store.data_dir().glob("*.tmp")) == []


def test_update_json_is_atomic_across_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    from tests._proc_helpers import bump

    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=bump, args=(str(tmp_path), 50), daemon=True) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0, f"writer exit={p.exitcode}"
    assert json.loads((tmp_path / "counter.json").read_text())["n"] == 200


def test_house_schedule_writers_do_not_drop_each_others_fields():
    from gaming.src.stack.agentic.house_schedule import read_schedule, write_schedule

    write_schedule(set_by="admin", cadence_sec=900)
    write_schedule(set_by="session", last_match_id="agm_1")
    cur = read_schedule()
    assert cur["cadence_sec"] == 900 and cur["last_match_id"] == "agm_1"


def test_db_backed_names_keep_their_legacy_shapes():
    from decimal import Decimal

    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.db.tables import MATCHES

    ledger.credit("0xshape", Decimal("2.50"), reason="x")
    MATCHES.put("agm_shape", {"match_id": "agm_shape", "status": "open"})
    led = store.load_json("ledger.json", {})
    assert set(led) == {"balances", "escrows", "txs"} and led["balances"]["0xshape"] == "2.50"
    m = store.load_json("matches.json", {"matches": {}})
    assert m["matches"]["agm_shape"]["status"] == "open"
    m["matches"]["agm_shape"]["clerk"] = "boardman_house"
    store.save_json("matches.json", m)
    assert MATCHES.get("agm_shape")["clerk"] == "boardman_house"
    with pytest.raises(RuntimeError, match="database-backed"):
        store.save_json("ledger.json", led)
    assert not (store.data_dir() / "matches.json").exists()
