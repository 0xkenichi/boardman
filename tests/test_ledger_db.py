"""Database-backed ledger: exact micro-USDC, atomic balance changes, no lost writes."""
from __future__ import annotations

import multiprocessing as mp
import os
import threading
from decimal import Decimal

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db import get_db, transaction
from gaming.src.stack.agentic.db.money import from_micro, to_micro

W_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
W_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_micro_roundtrip_is_exact():
    assert to_micro("58.6") == 58_600_000
    assert to_micro(Decimal("0.000001")) == 1
    assert str(from_micro(58_600_000)) == "58.6"
    assert str(from_micro(100_000_000)) == "100"
    assert str(from_micro(1)) == "0.000001"
    # half-even at the 7th decimal, never float drift
    assert to_micro("0.0000005") == 0
    assert to_micro("0.0000015") == 2
    assert to_micro(0.1) == 100_000


def test_credit_debit_and_snapshot_shape():
    ledger.credit(W_A, Decimal("10.5"), reason="fund", ref="t")
    tx = ledger.debit(W_A, Decimal("0.25"), reason="bet", ref="t")
    assert tx["balance_after"] == "10.25"
    assert ledger.balance(W_A) == Decimal("10.25")
    snap = ledger.snapshot()
    assert snap["balances"][W_A.lower()] == "10.25"
    assert [t["type"] for t in snap["txs"]] == ["credit", "debit"]
    assert set(snap["txs"][0]) == {"ts", "type", "wallet", "amount", "reason", "ref", "balance_after"}


def test_debit_refuses_overdraft_and_leaves_balance():
    ledger.credit(W_A, Decimal("1"), reason="fund")
    with pytest.raises(ValueError, match="insufficient balance"):
        ledger.debit(W_A, Decimal("1.000001"), reason="x")
    assert ledger.balance(W_A) == Decimal("1")
    with pytest.raises(ValueError):
        ledger.debit(W_A, Decimal("0"), reason="x")


def test_database_check_constraint_blocks_negative_balance():
    ledger.credit(W_A, Decimal("1"), reason="fund")
    with pytest.raises(Exception):
        with transaction() as tx:
            tx.execute("UPDATE ledger_balances SET balance_micro = -1 WHERE wallet = ?", (W_A.lower(),))
    assert ledger.balance(W_A) == Decimal("1")


def test_nested_failure_rolls_back_only_inner_savepoint():
    with transaction():
        ledger.credit(W_A, Decimal("5"), reason="outer")
        with pytest.raises(ValueError):
            with transaction():
                ledger.credit(W_B, Decimal("1"), reason="inner")
                raise ValueError("boom")
    assert ledger.balance(W_A) == Decimal("5")
    assert ledger.balance(W_B) == Decimal("0")


def test_outer_failure_rolls_back_everything():
    with pytest.raises(RuntimeError):
        with transaction():
            ledger.credit(W_A, Decimal("5"), reason="outer")
            ledger.credit(W_B, Decimal("5"), reason="outer")
            raise RuntimeError("crash before commit")
    assert ledger.balance(W_A) == 0 and ledger.balance(W_B) == 0
    assert ledger.snapshot()["txs"] == []


def test_escrow_lock_settle_win_and_idempotent():
    ledger.credit(W_A, Decimal("50"), reason="fund")
    ledger.credit(W_B, Decimal("50"), reason="fund")
    ledger.open_escrow("agm_x1", agent_a_wallet=W_A, agent_b_wallet=W_B, stake_usdc=Decimal("10"))
    ledger.lock("agm_x1", W_A)
    ledger.lock("agm_x1", W_A)  # idempotent
    ledger.lock("agm_x1", W_B)
    assert ledger.balance(W_A) == Decimal("40")
    esc = ledger.settle("agm_x1", W_A, result="win")
    again = ledger.settle("agm_x1", W_A, result="win")
    assert Decimal(esc["payout"]) == Decimal(again["payout"]) == Decimal("18.6")
    assert ledger.balance(W_A) == Decimal("58.6")
    assert ledger.balance(ledger.TREASURY_WALLET) == Decimal("1.4")
    with pytest.raises(ValueError, match="conflicting"):
        ledger.settle("agm_x1", W_A, result="draw")
    assert ledger.balance(W_A) == Decimal("58.6")


def test_lock_without_funds_is_refused_atomically():
    ledger.credit(W_A, Decimal("5"), reason="fund")
    ledger.open_escrow("agm_x2", agent_a_wallet=W_A, agent_b_wallet=W_B, stake_usdc=Decimal("10"))
    with pytest.raises(ValueError, match="insufficient USDC for lock"):
        ledger.lock("agm_x2", W_A)
    assert ledger.get_escrow("agm_x2")["locked_a"] is False
    assert ledger.balance(W_A) == Decimal("5")


def test_threads_do_not_lose_writes():
    ledger.credit(W_A, Decimal("0"), reason="init")

    def worker():
        for _ in range(50):
            ledger.credit(W_A, Decimal("0.01"), reason="tick")

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert ledger.balance(W_A) == Decimal("4.00")


def _proc_credit(data_dir: str, n: int) -> None:
    os.environ["BOARDMAN_AGENTIC_DATA"] = data_dir
    from gaming.src.stack.agentic import ledger as L

    for _ in range(n):
        L.credit(W_B, Decimal("0.5"), reason="proc")
        try:
            L.debit(W_B, Decimal("0.25"), reason="proc")
        except ValueError:
            pass


def test_two_processes_share_one_ledger(tmp_path, monkeypatch):
    """The API and the house session are separate processes — both must count."""
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    get_db()  # create schema first
    ctx = mp.get_context("fork")
    procs = [ctx.Process(target=_proc_credit, args=(str(tmp_path), 40)) for _ in range(3)]
    for p in procs:
        p.start()
    _proc_credit(str(tmp_path), 40)
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    # 4 writers x 40 x (0.5 - 0.25)
    assert ledger.balance(W_B) == Decimal("40")
    assert len([t for t in ledger.txs(wallet=W_B)]) == 4 * 40 * 2


def test_ensure_funded_tops_up_once():
    ledger.ensure_funded(W_A, Decimal("100"))
    ledger.ensure_funded(W_A, Decimal("100"))
    assert ledger.balance(W_A) == Decimal("100")
    assert len(ledger.txs(wallet=W_A)) == 1
