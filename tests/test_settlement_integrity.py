"""Settlement-integrity regression tests.

Root cause under test: on agm_91dadd7c75f5 a draw-refund raced the real
settlement — ledger.settle silently no-op'd on the conflict, the spectator
book kept the wrong draw result, and the $10 fan pool was stranded. These
tests pin the guards so a repeat is impossible.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db.tables import MATCHES
from gaming.src.stack.agentic.economy.spectator import SpectatorBook
from gaming.src.stack.agentic.matches import AgentMatchService, TableBusy


W_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
W_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class _Balances:
    """Read-through view so the assertions below read like the old dict."""

    def __getitem__(self, wallet: str) -> str:
        return str(ledger.balance(wallet))

    def get(self, wallet: str, default: str = "0") -> str:
        return str(ledger.balance(wallet))


@pytest.fixture()
def ledger_state():
    """The per-test database ledger (conftest gives each test its own store)."""
    return {"balances": _Balances()}


def _make_locked_escrow(match_id: str, stake: str = "10") -> None:
    ledger.credit(W_A, Decimal("50"), reason="fund")
    ledger.credit(W_B, Decimal("50"), reason="fund")
    ledger.open_escrow(
        match_id,
        agent_a_wallet=W_A,
        agent_b_wallet=W_B,
        stake_usdc=Decimal(stake),
    )
    ledger.lock(match_id, W_A)
    ledger.lock(match_id, W_B)


def test_ledger_settle_idempotent_same_result(ledger_state):
    _make_locked_escrow("m_same")
    first = ledger.settle("m_same", W_A, result="win")
    again = ledger.settle("m_same", W_A, result="win")
    assert first["result"] == again["result"] == "win"
    assert again["winner_wallet"] == W_A
    # 50 seed − 10 lock + 7%-of-20-pot payout (18.6), credited exactly once
    assert Decimal(ledger_state["balances"][W_A]) == Decimal("58.6")


def test_ledger_settle_raises_on_conflicting_result(ledger_state):
    _make_locked_escrow("m_conflict")
    ledger.settle("m_conflict", W_A, result="win")
    with pytest.raises(ValueError, match="conflicting"):
        ledger.settle("m_conflict", W_A, result="draw")
    # balances untouched by the refused draw-refund
    assert Decimal(ledger_state["balances"].get(W_A, "0")) == Decimal("58.6")


def test_ledger_draw_then_win_refused(ledger_state):
    _make_locked_escrow("m_dw")
    ledger.settle("m_dw", W_A, result="draw")
    with pytest.raises(ValueError, match="conflicting"):
        ledger.settle("m_dw", W_A, result="win")
    # both refunds intact (50 − 10 + 10), no payout layered on top
    assert Decimal(ledger_state["balances"][W_A]) == Decimal("50")
    assert Decimal(ledger_state["balances"][W_B]) == Decimal("50")


def test_spectator_settle_idempotent_same_winner():
    sb = SpectatorBook()
    sb.ensure_from_match(
        {
            "match_id": "m_spec",
            "agent_a_id": "agent-a",
            "agent_b_id": "agent-b",
            "economy": {},
        }
    )
    first = sb.settle("m_spec", winner_side="a")
    again = sb.settle("m_spec", winner_side="a")
    assert first["status"] == again["status"] == "settled"
    assert (again.get("payouts") or {}).get("winner_side") == "a"


def test_spectator_settle_raises_on_conflicting_winner():
    sb = SpectatorBook()
    sb.ensure_from_match(
        {
            "match_id": "m_spec2",
            "agent_a_id": "agent-a",
            "agent_b_id": "agent-b",
            "economy": {},
        }
    )
    sb.settle("m_spec2", winner_side="a")
    with pytest.raises(ValueError, match="refusing conflicting"):
        sb.settle("m_spec2", winner_side=None)  # draw after a win — the bug
    with pytest.raises(ValueError, match="refusing conflicting"):
        sb.settle("m_spec2", winner_side="b")


def test_run_match_tablebusy(monkeypatch):
    """A second run_match on the same live table must raise TableBusy."""
    svc = AgentMatchService()
    mid = "m_busy"
    fake_match = {
        "match_id": mid,
        "status": "playing",
        "game_id": "agentic.chess_standard",
        "white_agent_id": "agent-a",
        "black_agent_id": "agent-b",
        "stake_usdc": "10",
    }

    class _FakeReg:
        def get_agent(self, _):
            return {"agent_id": "agent-a", "wallet_address": W_A}

    MATCHES.put(mid, dict(fake_match))
    monkeypatch.setattr(
        "gaming.src.stack.agentic.matches.get_registry", lambda: _FakeReg()
    )

    from gaming.src.stack.agentic.matches import _RUNNING, _RUNNING_LOCK

    with _RUNNING_LOCK:
        _RUNNING[mid] = 0.0  # simulate another driver mid-game
    try:
        with pytest.raises(TableBusy):
            svc.run_match(mid)
    finally:
        with _RUNNING_LOCK:
            _RUNNING.pop(mid, None)
    # the second driver's own registry entry was cleaned up after the raise
    with _RUNNING_LOCK:
        assert mid not in _RUNNING


def test_run_match_registry_cleared_on_error(monkeypatch):
    """Driver registry must not leak entries when a match blows up mid-run."""
    svc = AgentMatchService()
    mid = "m_leak"
    fake_match = {
        "match_id": mid,
        "status": "playing",
        "game_id": "agentic.chess_standard",
        "white_agent_id": "agent-a",
        "black_agent_id": "agent-missing",
        "stake_usdc": "10",
    }

    class _RegMissing:
        def get_agent(self, aid):
            return {"agent_id": aid} if aid == "agent-a" else None

    MATCHES.put(mid, dict(fake_match))
    monkeypatch.setattr(
        "gaming.src.stack.agentic.matches.get_registry", lambda: _RegMissing()
    )
    with pytest.raises(ValueError, match="agents missing"):
        svc.run_match(mid)

    from gaming.src.stack.agentic.matches import _RUNNING

    assert mid not in _RUNNING
