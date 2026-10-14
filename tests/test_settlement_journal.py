"""Crash-at-every-step property test for match settlement.

For each step boundary of a real settlement (escrow, creator fee, LP profit
and loss, spectator payouts, play-wallet adjustments, notify, finalize) the
process "dies" right after that step commits. A different process then takes
over the expired lease and retries. The final money state must equal an
uncrashed reference run exactly: no double credit, nothing missing.
"""
from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic import matches as matches_mod
from gaming.src.stack.agentic.db import journal, leases, transaction
from gaming.src.stack.agentic.db.tables import MATCHES

RAJA = "agent_raja_kia_alekhine"
NERO = "agent_nero_sicilian_french"


class SimulatedCrash(BaseException):
    """The process dies (BaseException: no `except Exception` swallows it)."""


def _fresh_store(monkeypatch, path: Path) -> None:
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(path))
    get_registry.cache_clear()
    get_match_service.cache_clear()
    leases.forget_local_state()


def _scenario(kind: str) -> tuple[str, dict[str, Any]]:
    """A locked table with an LP book, fans on every side, ready to settle."""
    from gaming.src.stack.agentic.economy.lp import AgentLPPool
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    svc = get_match_service()
    m = svc.create_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=5, white_agent_id=RAJA)
    mid = m["match_id"]
    AgentLPPool().deposit(RAJA, lp_id="lp_alice", amount_usdc=Decimal("20"))
    AgentLPPool().deposit(NERO, lp_id="lp_bob", amount_usdc=Decimal("10"))
    svc.lock_both(mid)
    book = SpectatorBook()
    book.place_bet(mid, bettor_id="fan_a1", side="a", amount_usdc=Decimal("1.5"))
    book.place_bet(mid, bettor_id="fan_a2", side="a", amount_usdc=Decimal("0.75"))
    book.place_bet(mid, bettor_id="fan_b1", side="b", amount_usdc=Decimal("2"))
    book.place_bet(mid, bettor_id="fan_d1", side="draw", amount_usdc=Decimal("0.5"))
    if kind == "win":
        result = {"result": "white_win", "winner_agent_id": RAJA, "termination": "CHECKMATE", "moves": []}
    else:
        result = {"result": "draw", "winner_agent_id": None, "termination": "STALEMATE", "moves": []}
    return mid, result


def _money_state(mid: str) -> dict[str, Any]:
    from gaming.src.stack.agentic.economy.lp import AgentLPPool
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.store import load_json

    bals = {w: Decimal(v) for w, v in ledger.balances().items()}
    # Every movement, without timestamps or the (random) match id.
    moves = Counter(
        (t.get("type"), t.get("wallet"), t.get("reason"), str(Decimal(str(t.get("amount") or t.get("payout") or "0"))))
        for t in ledger.snapshot()["txs"]
    )
    pools = {
        aid: {k: Decimal(p["amount"]) for k, p in AgentLPPool().get_pool(aid)["positions"].items()}
        for aid in (RAJA, NERO)
    }
    book = SpectatorBook().get(mid) or {}
    adjust = {
        pid: Decimal(rec.get("adjust") or "0")
        for pid, rec in (load_json("play_adjust.json", {"profiles": {}}).get("profiles") or {}).items()
    }
    rec = MATCHES.get(mid) or {}
    return {
        "balances": bals,
        "moves": moves,
        "pools": pools,
        "book_status": book.get("status"),
        "book_payouts": json.dumps(book.get("payouts"), sort_keys=True, default=str),
        "adjust": adjust,
        "match_status": rec.get("status"),
        "escrow_result": (rec.get("escrow") or {}).get("result"),
        "steps": sorted(r["step"] for r in journal.steps(mid)),
    }


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(matches_mod, "_notify_spectator_outcomes", lambda *a, **k: None)
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    yield
    leases.forget_local_state()


def _reference(tmp_path, monkeypatch, kind: str) -> tuple[dict[str, Any], list[str]]:
    _fresh_store(monkeypatch, tmp_path / "reference")
    seen: list[str] = []
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", seen.append)
    mid, result = _scenario(kind)
    from gaming.src.stack.agentic.matches import get_match_service

    out = get_match_service().settle_result(mid, result)
    assert out["status"] == "settled"
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    return _money_state(mid), seen


