"""Behaviour that differs between SQLite and Postgres, pinned on both.

Runs on SQLite by default; with BOARDMAN_TEST_DATABASE_URL the same
assertions run on a real Postgres (the ones only meaningful there skip on
SQLite).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db import get_db, transaction
from gaming.src.stack.agentic.db.tables import BOOKS, MATCHES, hot_matches

W = "0xd1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1d1"
W2 = "0xd2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2"


def _pg_only():
    if not get_db().is_postgres:
        pytest.skip("Postgres-only behaviour (set BOARDMAN_TEST_DATABASE_URL)")


def test_money_columns_hold_more_than_32_bits_of_micro_usdc():
    """INTEGER would cap a balance at ~2147 USDC; every money column is BIGINT."""
    big = Decimal("9000000000.123456")  # 9e15 micro
    ledger.credit(W, big, reason="whale")
    ledger.credit(W2, Decimal("5000"), reason="fund")
    ledger.open_escrow("agm_big", agent_a_wallet=W, agent_b_wallet=W2, stake_usdc=Decimal("3000"))
    ledger.lock("agm_big", W)
    ledger.lock("agm_big", W2)
    ledger.settle("agm_big", W, result="win")
    assert ledger.balance(W) > big
    assert ledger.total_micro() == ledger.to_micro(big) + ledger.to_micro(Decimal("5000"))
    t = ledger.txs(wallet=W)[0]
    assert t["amount"] == "9000000000.123456"


def test_database_error_inside_a_savepoint_leaves_the_outer_transaction_usable():
    """On Postgres any failed statement poisons the transaction unless it ran
    inside a savepoint; a nested transaction() is one."""
    ledger.credit(W, Decimal("1"), reason="fund")
    with transaction() as tx:
        ledger.credit(W2, Decimal("2"), reason="outer")
        with pytest.raises(Exception):
            with transaction():
                tx.execute("UPDATE ledger_balances SET balance_micro = -5 WHERE wallet = ?", (W,))
        ledger.credit(W2, Decimal("3"), reason="after")
    assert ledger.balance(W) == Decimal("1")
    assert ledger.balance(W2) == Decimal("5")


def test_documents_survive_jsonb():
    """JSONB rejects NUL characters and has no NaN; key order is not kept."""
    doc = {
        "match_id": "agm_doc",
        "status": "open",
        "name": "nul\x00inside",
        "edge": float("nan"),
        "z": 1,
        "a": [1.5, {"k\x00": "v"}],
        "big": 2**62,
    }
    MATCHES.put("agm_doc", doc)
    got = MATCHES.get("agm_doc")
    assert got["status"] == "open" and got["z"] == 1 and got["big"] == 2**62
    assert got["a"][0] == 1.5
    assert "inside" in got["name"]
    assert got["edge"] is None or got["edge"] != got["edge"]  # null on Postgres, NaN on SQLite


def test_settled_records_without_a_date_sort_last_on_both_backends():
    for i, stamp in enumerate(["2026-01-01T00:00:00+00:00", None, "2026-03-01T00:00:00+00:00"]):
        MATCHES.put(f"agm_h{i}", {"match_id": f"agm_h{i}", "status": "settled", "settled_at": stamp})
    newest = [m["match_id"] for m in MATCHES.query(
        "status = ?", ("settled",), order_by="settled_at DESC NULLS LAST", limit=2
    )]
    assert newest == ["agm_h2", "agm_h0"]
    hot = [m["match_id"] for m in hot_matches()]
    assert hot[:2] == ["agm_h2", "agm_h0"]
    BOOKS.put("bk", {"match_id": "bk", "status": "settled"})
    assert BOOKS.hot(1, settled_order="settled_at DESC NULLS LAST")


def test_recent_txs_come_back_oldest_first():
    for i in range(5):
        ledger.credit(W, Decimal(i + 1), reason=f"r{i}")
    assert [t["reason"] for t in ledger.txs(wallet=W, limit=3)] == ["r2", "r3", "r4"]


def test_a_dropped_connection_is_replaced_not_kept_broken():
    """Supabase's pooler or a failover can kill a session. The thread's next
    transaction must reconnect instead of failing forever."""
    _pg_only()
    ledger.credit(W, Decimal("1"), reason="before")
    db = get_db()
    pid = db.connection().info.backend_pid
    import psycopg  # type: ignore

    with psycopg.connect(db.url, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
    ledger.credit(W, Decimal("1"), reason="after")  # first use after the kill
    assert ledger.balance(W) == Decimal("2")
    assert db.connection().info.backend_pid != pid


def test_closing_the_store_never_pulls_a_connection_from_under_a_busy_thread():
    """reset_databases()/eviction used to close every thread's connection,
    including one mid-transaction (an sqlite3 handle closed mid-query can
    segfault). A busy thread keeps its connection until it is done; its next
    call is refused and closes it."""
    import threading

    from gaming.src.stack.agentic.db import StorageError, engine

    db = get_db()
    ready, go = threading.Event(), threading.Event()
    box: dict = {}

    def worker() -> None:
        with transaction() as tx:
            tx.scalar("SELECT 1 AS x", ())
            ready.set()
            go.wait(10)
            box["after"] = tx.scalar("SELECT 2 AS x", ())
        try:
            db.connection()
        except StorageError:
            box["refused"] = True

    t = threading.Thread(target=worker)
    t.start()
    assert ready.wait(10)
    engine.reset_databases()
    go.set()
    t.join(20)
    assert box == {"after": 2, "refused": True}
