"""AFM match stakes never leave a dangling escrow.

When one club could not cover its 5 USDC stake, the old code opened the
escrow, locked the side that could pay, then refunded it with a fresh
credit — leaving the escrow "partial_lock" (or "open" when neither could
pay) forever. Other code reads unsettled escrows as live stakes (the agent
LP withdrawable in rematch_web), so a short side now
owes the stake and no escrow is opened at all.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

HOME, AWAY = "agent_bluelock_demo", "agent_aoashi_demo"


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "0")
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    yield


def _season(no: int) -> dict:
    return {"season_no": no, "stake_debt": {HOME: "0", AWAY: "0"}}


def test_short_side_owes_the_stake_and_no_escrow_opens():
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    hw, aw = S._wallet(HOME), S._wallet(AWAY)
    L.credit(hw, Decimal("100"), reason="test_fund", ref="t")
    L.credit(aw, Decimal("2"), reason="test_fund", ref="t")
    s = _season(7)
    S._settle_match(s, 1, HOME, AWAY, "home_win")

    assert L.get_escrow(f"afm_season_7_md1_{HOME}_{AWAY}") is None
    assert L.balance(hw) == Decimal("100")
    assert L.balance(aw) == Decimal("2")
    assert Decimal(s["stake_debt"][AWAY]) == Decimal("3.00")
    assert Decimal(s["stake_debt"][HOME]) == 0


def test_neither_side_paying_opens_nothing():
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    s = _season(8)
    S._settle_match(s, 2, HOME, AWAY, "draw")
    assert L.get_escrow(f"afm_season_8_md2_{HOME}_{AWAY}") is None
    assert Decimal(s["stake_debt"][HOME]) == Decimal("5.00")
    assert Decimal(s["stake_debt"][AWAY]) == Decimal("5.00")


def test_both_funded_stakes_settle_to_the_winner():
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    hw, aw = S._wallet(HOME), S._wallet(AWAY)
    L.credit(hw, Decimal("50"), reason="test_fund", ref="t")
    L.credit(aw, Decimal("50"), reason="test_fund", ref="t")
    s = _season(9)
    S._settle_match(s, 3, HOME, AWAY, "away_win")

    esc = L.get_escrow(f"afm_season_9_md3_{HOME}_{AWAY}")
    assert esc["status"] == "settled"
    assert L.balance(hw) == Decimal("45")
    assert L.balance(aw) > Decimal("50")  # 10 pot less the platform fee
    assert s["stake_debt"] == {HOME: "0", AWAY: "0"}
