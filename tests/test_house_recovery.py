"""Crash recovery: a table whose worker died never stays stuck.

The bug: kill -9 the house session during a table's bet window and the table
sat "locked" with no result forever — both stakes locked, every pair with
either agent refused as "already live", rematch handing the dead table back
as if it were live, and the session retrying every 2s.

Here a "crash" is simulated in-process (the dead process's lease row stays,
its in-memory state is dropped, a new process id takes over) and, in the last
tests, by really SIGKILLing a spawned child.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import signal
import time
from decimal import Decimal
from typing import Any

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic import matches as matches_mod
from gaming.src.stack.agentic.db import journal, leases, transaction
from gaming.src.stack.agentic.db.tables import MATCHES

RAJA = "agent_raja_kia_alekhine"
NERO = "agent_nero_sicilian_french"
SHEILA = "agent_sheila_anaconda"


class SimulatedCrash(BaseException):
    """The process dies (BaseException: no `except Exception` swallows it)."""


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_BET_WINDOW_SEC", "0")
    monkeypatch.setenv("BOARDMAN_MAX_PLIES", "20")  # short games
    monkeypatch.setenv("BOARDMAN_RECOVERY_GRACE_SEC", "0")
    monkeypatch.setenv("BOARDMAN_RECOVERY_OPEN_GRACE_SEC", "0")
    monkeypatch.setattr(matches_mod, "_notify_spectator_outcomes", lambda *a, **k: None)
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    _reset_process(monkeypatch, "house-session-1")
    yield
    _reset_process(monkeypatch, "teardown")


def _reset_process(monkeypatch, owner: str) -> None:
    """A brand-new process: no leases in memory, no workers, a new owner id."""
    from gaming.src.stack.agentic import house
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    leases.forget_local_state()
    with house._floor_lock:
        house._workers.clear()
    with matches_mod._RUNNING_LOCK:
        matches_mod._RUNNING.clear()
    get_registry.cache_clear()
    get_match_service.cache_clear()
    monkeypatch.setattr(leases, "process_owner", lambda: owner)


def _expire(mid: str) -> None:
    with transaction() as tx:
        tx.execute("UPDATE match_leases SET expires_at_ms = 0 WHERE match_id = ?", (mid,))


def _agents() -> dict[str, dict[str, Any]]:
    from gaming.src.stack.agentic.registry import get_registry

    return {a["agent_id"]: a for a in get_registry().ensure_demo_agents()}


def _locked_table(monkeypatch, *, bets: bool = True, stake: float = 1, pre: dict | None = None) -> str:
    """Open + lock Raja vs Nero as the house session does, under its lease.

    Returns with the lease still held — the caller then "kills" the process.
    ``pre`` receives both agents' balances just before the lock.
    """
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.house import get_house

    _agents()
    rt = get_house()
    mid = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=stake, white_agent_id=RAJA)["match_id"]
    if pre is not None:
        pre.update({w: ledger.balance(w) for w in _wallets(mid)})
    leases.acquire(mid)  # rematch(wait=True) holds it across lock -> bet window
    rt.lock(mid)
    if bets:
        book = SpectatorBook()
        book.ensure_from_match(MATCHES.get(mid))
        book.place_bet(mid, bettor_id="fan_a", side="a", amount_usdc=Decimal("1.5"))
        book.place_bet(mid, bettor_id="fan_b", side="b", amount_usdc=Decimal("0.75"))
        book.place_bet(mid, bettor_id="fan_d", side="draw", amount_usdc=Decimal("0.5"))
    return mid


def _crash(monkeypatch, owner: str = "house-session-2") -> None:
    """kill -9: the lease row stays behind (still fresh), memory is gone."""
    _reset_process(monkeypatch, owner)


def _wallets(mid: str) -> tuple[str, str]:
    m = MATCHES.get(mid)
    return m["agent_a_wallet"].lower(), m["agent_b_wallet"].lower()


def _escrow_moves(mid: str) -> list[str]:
    return [t["type"] for t in ledger.txs(ref=mid) if t.get("type") in {"escrow_settle", "escrow_refund_draw"}]


# ── the reported bug, end to end (in-process) ───────────────────────────────


def test_kill_in_bet_window_then_restart_resumes_and_settles_exactly_once(monkeypatch):
    from gaming.src.stack.agentic import recovery
    from gaming.src.stack.agentic.house import get_house

    mid = _locked_table(monkeypatch)
    _crash(monkeypatch)
    assert MATCHES.get(mid)["status"] == "locked"

    # The dead process's lease is still fresh: nobody may touch the table yet.
    plan = recovery.plan_table(MATCHES.get(mid))
    assert plan.action == "skip" and "lease held by house-session-1" in plan.why
    assert recovery.recover_interrupted(resume_inline=True) == []
    with pytest.raises(ValueError, match="already live"):
        get_house().open_match(agent_a_id=RAJA, agent_b_id=SHEILA, stake_usdc=1)

    _expire(mid)  # BOARDMAN_LEASE_TTL_SEC later
    out = recovery.recover_interrupted(resume_inline=True)
    assert [(r["match_id"], r["action"]) for r in out] == [(mid, "resume")]
    rec = MATCHES.get(mid)
    assert rec["status"] == "settled" and rec["result"]
    assert rec["escrow"]["status"] == "settled"
    assert len(_escrow_moves(mid)) == 1
    assert leases.state(mid) is None  # released after the worker finished

    # Another restart / sweep: nothing left to do, no money moves.
    before = ledger.balances()
    _crash(monkeypatch, "house-session-3")
    assert recovery.recover_interrupted(resume_inline=True) == []
    assert ledger.balances() == before
    assert len(_escrow_moves(mid)) == 1
    # Both agents are free again.
    get_house().open_match(agent_a_id=RAJA, agent_b_id=SHEILA, stake_usdc=1)


def test_unreplayable_interrupted_game_is_refunded_exactly_once(monkeypatch):
    from gaming.src.stack.agentic import recovery
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.store import load_json

    pre: dict[str, Decimal] = {}
    mid = _locked_table(monkeypatch, pre=pre)
    wa, wb = _wallets(mid)
    assert ledger.balance(wa) < pre[wa]  # stake (and seeds) are locked
    # Died mid-game; the stored moves no longer replay (corrupt record).
    get_match_service()._set(mid, status="playing", moves=[{"ply": 1, "uci": "e2e5", "san": "?"}])
    _crash(monkeypatch)
    _expire(mid)

    plan = recovery.plan_table(MATCHES.get(mid))
    assert plan.action == "abort" and "do not replay" in plan.why
    out = recovery.recover_interrupted()
    assert [(r["match_id"], r["action"], r.get("final_status")) for r in out] == [(mid, "abort", "cancelled")]

    rec = MATCHES.get(mid)
    assert rec["status"] == "cancelled" and rec["abort_reason"] == "interrupted"
    assert rec["result"] is None
    # Both agents whole again: stake and every seed back.
    assert {w: ledger.balance(w) for w in (wa, wb)} == pre
    assert _escrow_moves(mid) == ["escrow_refund_draw"]
    book = SpectatorBook().get(mid)
    assert book["status"] == "void"
    assert sorted((r["bettor_id"], r["amount"]) for r in book["payouts"]["refunds"]) == [
        ("fan_a", "1.5"), ("fan_b", "0.75"), ("fan_d", "0.5"),
    ]
    assert ledger.balance("fan_a") == Decimal("1.5")
    adjust = load_json("play_adjust.json", {"profiles": {}})["profiles"]
    assert Decimal(adjust["fan_b"]["adjust"]) == Decimal("0.75")
    assert {s["step"] for s in journal.steps(mid)} >= {"abort:escrow", "abort:spectator", "abort:finalize"}

    # Never twice: another sweep, a direct abort, an ops abort.
    snap = ledger.balances()
    _crash(monkeypatch, "house-session-3")
    assert recovery.recover_interrupted() == []
    assert get_house().abort_never_started(mid)["already"] is True
    assert ledger.balances() == snap
    assert Decimal(load_json("play_adjust.json", {"profiles": {}})["profiles"]["fan_b"]["adjust"]) == Decimal("0.75")


def _abort_money_state(mid: str) -> dict[str, Any]:
    from collections import Counter

    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.store import load_json

    rec = MATCHES.get(mid) or {}
    return {
        "balances": {w: Decimal(v) for w, v in ledger.balances().items()},
        "moves": Counter(
            (t.get("type"), t.get("wallet"), t.get("reason"), str(Decimal(str(t.get("amount") or "0"))))
            for t in ledger.snapshot()["txs"]
        ),
        "adjust": {
            pid: Decimal(r.get("adjust") or "0")
            for pid, r in (load_json("play_adjust.json", {"profiles": {}}).get("profiles") or {}).items()
        },
        "book": json.dumps((SpectatorBook().get(mid) or {}).get("payouts"), sort_keys=True),
        "status": rec.get("status"),
        "steps": sorted(r["step"] for r in journal.steps(mid)),
    }


def test_refund_crash_at_every_step_then_recovery_refunds_exactly_once(tmp_path, monkeypatch):
    from gaming.src.stack.agentic import recovery
    from gaming.src.stack.agentic.house import abort_table

    def _fresh(name: str) -> str:
        monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path / name))
        _reset_process(monkeypatch, "house-session-1")
        mid = _locked_table(monkeypatch)
        leases.release(mid)
        return mid

    seen: list[str] = []
    mid = _fresh("reference")
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", seen.append)
    abort_table(mid, reason="interrupted")
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    ref = _abort_money_state(mid)
    assert ref["status"] == "cancelled"
    assert {"aborting", "abort:escrow", "abort:spectator", "abort:finalize"} <= set(seen)
    assert any(s.startswith("abort:play_adjust:") for s in seen)

    for i, crash_at in enumerate(seen):
        mid = _fresh(f"crash_{i}")

        def _die(step: str, crash_at: str = crash_at) -> None:
            if step == crash_at:
                raise SimulatedCrash(step)

        monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", _die)
        real_release = leases.release
        leases.release = lambda *a, **k: None  # the dead never release
        try:
            with pytest.raises(SimulatedCrash):
                abort_table(mid, reason="interrupted")
        finally:
            leases.release = real_release
        monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
        if crash_at != "abort:finalize":
            assert MATCHES.get(mid)["status"] == "aborting", crash_at

        _crash(monkeypatch)
        assert recovery.plan_table(MATCHES.get(mid)).action in {"skip"}  # lease still fresh
        _expire(mid)
        recovery.recover_interrupted()
        got = _abort_money_state(mid)
        for key in ref:
            assert got[key] == ref[key], f"crash after {crash_at!r}: {key} differs"


def test_live_lease_is_never_taken_and_lease_less_tables_get_a_grace_period(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from gaming.src.stack.agentic import recovery

    mid = _locked_table(monkeypatch, bets=False)
    leases.release(mid)  # API-style lock: no lease at all
    monkeypatch.setenv("BOARDMAN_RECOVERY_GRACE_SEC", "120")
    m = MATCHES.get(mid)
    assert recovery.plan_table(m).action == "skip"  # touched just now
    later = datetime.now(timezone.utc) + timedelta(seconds=121)
    assert recovery.plan_table(m, now=later).action == "resume"

    # A process that is alive keeps renewing: never taken over, however old.
    monkeypatch.setattr(leases, "process_owner", lambda: "api-replica")
    leases.try_acquire(mid)
    monkeypatch.setattr(leases, "process_owner", lambda: "house-session-1")
    plan = recovery.plan_table(m, now=later)
    assert plan.action == "skip" and "api-replica" in plan.why


# ── stale-pair release, rematch handoff, backoff ────────────────────────────


def test_release_stale_pair_frees_a_stuck_table_holding_either_agent(monkeypatch):
    from gaming.src.stack.agentic.house import get_house

    _agents()
    rt = get_house()
    # Raja–Nero died while its stakes were still being locked.
    stuck = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=1)["match_id"]
    with pytest.raises(ValueError, match="already live"):
        rt.open_match(agent_a_id=RAJA, agent_b_id=SHEILA, stake_usdc=1)

    # A live owner still holds it: release must leave it alone.
    monkeypatch.setattr(leases, "process_owner", lambda: "api-replica")
    leases.try_acquire(stuck)
    monkeypatch.setattr(leases, "process_owner", lambda: "house-session-1")
    assert rt.release_stale_pair(RAJA, SHEILA) == []
    assert MATCHES.get(stuck)["status"] == "open"

    _expire(stuck)
    released = rt.release_stale_pair(RAJA, SHEILA)  # Raja–Sheila frees Raja–Nero
    assert [(r["match_id"], r["action"]) for r in released] == [(stuck, "abort")]
    assert MATCHES.get(stuck)["status"] == "cancelled"
    rt.open_match(agent_a_id=RAJA, agent_b_id=SHEILA, stake_usdc=1)


class _RecordingPool:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple]] = []

    def submit(self, fn, *args, **kwargs):
        from concurrent.futures import Future

        self.calls.append((fn, args))
        return Future()


def test_rematch_resumes_a_dead_table_instead_of_handing_it_back(monkeypatch):
    from gaming.src.stack.agentic import house

    pool = _RecordingPool()
    monkeypatch.setattr(house, "_executor", lambda: pool)
    mid = _locked_table(monkeypatch, bets=False)
    _crash(monkeypatch)
    _expire(mid)

    out = house.get_house().rematch(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=1, wait=False)
    assert out["attached"] is True and out["match_id"] == mid
    # Handed back only because THIS process now drives it under a fresh lease.
    assert [fn for fn, _ in pool.calls] == [house._lock_and_run]
    assert leases.active_holder(mid) == "house-session-2"
    assert mid in house._workers
    leases.release(mid)


def test_retry_backoff_is_exponential_and_capped(monkeypatch):
    from gaming.src.stack.agentic.recovery import retry_delay

    assert [retry_delay(n) for n in range(1, 10)] == [2, 4, 8, 16, 32, 64, 120, 120, 120]
    monkeypatch.setenv("BOARDMAN_HOUSE_RETRY_BASE_SEC", "5")
    monkeypatch.setenv("BOARDMAN_HOUSE_RETRY_CAP_SEC", "30")
    assert [retry_delay(n) for n in range(1, 6)] == [5, 10, 20, 30, 30]
    assert retry_delay(10_000) == 30  # no overflow


def test_recovery_thread_sweeps_periodically(monkeypatch):
    from gaming.src.stack.agentic import recovery

    calls: list[float] = []
    monkeypatch.setattr(recovery, "recover_interrupted", lambda **k: calls.append(time.monotonic()) or [])
    t = recovery.start_recovery_thread(every=0.05)
    assert recovery.start_recovery_thread(every=0.05) is t  # once per process
    deadline = time.monotonic() + 5
    while len(calls) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    recovery.stop_recovery_thread()
    assert len(calls) >= 2


def test_admin_script_lists_then_recovers(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "recover_interrupted_tables.py"
    spec = importlib.util.spec_from_file_location("recover_interrupted_tables", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mid = _locked_table(monkeypatch, bets=False)
    _crash(monkeypatch)
    assert mod.main([], bootstrap=False) == 0
    out = capsys.readouterr().out
    assert mid in out and "skip" in out and "lease held" in out  # dry run, live lease

    _expire(mid)
    assert mod.main(["--match", mid, "--refund"], bootstrap=False) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "abort" in out
    assert MATCHES.get(mid)["status"] == "locked"  # dry run changed nothing

    assert mod.main(["--match", mid, "--refund", "--apply"], bootstrap=False) == 0
    assert "cancelled" in capsys.readouterr().out
    assert MATCHES.get(mid)["status"] == "cancelled"


# ── real processes: SIGKILL a spawned child ─────────────────────────────────


def _spawn(target, *args) -> int:
    ctx = mp.get_context("spawn")  # never fork: see tests/_proc_helpers.py
    p = ctx.Process(target=target, args=args, daemon=True)
    p.start()
    p.join(120)
    if p.is_alive():
        p.kill()
        pytest.fail("child hung")
    return p.exitcode


def test_sigkilled_session_in_bet_window_is_recovered(tmp_path, monkeypatch):
    from gaming.src.stack.agentic import recovery
    from gaming.src.stack.agentic.house import get_house
    from tests._proc_helpers import proc_lock_then_die

    _agents()
    mid = get_house().open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=1, white_agent_id=RAJA)["match_id"]
    assert _spawn(proc_lock_then_die, str(tmp_path), mid) == -signal.SIGKILL

    _reset_process(monkeypatch, "house-session-restarted")
    assert MATCHES.get(mid)["status"] == "locked"
    holder = leases.active_holder(mid)
    assert holder and holder != "house-session-restarted"  # the dead child's
    assert recovery.recover_interrupted(resume_inline=True) == []
    _expire(mid)
    out = recovery.recover_interrupted(resume_inline=True)
    assert [(r["match_id"], r["action"], r.get("final_status")) for r in out] == [(mid, "resume", "settled")]
    assert len(_escrow_moves(mid)) == 1


@pytest.mark.parametrize("crash_step", ["escrow", "spectator_settle"])
def test_sigkilled_child_mid_settlement_is_finished_exactly_once(tmp_path, monkeypatch, crash_step):
    from tests._proc_helpers import proc_settle_then_die
    from tests.test_settlement_journal import _money_state, _scenario

    from gaming.src.stack.agentic import recovery
    from gaming.src.stack.agentic.matches import get_match_service

    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path / "reference"))
    _reset_process(monkeypatch, "reference")
    mid, result = _scenario("win")
    get_match_service().settle_result(mid, result)
    ref = _money_state(mid)

    data = tmp_path / "killed"
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(data))
    _reset_process(monkeypatch, "parent")
    mid, result = _scenario("win")
    assert _spawn(proc_settle_then_die, str(data), mid, result, crash_step) == -signal.SIGKILL

    _reset_process(monkeypatch, "house-session-restarted")
    assert MATCHES.get(mid)["status"] == "settling"
    assert recovery.recover_interrupted(resume_inline=True) == []  # child's lease still fresh
    _expire(mid)
    out = recovery.recover_interrupted(resume_inline=True)
    assert [(r["action"], r.get("final_status")) for r in out] == [("resume_settlement", "settled")]
    got = _money_state(mid)
    for key in ("balances", "moves", "pools", "book_status", "book_payouts", "adjust", "match_status", "escrow_result", "steps"):
        assert got[key] == ref[key], f"kill after {crash_step!r}: {key} differs"