@pytest.mark.parametrize("kind", ["win", "draw"])
def test_crash_at_every_step_then_retry_settles_exactly_once(tmp_path, monkeypatch, kind):
    ref, boundaries = _reference(tmp_path, monkeypatch, kind)
    # The settlement really moved money on every rail we care about.
    assert {"settling", "escrow", "spectator_settle", "finalize"} <= set(boundaries)
    if kind == "win":
        assert {"creator_fee", "lp_profit", "lp_loss"} <= set(boundaries)
    assert any(b.startswith("play_adjust:") for b in boundaries)
    assert ref["match_status"] == "settled"

    for i, crash_at in enumerate(boundaries):
        _fresh_store(monkeypatch, tmp_path / f"crash_{i}")
        mid, result = _scenario(kind)
        from gaming.src.stack.agentic.matches import get_match_service

        def _die(step: str, crash_at=crash_at) -> None:
            if step == crash_at:
                raise SimulatedCrash(step)

        monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", _die)
        # A dead process never releases its lease.
        monkeypatch.setattr(leases, "release", lambda *a, **k: None)
        with pytest.raises(SimulatedCrash):
            get_match_service().settle_result(mid, result)
        monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
        if crash_at != "finalize":
            assert MATCHES.get(mid)["status"] == "settling", crash_at

        # A new process: different owner id, the old lease has expired.
        leases.forget_local_state()
        monkeypatch.setattr(leases, "process_owner", lambda: "replacement-process")
        with transaction() as tx:
            tx.execute("UPDATE match_leases SET expires_at_ms = 0 WHERE match_id = ?", (mid,))
        get_match_service.cache_clear()
        if crash_at != "finalize":
            # The orphan sweep must see an expired lease as rescuable, and the
            # rescued worker resumes the table from its journal.
            assert leases.active_holder(mid) is None
            get_match_service().run_match(mid)
        else:
            # Died after the last step: a retry is a clean no-op.
            get_match_service().settle_result(mid, result)

        got = _money_state(mid)
        for key in ("balances", "moves", "pools", "book_status", "book_payouts", "adjust", "match_status", "escrow_result", "steps"):
            assert got[key] == ref[key], f"crash after {crash_at!r}: {key} differs"
        monkeypatch.undo()
        monkeypatch.setattr(matches_mod, "_notify_spectator_outcomes", lambda *a, **k: None)


def test_retry_with_a_different_result_is_refused(tmp_path, monkeypatch):
    _fresh_store(monkeypatch, tmp_path / "s")
    mid, result = _scenario("win")
    from gaming.src.stack.agentic.matches import get_match_service

    monkeypatch.setattr(leases, "release", lambda *a, **k: None)
    monkeypatch.setattr(
        matches_mod, "_SETTLE_STEP_HOOK", lambda s: (_ for _ in ()).throw(SimulatedCrash(s)) if s == "escrow" else None
    )
    with pytest.raises(SimulatedCrash):
        get_match_service().settle_result(mid, result)
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    with pytest.raises(RuntimeError, match="different result"):
        get_match_service().settle_result(mid, {"result": "draw", "winner_agent_id": None})
    # The stored result wins on resume.
    out = get_match_service().settle_result(mid, result)
    assert out["status"] == "settled" and out["escrow"]["result"] == "win"


def test_second_settle_after_success_is_a_no_op(tmp_path, monkeypatch):
    _fresh_store(monkeypatch, tmp_path / "s")
    mid, result = _scenario("win")
    from gaming.src.stack.agentic.matches import get_match_service

    get_match_service().settle_result(mid, result)
    before = _money_state(mid)
    get_match_service().settle_result(mid, result)
    assert _money_state(mid) == before
    with pytest.raises(RuntimeError, match="conflicting"):
        get_match_service().settle_result(mid, {"result": "draw", "winner_agent_id": None})


def test_settlement_attempts_are_capped(tmp_path, monkeypatch):
    _fresh_store(monkeypatch, tmp_path / "s")
    monkeypatch.setenv("BOARDMAN_MAX_SETTLE_ATTEMPTS", "2")
    mid, result = _scenario("win")
    from gaming.src.stack.agentic.matches import get_match_service

    monkeypatch.setattr(
        matches_mod, "_SETTLE_STEP_HOOK", lambda s: (_ for _ in ()).throw(RuntimeError("rpc down")) if s == "settling" else None
    )
    for _ in range(2):
        with pytest.raises(RuntimeError, match="rpc down"):
            get_match_service().settle_result(mid, result)
    with pytest.raises(RuntimeError, match="attempts exhausted"):
        get_match_service().settle_result(mid, result)
    assert MATCHES.get(mid)["status"] == "settle_failed"
