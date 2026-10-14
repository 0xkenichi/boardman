"""Many writers at once on the money paths.

On SQLite every write transaction takes the database write lock up front
(``BEGIN IMMEDIATE``), which hides most races. Postgres serializes only the
rows a statement actually locks, so the cases below are the ones that bite in
production: conditional debits under contention, and "read, nothing there,
insert" paths where ``SELECT ... FOR UPDATE`` has no row to lock. These run on
both backends; set BOARDMAN_TEST_DATABASE_URL to run them on Postgres.
"""
from __future__ import annotations

import gc
import threading
from decimal import Decimal
from typing import Any, Callable

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db import get_db, journal, leases, transaction
from gaming.src.stack.agentic.db.docs import DocTable
from gaming.src.stack.agentic.db.money import to_micro

W = "0xc0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0"
THREADS = 16


def _race(n: int, fn: Callable[[int], Any]) -> tuple[list[Any], list[BaseException]]:
    """Run ``fn(i)`` on ``n`` threads released together. Returns (results, errors)."""
    gate = threading.Barrier(n)
    results: list[Any] = [None] * n
    errors: list[BaseException] = []
    lock = threading.Lock()

    def run(i: int) -> None:
        gate.wait(timeout=30)
        try:
            results[i] = fn(i)
        except BaseException as exc:  # collected and asserted on below
            with lock:
                errors.append(exc)

    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(120)
        assert not t.is_alive(), "worker hung"
    return results, errors


def _min_balance_seen(stop: threading.Event, seen: list[int]) -> None:
    while not stop.is_set():
        with transaction(readonly=True) as tx:
            v = tx.scalar("SELECT MIN(balance_micro) AS m FROM ledger_balances", ())
        if v is not None:
            seen.append(int(v))


def test_debit_hammer_never_overdraws_and_lands_exactly():
    """32 threads x 10 debits of 0.07 against 10 USDC: exactly 142 succeed."""
    ledger.credit(W, Decimal("10"), reason="fund")
    amount = Decimal("0.07")
    stop, seen = threading.Event(), []
    watcher = threading.Thread(target=_min_balance_seen, args=(stop, seen))
    watcher.start()

    def debits(_i: int) -> tuple[int, int]:
        ok = refused = 0
        for _ in range(10):
            try:
                ledger.debit(W, amount, reason="hammer")
                ok += 1
            except ledger.InsufficientFunds:
                refused += 1
        return ok, refused

    try:
        results, errors = _race(32, debits)
    finally:
        stop.set()
        watcher.join(30)
    assert errors == []
    ok = sum(r[0] for r in results)
    assert ok == 142 and sum(r[1] for r in results) == 320 - 142
    assert ledger.balance(W) == Decimal("0.06")
    assert seen and min(seen) >= 0
    with transaction(readonly=True) as tx:
        afters = [int(r["b"]) for r in tx.all(
            "SELECT balance_after_micro AS b FROM ledger_txs WHERE wallet = ? AND type = 'debit'", (W,)
        )]
    assert len(afters) == 142 and min(afters) >= 0
    # Every successful debit saw a distinct balance: no two read the same row version.
    assert len(set(afters)) == 142


