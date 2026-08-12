"""Stake negotiation, LP pools, spectator cap/refunds."""
from __future__ import annotations

from decimal import Decimal

from gaming.src.stack.agentic.economy.budget import (
    AgentBudget,
    negotiate_match_stake,
)
from gaming.src.stack.agentic.economy.lp import AgentLPPool
from gaming.src.stack.agentic.economy.spectator import SpectatorBook
from gaming.src.stack.agentic.economy.fees import FeeRouter


def test_whale_vs_lean_negotiation():
    """Raja $1000 cannot force equal stake above Nero's free capital."""
    raja = AgentBudget(
        bankroll_usdc="1000",
        max_stake_usdc="100",
        min_stake_usdc="1",
        reserve_bps=1500,
        spectator_seed_bps=600,
    )
    nero = AgentBudget(
        bankroll_usdc="100",
        max_stake_usdc="20",
        min_stake_usdc="1",
        reserve_bps=2500,
        spectator_seed_bps=500,
    )
    neg = negotiate_match_stake(
        raja, nero, Decimal("1000"), Decimal("100"), requested=Decimal("50")
    )
    assert neg.ok
    stake = Decimal(neg.stake_usdc)
    # Nero free = 100 * 0.75 = 75; max stake with 5% seed: 75/1.05 ≈ 71.4 but max_stake 20
    assert stake == Decimal("20")
    assert neg.binding in {"b", "request"} or Decimal(neg.max_b) <= Decimal(neg.max_a)
    # Costs fit free capital
    assert Decimal(neg.cost_a) <= Decimal(neg.free_a)
    assert Decimal(neg.cost_b) <= Decimal(neg.free_b)


def test_empty_bankroll_no_deal():
    rich = AgentBudget(bankroll_usdc="500", max_stake_usdc="50")
    broke = AgentBudget(bankroll_usdc="0.5", max_stake_usdc="25", min_stake_usdc="1")
    neg = negotiate_match_stake(rich, broke, Decimal("500"), Decimal("0.5"))
    assert not neg.ok


def test_fee_split_math():
    split = FeeRouter().split_skill_pot(
        stake_usdc=Decimal("10"),
        winner_agent={"agent_id": "a", "creator_fee_bps": 800, "creator_id": "c1"},
        loser_agent={"agent_id": "b"},
    )
    # pot 20, platform 3% = 0.6, gross 19.4, creator 8% = 1.552, owner 17.848
    assert Decimal(split.pot) == Decimal("20")
    assert Decimal(split.platform_fee) == Decimal("0.6")
    assert Decimal(split.creator_fee) + Decimal(split.owner_payout) == Decimal(
        split.winner_gross
    )


def test_spectator_pot_cap_and_seed_refund(tmp_path, monkeypatch):
    import gaming.src.stack.agentic.economy.spectator as spec_mod
    import gaming.src.stack.agentic.store as store_mod

    # Isolate store path if store uses fixed data dir — exercise logic in-memory via methods
    book = SpectatorBook()
    # Use unique match ids
    mid = "test_match_cap_1"
    # Clean if exists
    data = book._load()
    data["books"].pop(mid, None)
    book._save(data)

    rec = book.open_book(
        mid,
        agent_a_id="a",
        agent_b_id="b",
        seed_a=Decimal("0.5"),
        seed_b=Decimal("0.4"),
        pot_cap_usdc=Decimal("3"),
        agent_a_wallet="0xA",
        agent_b_wallet="0xB",
    )
    assert rec["status"] == "open"
    book.place_bet(mid, bettor_id="fan1", side="a", amount_usdc=Decimal("1"))
    book.place_bet(mid, bettor_id="fan2", side="b", amount_usdc=Decimal("1"))
    # pot = 0.5+0.4+1+1 = 2.9, room 0.1
    try:
        book.place_bet(mid, bettor_id="fan3", side="a", amount_usdc=Decimal("1"))
        assert False, "should reject over cap"
    except ValueError:
        pass

    settled = book.settle(mid, winner_side=None)
    assert settled["payouts"]["mode"] == "refund"
    seeds = settled["payouts"]["seed_refunds"]
    assert len(seeds) == 2
    assert Decimal(seeds[0]["amount"]) == Decimal("0.5")


def test_lp_profit_and_loss():
    pool = AgentLPPool()
    agent = "agent_test_lp_xyz"
    # clean
    data = pool._load()
    data["pools"].pop(agent, None)
    pool._save(data)

    pool.deposit(agent, lp_id="lp1", amount_usdc=Decimal("40"))
    pool.deposit(agent, lp_id="lp2", amount_usdc=Decimal("60"))
    dist = pool.distribute_skill_profit(
        agent, net_profit_usdc=Decimal("10"), lp_profit_share_bps=4000
    )
    # 40% of 10 = 4 to LPs; lp1 40%, lp2 60%
    assert Decimal(dist["lp_total"]) == Decimal("4")
    assert Decimal(dist["owner_residual"]) == Decimal("6")
    amounts = {p["lp_id"]: Decimal(p["amount"]) for p in dist["lp_payouts"]}
    assert amounts["lp1"] == Decimal("1.6")
    assert amounts["lp2"] == Decimal("2.4")

    # Loss haircut
    p2 = pool.get_pool(agent)
    before = Decimal(p2["total_lp_usdc"])
    pool.mark_loss(
        agent, loss_usdc=Decimal("20"), agent_bankroll_before=Decimal("200")
    )
    after = Decimal(pool.get_pool(agent)["total_lp_usdc"])
    assert after < before
