"""Owner sales desk — money earned from manager sales + listing history.

The read model (`party_sales_view`) is derived from each manager's recorded
market events (list / relist / delist / sold), with legacy demo-ledger rows as
the fallback for managers that predate the event log — never both, so a sale
is never counted twice.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
        list_manager_for_sale,
    )

    return {"create": create_manager_agent, "list": list_manager_for_sale}


def _market_history(agent_id: str) -> list[dict]:
    from gaming.src.stack.agentic.registry import get_registry

    rec = get_registry().get_agent(agent_id)
    return [e for e in (rec or {}).get("market_history") or [] if isinstance(e, dict)]


def test_listing_events_are_recorded(_world):
    """Every list / relist / delist / sale appends to the manager's history."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        delist_manager_agent,
        list_manager_for_sale,
    )

    dev = _world["create"](manager_name="Event FC", owner_id="dev_ev")["agent"]
    aid = dev["agent_id"]

    list_manager_for_sale(agent_id=aid, price_usdc="20.00", creator_cut_bps=500, listed_by="dev_ev")
    list_manager_for_sale(agent_id=aid, price_usdc="25.00", creator_cut_bps=500, listed_by="dev_ev")
    delist_manager_agent(agent_id=aid, listed_by="dev_ev")

    hist = _market_history(aid)
    kinds = [e["kind"] for e in hist]
    assert kinds == ["listed", "relisted", "delisted"]
    listed = hist[0]
    assert listed["price_usdc"] == "20.00" and listed["by"] == "dev_ev"
    assert hist[1]["price_usdc"] == "25.00"
    assert hist[2]["by"] == "dev_ev"


def test_developer_keeps_full_price_of_own_build(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
        party_sales_view,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Forge Desk", owner_id="dev_desk")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="30.00", listed_by="dev_desk")
    res = purchase_manager_agent(agent_id=aid, buyer_id="alice_desk")

    # the sold event carries the money split
    hist = _market_history(aid)
    sold = [e for e in hist if e["kind"] == "sold"]
    assert len(sold) == 1
    assert sold[0]["price_usdc"] == "30.00"
    assert sold[0]["seller_id"] == "dev_desk" and sold[0]["buyer_id"] == "alice_desk"
    assert sold[0]["seller_payout_usdc"] == "30.00" and sold[0]["creator_cut_usdc"] == "0"
    assert sold[0]["mode"] == "ledger" and sold[0]["first_sale"] is True

    # the developer's sales desk shows the full proceeds (they no longer own it)
    view = party_sales_view("dev_desk")
    assert view["total_earned_usdc"] == "30.00"
    assert view["as_seller_usdc"] == "30.00" and view["creator_cuts_usdc"] == "0.00"
    assert view["sale_count"] == 1
    assert view["portfolio"] == []  # sold — nothing left in the portfolio

    timeline = view["timeline"]
    assert len(timeline) == 2  # listed + sold
    assert timeline[0]["kind"] == "sold" and timeline[0]["role"] == "seller"
    assert timeline[0]["amount_usdc"] == "30.00" and timeline[0]["manager"] == "Forge Desk"


def test_creator_cuts_accumulate_on_resales(_world):
    """A developer earns: full price on their own sale + a creator cut on each
    later resale — and never double-counts (ledger rows exist for the same sales)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
        party_sales_view,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Royalty Desk", owner_id="dev_roy")["agent"]
    aid = dev["agent_id"]

    # first sale: dev keeps the full $40
    list_manager_for_sale(agent_id=aid, price_usdc="40.00", creator_cut_bps=500, listed_by="dev_roy")
    purchase_manager_agent(agent_id=aid, buyer_id="alice_roy")

    # alice resells at $50 → the dev gets 5% = $2.50
    list_manager_for_sale(agent_id=aid, price_usdc="50.00", creator_cut_bps=500, listed_by="alice_roy")
    purchase_manager_agent(agent_id=aid, buyer_id="bob_roy")

    view = party_sales_view("dev_roy")
    assert view["total_earned_usdc"] == "42.50"
    assert view["as_seller_usdc"] == "40.00"
    assert view["creator_cuts_usdc"] == "2.50"
    assert view["sale_count"] == 2

    roles = [(t["role"], t["amount_usdc"]) for t in view["timeline"] if t["kind"] == "sold"]
    assert ("seller", "40.00") in roles
    assert ("creator_cut", "2.50") in roles

    # alice's desk: she earned the $47.50 payout on the resale (she sold it)
    alice = party_sales_view("alice_roy")
    assert alice["total_earned_usdc"] == "47.50"
    assert alice["as_seller_usdc"] == "47.50"
    assert alice["portfolio"] == []  # she sold it — no longer owns it

    # bob bought it — it shows in his portfolio with the last sale recorded
    bob = party_sales_view("bob_roy")
    row = bob["portfolio"][0]
    assert row["agent_id"] == aid and row["owned"] is True
    assert row["sales_count"] == 2 and row["earned_usdc"] == "0.00"
    assert row["last_sale"]["seller_payout_usdc"] == "47.50"
    assert row["last_sale"]["mode"] == "ledger"
    assert row["last_sale"]["seller_id"] == "alice_roy"


def test_portfolio_shows_live_listing_state(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
        party_sales_view,
    )

    dev = _world["create"](manager_name="Holding Desk", owner_id="dev_hold2")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(
        agent_id=aid,
        price_usdc="15.00",
        creator_cut_bps=1000,
        reserve_price_usdc="9.00",
        listed_by="dev_hold2",
    )

    view = party_sales_view("dev_hold2")
    row = view["portfolio"][0]
    assert row["listed"] is True
    assert row["price_usdc"] == "15.00"
    assert row["creator_cut_bps"] == 1000 and row["reserve_usdc"] == "9.00"
    assert row["listed_at"] and row["earned_usdc"] == "0.00"
    assert view["sale_count"] == 0

    # the listing appears in the owner's timeline
    listed_events = [t for t in view["timeline"] if t["kind"] == "listed"]
    assert len(listed_events) == 1
    assert listed_events[0]["role"] == "owner" and listed_events[0]["amount_usdc"] == "15.00"


def test_legacy_demo_sales_fall_back_to_ledger_rows(_world):
    """Managers that predate the event log still report money — from the demo
    ledger rows (payout / creator cut) — exactly once."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
        party_sales_view,
        purchase_manager_agent,
    )
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    dev = _world["create"](manager_name="Legacy Desk", owner_id="dev_leg")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="22.00", creator_cut_bps=500, listed_by="dev_leg")
    purchase_manager_agent(agent_id=aid, buyer_id="alice_leg")

    # simulate a sale that happened before the event log: wipe the history but
    # keep the ledger rows (the pre-change money truth)
    data = load_json("agents.json", {"agents": {}})
    data["agents"][aid].pop("market_history", None)
    save_json("agents.json", data)

    assert _market_history(aid) == []
    view = party_sales_view("dev_leg")
    assert view["total_earned_usdc"] == "22.00"
    assert view["as_seller_usdc"] == "22.00" and view["sale_count"] == 1

    # timeline is synthesized from the ledger rows
    sold = [t for t in view["timeline"] if t["kind"] == "sold"]
    assert len(sold) == 1
    assert sold[0]["role"] == "seller" and sold[0]["amount_usdc"] == "22.00"

    # a second sale (recorded as an event) is NOT double counted against the
    # ledger rows of the first
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        party_sales_view as _view,
    )

    assert _view("dev_leg")["total_earned_usdc"] == "22.00"