def test_mixed_credits_and_debits_balance_exactly():
    ledger.credit(W, Decimal("1"), reason="fund")

    def work(i: int) -> int:
        ok = 0
        for _ in range(15):
            if i % 2:
                ledger.credit(W, Decimal("0.010001"), reason="in")
            else:
                try:
                    ledger.debit(W, Decimal("0.03"), reason="out")
                    ok += 1
                except ledger.InsufficientFunds:
                    pass
        return ok

    results, errors = _race(THREADS, work)
    assert errors == []
    debited = sum(r for i, r in enumerate(results) if i % 2 == 0)
    credited = (THREADS // 2) * 15
    expect = Decimal("1") + credited * Decimal("0.010001") - debited * Decimal("0.03")
    assert ledger.balance(W) == expect
    assert ledger.total_micro() == to_micro(expect)


def test_concurrent_escrow_locks_spend_each_stake_once():
    """Both sides lock several escrows at once with only enough for some."""
    a, b = "0xa1" + "0" * 38, "0xb1" + "0" * 38
    ledger.credit(a, Decimal("25"), reason="fund")
    ledger.credit(b, Decimal("100"), reason="fund")
    for k in range(THREADS):
        ledger.open_escrow(f"agm_c{k}", agent_a_wallet=a, agent_b_wallet=b, stake_usdc=Decimal("5"))

    def lock(k: int) -> bool:
        try:
            ledger.lock(f"agm_c{k}", a)
            ledger.lock(f"agm_c{k}", a)  # idempotent re-lock
            return True
        except ledger.InsufficientFunds:
            return False

    results, errors = _race(THREADS, lock)
    assert errors == []
    assert sum(results) == 5
    assert ledger.balance(a) == Decimal("0")
    locked = [k for k in range(THREADS) if ledger.get_escrow(f"agm_c{k}")["locked_a"]]
    assert len(locked) == 5


# ── "read, nothing there, insert" under contention ───────────────────────────


def test_journal_step_is_recorded_once():
    def rec(i: int) -> bool:
        with transaction() as tx:
            return journal.record(tx, "agm_j", "escrow", {"by": i}, owner=f"w{i}")

    results, errors = _race(THREADS, rec)
    assert errors == []
    assert results.count(True) == 1
    assert [s["step"] for s in journal.steps("agm_j")] == ["escrow"]


def test_one_new_lease_one_owner():
    results, errors = _race(THREADS, lambda i: leases.try_acquire("agm_l", owner=f"proc-{i}"))
    assert errors == []
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert leases.state("agm_l")["owner"] == winners[0]["owner"]


def test_expired_lease_is_taken_over_once():
    assert leases.try_acquire("agm_t", owner="dead-proc")
    with transaction() as tx:
        tx.execute("UPDATE match_leases SET expires_at_ms = 0 WHERE match_id = ?", ("agm_t",))
    results, errors = _race(THREADS, lambda i: leases.try_acquire("agm_t", owner=f"proc-{i}"))
    assert errors == []
    winners = [r for r in results if r is not None]
    assert len(winners) == 1 and winners[0]["taken_over"] is True and winners[0]["epoch"] == 2


def test_escrow_opens_once():
    a, b = "0xa2" + "0" * 38, "0xb2" + "0" * 38

    def open_(i: int) -> dict:
        return ledger.open_escrow("agm_o", agent_a_wallet=a, agent_b_wallet=b, stake_usdc=Decimal("3"))

    results, errors = _race(THREADS, open_)
    assert errors == []
    assert len({r["created_at"] for r in results}) == 1
    assert [t["type"] for t in ledger.txs(ref="agm_o")] == ["escrow_open"]


def test_documents_created_once_and_counted_exactly():
    table = DocTable("lp_pools", "agent_id", root_key="pools", default_status="active")

    results, errors = _race(THREADS, lambda i: table.insert_if_absent("agent_x", {"agent_id": "agent_x", "by": i}))
    assert errors == []
    assert [created for _doc, created in results].count(True) == 1

    def bump(_i: int) -> None:
        for _ in range(5):
            table.upsert_with("agent_n", lambda cur: {"agent_id": "agent_n", "n": int((cur or {}).get("n", 0)) + 1})

    _results, errors = _race(THREADS, bump)
    assert errors == []
    assert table.get("agent_n")["n"] == THREADS * 5


def test_faucet_tops_up_once():
    results, errors = _race(THREADS, lambda i: ledger.ensure_funded(W, Decimal("100")))
    assert errors == []
    assert ledger.balance(W) == Decimal("100")
    assert len(ledger.txs(wallet=W)) == 1


def test_fee_sweep_slot_is_claimed_once():
    from gaming.src.stack.agentic import fee_sweep

    results, errors = _race(THREADS, lambda i: fee_sweep._claim_slot("fee_sweep:race", 3600))
    assert errors == []
    assert results.count(True) == 1


def test_tournament_place_is_claimed_once():
    from gaming.src.backend.services import tournament_money as tm

    def claim(i: int) -> str:
        key = tm.payout_idempotency_key("CUPX", 1, "alice", Decimal("10"))
        return tm._claim_place("CUPX", 1, "alice", Decimal("10"), key)[0]

    results, errors = _race(THREADS, claim)
    assert errors == []
    assert results.count("pay") == 1 and set(results) <= {"pay", "busy"}


# ── connections ──────────────────────────────────────────────────────────────


def test_threads_use_their_own_connections_and_close_them():
    db = get_db()
    conns: list[Any] = []

    def work(i: int) -> None:
        ledger.credit(W, Decimal("0.01"), reason="conn")
        conns.append(db.connection())

    _results, errors = _race(THREADS, work)
    assert errors == []
    assert len({id(c) for c in conns}) == THREADS
    conns.clear()
    assert ledger.balance(W) == Decimal("0.16")
    gc.collect()
    if db.is_postgres:
        with transaction(readonly=True) as tx:
            n = tx.scalar(
                "SELECT COUNT(*) AS n FROM pg_stat_activity "
                "WHERE application_name = current_setting('application_name')", ()
            )
        # Only this (main) thread's connection is left once the workers exit.
        assert int(n) == 1, f"{n} connections still open"


def test_tables_with_swapped_players_lock_without_deadlock():
    """Two tables with the same agents in opposite seats lock at once.

    Each lock transaction debits both players (stakes, then seeds). Taken in
    seat order, table 1 holds A's balance row and wants B's while table 2
    holds B's and wants A's: Postgres aborts one of them with a deadlock.
    """
    from gaming.src.stack.agentic.matches import lock_escrow_and_seeds

    a, b = "0xa3" + "0" * 38, "0xb3" + "0" * 38
    rounds = 40
    ledger.credit(a, Decimal("1000"), reason="fund")
    ledger.credit(b, Decimal("1000"), reason="fund")
    for r in range(rounds):
        ledger.open_escrow(f"agm_s{r}_0", agent_a_wallet=a, agent_b_wallet=b, stake_usdc=Decimal("1"))
        ledger.open_escrow(f"agm_s{r}_1", agent_a_wallet=b, agent_b_wallet=a, stake_usdc=Decimal("1"))

    def lock_rounds(i: int) -> None:
        for r in range(rounds):
            esc = ledger.get_escrow(f"agm_s{r}_{i}")
            lock_escrow_and_seeds(
                f"agm_s{r}_{i}", esc["agent_a_wallet"], esc["agent_b_wallet"],
                seed_a=Decimal("0.1"), seed_b=Decimal("0.1"), seed_draw=Decimal("0.05"),
            )

    _results, errors = _race(2, lock_rounds)
    assert errors == []
    left = Decimal("1000") - rounds * 2 * (Decimal("1") + Decimal("0.1") + Decimal("0.05"))
    assert ledger.balance(a) == ledger.balance(b) == left


def test_settlement_step_reruns_after_a_deadlock_rollback():
    """Postgres rolls back the loser of a deadlock whole; the step re-runs once."""
    from gaming.src.stack.agentic.matches import get_match_service

    class Deadlock(Exception):
        sqlstate = "40P01"

    calls: list[int] = []

    def step() -> dict:
        calls.append(1)
        ledger.credit(W, Decimal("1"), reason="step", ref="agm_r")
        if len(calls) == 1:
            raise Deadlock("deadlock detected")
        return {"ok": True}

    assert get_match_service()._step("agm_r", "escrow", step) == {"ok": True}
    assert len(calls) == 2
    assert ledger.balance(W) == Decimal("1")  # the rolled-back try left nothing
    assert journal.done("agm_r", "escrow")

    class Other(Exception):
        sqlstate = "23505"

    def bad() -> dict:
        raise Other("unique violation")

    with pytest.raises(Other):
        get_match_service()._step("agm_r", "creator_fee", bad)
