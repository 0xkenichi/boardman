"""AFM manager marketplace — owner seat step 1: create or acquire an agent.

Covers: creating a manager agent + seeded club, archetype-driven matchday
decisions, acquiring a developer-built manager, and the club-store re-seed
keeping owner-created clubs while pruning chess-only owners.
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
    """Demo AFM managers + clubs + the marketplace service, under tmp store."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
        list_market_agents,
    )
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    return {
        "create": create_manager_agent,
        "list": list_market_agents,
        "registry": get_registry(),
    }


def test_create_registers_agent_and_seeds_club(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        acquire_manager_agent,
    )

    out = _world["create"](
        manager_name="Test City",
        club_name="Test City FC",
        archetype="pragmatist",
        formation="5-3-2",
        owner_id="owner_test",
    )
    agent = out["agent"]
    assert agent["name"] == "Test City"
    assert agent["archetype"] == "pragmatist"
    assert agent["strategy_id"] == "pragmatist_playbook"
    assert agent["owner_id"] == "owner_test"
    assert agent["has_club"] and agent["club_name"] == "Test City FC"

    rec = _world["registry"].get_agent(agent["agent_id"])
    assert rec is not None
    assert "agentic.football_managers" in rec["game_ids"]
    assert rec["mind"]["archetype"] == "pragmatist"
    assert rec["wallet_address"]

    club = out["club"]
    assert club["agent_id"] == agent["agent_id"]
    assert club["formation"] == "5-3-2"
    assert len(club["starters"]) == 11
    gk = [p for p in club["starters"] if str(p.get("slot") or "").upper() == "GK"]
    assert len(gk) == 1
    assert float(club["spend_usdc"]) <= float(club["budget_usdc"]) + 1e-6

    # the new manager shows up on the marketplace
    ids = [a["agent_id"] for a in _world["list"]()]
    assert agent["agent_id"] in ids


def test_create_rejects_bad_archetype_or_formation(_world):
    with pytest.raises(ValueError, match="archetype"):
        _world["create"](manager_name="Bad", archetype="false_nine_wizard")
    with pytest.raises(ValueError, match="formation"):
        _world["create"](manager_name="Bad", archetype="tactician", formation="2-7-2")


def test_archetype_drives_matchday_decisions(_world):
    """A pragmatist parks (low_block) and a possession coach keeps the ball —
    both pick their strategy's shapes and tags on the decide loop."""
    from gaming.src.stack.agentic.games.football_managers.decide import decide_matchday

    prag = _world["create"](manager_name="Low Block United", archetype="pragmatist")["agent"]
    poss = _world["create"](manager_name="Keepball City", archetype="possession")["agent"]

    season = {
        "division": [prag["agent_id"], poss["agent_id"], "agent_bluelock_demo"],
        "standings": {},
    }

    p = decide_matchday(prag["agent_id"], season, 1)
    assert p["formation"] in {"5-3-2", "4-1-4-1", "4-4-2"}
    assert set(p["tags"]) <= {"low_block", "counter"}

    q = decide_matchday(poss["agent_id"], season, 1)
    assert q["formation"] in {"4-3-3", "4-2-3-1", "4-1-4-1"}
    assert set(q["tags"]) <= {"tiki_taka", "counter"}


def test_acquire_transfers_ownership(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        acquire_manager_agent,
    )

    out = acquire_manager_agent(agent_id="agent_bluelock_demo", owner_id="owner_alice")
    agent = out["agent"]
    assert agent["owner_id"] == "owner_alice"
    assert agent["adopted"] is True
    assert out["previous_owner_id"] != "owner_alice"

    rec = _world["registry"].get_agent("agent_bluelock_demo")
    assert rec["owner_id"] == "owner_alice"
    assert rec["acquired_by"] == "owner_alice"

    row = next(a for a in _world["list"]() if a["agent_id"] == "agent_bluelock_demo")
    assert row["owner_id"] == "owner_alice" and row["adopted"] is True

    with pytest.raises(ValueError):
        acquire_manager_agent(agent_id="agent_raja", owner_id="owner_alice")  # chess-only


def test_seed_keeps_custom_clubs_and_prunes_chess_only(_world):
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
        get_club,
        seed_demo_clubs,
    )

    custom = _world["create"](manager_name="Survivor FC", archetype="striker")["agent"]

    # a chess-only agent with a club (the old leak: clubs for non-AFM owners)
    _world["registry"].register_agent(
        agent_id="agent_chess_only",
        name="Chess Bot",
        owner_id="creator_chess",
        strategy_id="stockfish",
        openings=[],
        mind={},
        game_ids=["agentic.chess_standard"],
    )
    ensure_club_for_agent("agent_chess_only", club_name="Chess United")

    seed_demo_clubs()  # keeper re-seed must not wipe owner-created clubs

    assert get_club(custom["agent_id"]) is not None
    assert get_club("agent_bluelock_demo") is not None
    assert get_club("agent_chess_only") is None  # pruned: registered, not AFM


def test_created_manager_can_play_a_full_season(_world):
    """A 3rd club created in the owner seat joins and resolves a real season."""
    from datetime import datetime, timedelta, timezone

    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    new = _world["create"](manager_name="Third Wheel", archetype="possession")["agent"]
    start = datetime.now(timezone.utc) - timedelta(hours=7)

    S.open_season(
        agent_ids=[new["agent_id"], "agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=start,
    )
    out = S.tick()
    assert out["resolved"] == [1]

    club = get_club(new["agent_id"])
    assert len(club["starters"]) == 11
    assert set(club["tactical_tags"]) <= {"tiki_taka", "counter"}

    st = S._state()
    results = st["season"]["matchdays"]["1"]["results"]
    assert any(r["home_agent_id"] == new["agent_id"] or r["away_agent_id"] == new["agent_id"] for r in results)


# ------------------------------------------------------------ selling managers


def test_developer_lists_manager_then_buyer_purchases(_world):
    """A developer lists a manager at a price with a creator cut; a buyer pays
    on the demo ledger and ownership moves. First sale (developer = seller)
    keeps the full price; a resale pays the developer their cut."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        acquire_manager_agent,
        delist_manager_agent,
        list_manager_for_sale,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Forge United", archetype="possession", owner_id="dev_mint")["agent"]
    aid = dev["agent_id"]

    out = list_manager_for_sale(agent_id=aid, price_usdc="30.00", creator_cut_bps=500, listed_by="dev_mint")
    assert out["agent"]["listed"] is True
    assert out["agent"]["price_usdc"] == "30.00"
    assert out["agent"]["creator_cut_bps"] == 500
    assert out["agent"]["seller_id"] == "dev_mint"

    # only the current owner may list / delist
    with pytest.raises(ValueError, match="only the current owner"):
        list_manager_for_sale(agent_id=aid, price_usdc="1.00", listed_by="stranger")
    with pytest.raises(ValueError, match="only the current owner"):
        delist_manager_agent(agent_id=aid, listed_by="stranger")

    # a listed manager can no longer be adopted free, and its owner can't buy it
    with pytest.raises(ValueError, match="listed for sale"):
        acquire_manager_agent(agent_id=aid, owner_id="buyer_alice")
    with pytest.raises(ValueError, match="already own"):
        purchase_manager_agent(agent_id=aid, buyer_id="dev_mint")

    # first sale — the developer keeps the full price
    res = purchase_manager_agent(agent_id=aid, buyer_id="buyer_alice")
    sale = res["sale"]
    assert sale["first_sale"] is True and sale["price_usdc"] == "30.00"
    assert sale["seller_payout_usdc"] == "30.00" and sale["creator_cut_usdc"] == "0"
    assert res["agent"]["owner_id"] == "buyer_alice"
    assert res["agent"]["listed"] is False
    assert res["agent"]["sales_count"] == 1
    assert str(L.balance("owner:dev_mint")) == "30.00"
    assert L.balance("owner:buyer_alice") == 0  # faucet exactly covered the price

    # resale by the new owner — the developer still earns their creator cut
    list_manager_for_sale(agent_id=aid, price_usdc="40.00", creator_cut_bps=500, listed_by="buyer_alice")
    res2 = purchase_manager_agent(agent_id=aid, buyer_id="buyer_bob")
    s2 = res2["sale"]
    assert s2["first_sale"] is False
    assert s2["creator_cut_usdc"] == "2.00"  # 5% of 40
    assert s2["seller_payout_usdc"] == "38.00"
    assert str(L.balance("creator:dev_mint")) == "2.00"
    assert str(L.balance("owner:buyer_alice")) == "38.00"
    assert L.balance("owner:buyer_bob") == 0
    assert res2["agent"]["owner_id"] == "buyer_bob"

    # ledger trail: buy debit + payout (+ creator cut) per sale
    snap = L.snapshot()
    reasons = [tx.get("reason") for tx in snap["txs"]]
    assert reasons.count("afm_agent_sale_buy") == 2
    assert reasons.count("afm_agent_sale_payout") == 2
    assert reasons.count("afm_agent_sale_creator_cut") == 1


def test_delist_pulls_manager_off_market(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        delist_manager_agent,
        list_manager_for_sale,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Hold FC", owner_id="dev_hold")["agent"]
    list_manager_for_sale(agent_id=dev["agent_id"], price_usdc="12.50", listed_by="dev_hold")
    out = delist_manager_agent(agent_id=dev["agent_id"], listed_by="dev_hold")
    assert out["agent"]["listed"] is False and out["agent"]["price_usdc"] is None

    with pytest.raises(ValueError, match="not listed for sale"):
        delist_manager_agent(agent_id=dev["agent_id"], listed_by="dev_hold")
    with pytest.raises(ValueError, match="not listed for sale"):
        purchase_manager_agent(agent_id=dev["agent_id"], buyer_id="buyer_alice")


def test_create_with_price_lists_manager_immediately(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import list_market_agents

    out = _world["create"](
        manager_name="Storefront City",
        archetype="striker",
        owner_id="dev_store",
        list_price_usdc="15.00",
        creator_cut_bps=1000,
    )
    row = out["agent"]
    assert row["listed"] is True
    assert row["price_usdc"] == "15.00" and row["creator_cut_bps"] == 1000
    listed = [a for a in list_market_agents() if a["agent_id"] == row["agent_id"]][0]
    assert listed["listed"] and listed["seller_id"] == "dev_store"


def test_builtin_demo_managers_ship_listed_and_are_buyable(_world):
    """The marketplace seeds Blue Lock / Ao Ashi listed by their developers,
    so the demo owner-seat can actually buy a developer-built manager."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_market_agents,
        purchase_manager_agent,
    )

    rows = {a["agent_id"]: a for a in list_market_agents()}
    bl = rows["agent_bluelock_demo"]
    assert bl["listed"] is True
    assert bl["price_usdc"] == "25.00" and bl["creator_cut_bps"] == 500
    assert bl["seller_id"] == bl["creator_id"] == "creator_bluelock_demo"
    assert rows["agent_aoashi_demo"]["listed"] is True

    # Match-Slice ships listed by its developer too, so the marketplace has
    # a third priced demo manager to buy
    ms = rows["agent_matchslice_demo"]
    assert ms["listed"] is True
    assert ms["price_usdc"] == "22.00" and ms["creator_cut_bps"] == 500
    assert ms["seller_id"] == ms["creator_id"] == "creator_matchslice_demo"

    # buying the developer's built-in pays the developer studio wallet
    res = purchase_manager_agent(agent_id="agent_bluelock_demo", buyer_id="demo_owner")
    assert res["agent"]["owner_id"] == "demo_owner"
    assert res["sale"]["first_sale"] is True
    assert str(L.balance("creator:creator_bluelock_demo")) == "25.00"

    # adopted-by-a-user managers are never force-listed
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_market_agents as _again,
    )

    bl2 = [a for a in _again() if a["agent_id"] == "agent_bluelock_demo"][0]
    assert bl2["listed"] is False and bl2["owner_id"] == "demo_owner"


# ------------------------------------------------------------ offers & reserve


def test_reserve_declines_low_offers_and_owner_accepts(_world):
    """The owner sets a reserve floor; below-reserve offers auto-decline and
    at/above-reserve offers queue up for the owner to accept or reject.
    Accepting settles the sale at the offered price."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        accept_manager_offer,
        list_manager_for_sale,
        make_manager_offer,
        reject_manager_offer,
    )

    dev = _world["create"](manager_name="Negotiate FC", owner_id="dev_sell")["agent"]
    aid = dev["agent_id"]
    row = list_manager_for_sale(
        agent_id=aid,
        price_usdc="50.00",
        creator_cut_bps=500,
        reserve_price_usdc="30.00",
        listed_by="dev_sell",
    )["agent"]
    assert row["reserve_usdc"] == "30.00" and row["pending_offers"] == []

    # below the reserve → declined on the spot, never queued
    low = make_manager_offer(agent_id=aid, offer_usdc="20.00", buyer_id="buyer_a")
    assert low["auto_declined"] is True and low["offer"]["status"] == "rejected"
    assert low["agent"]["pending_offers"] == []

    # at/above the reserve → pending in the owner's inbox
    offer = make_manager_offer(agent_id=aid, offer_usdc="35.00", buyer_id="buyer_a")
    assert offer["auto_declined"] is False and offer["offer"]["status"] == "pending"
    pending = offer["agent"]["pending_offers"]
    assert len(pending) == 1 and pending[0]["buyer_id"] == "buyer_a"
    assert pending[0]["amount_usdc"] == "35.00"
    offer_a_id = pending[0]["offer_id"]

    # guards: no second pending from the same buyer, no self-offers, no strangers deciding
    with pytest.raises(ValueError, match="already have a pending offer"):
        make_manager_offer(agent_id=aid, offer_usdc="36.00", buyer_id="buyer_a")
    with pytest.raises(ValueError, match="can't offer on your own"):
        make_manager_offer(agent_id=aid, offer_usdc="36.00", buyer_id="dev_sell")
    with pytest.raises(ValueError, match="only the current owner"):
        accept_manager_offer(agent_id=aid, offer_id=offer_a_id, accept_by="buyer_a")
    with pytest.raises(ValueError, match="only the current owner"):
        reject_manager_offer(agent_id=aid, offer_id=offer_a_id, reject_by="buyer_a")

    # a second buyer's offer arrives too
    offer_b = make_manager_offer(agent_id=aid, offer_usdc="40.00", buyer_id="buyer_b")
    assert len(offer_b["agent"]["pending_offers"]) == 2
    offer_b_id = next(
        p["offer_id"] for p in offer_b["agent"]["pending_offers"] if p["buyer_id"] == "buyer_b"
    )

    # owner accepts buyer B at $40 — full price to the developer (their own build)
    res = accept_manager_offer(agent_id=aid, offer_id=offer_b_id, accept_by="dev_sell")
    sale = res["sale"]
    assert sale["price_usdc"] == "40.00" and sale["source"] == "offer_accepted"
    assert sale["seller_payout_usdc"] == "40.00"
    assert res["agent"]["owner_id"] == "buyer_b"
    assert res["agent"]["listed"] is False and res["agent"]["pending_offers"] == []
    assert str(L.balance("owner:dev_sell")) == "40.00"


def test_offer_accepted_on_resale_pays_developer_cut(_world):
    """A later owner accepting an offer still pays the original developer the
    creator cut set on the listing."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        accept_manager_offer,
        list_manager_for_sale,
        make_manager_offer,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Royalty FC", owner_id="dev_two")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="60.00", creator_cut_bps=1000, listed_by="dev_two")
    purchase_manager_agent(agent_id=aid, buyer_id="alice_owner")  # first sale → dev_two keeps $60

    # alice relists and accepts an offer below buy-now but above her reserve
    list_manager_for_sale(
        agent_id=aid,
        price_usdc="70.00",
        creator_cut_bps=1000,
        reserve_price_usdc="45.00",
        listed_by="alice_owner",
    )
    offer = make_manager_offer(agent_id=aid, offer_usdc="50.00", buyer_id="bob_buyer")
    oid = next(p["offer_id"] for p in offer["agent"]["pending_offers"])

    res = accept_manager_offer(agent_id=aid, offer_id=oid, accept_by="alice_owner")
    s = res["sale"]
    assert s["first_sale"] is False and s["price_usdc"] == "50.00"
    assert s["creator_cut_usdc"] == "5.00"  # 10% → original developer
    assert s["seller_payout_usdc"] == "45.00"
    assert res["agent"]["owner_id"] == "bob_buyer"
    # first sale proceeds went to the developer's owner wallet; the creator-cut
    # wallet only collects the 10% royalty on this resale
    assert str(L.balance("creator:dev_two")) == "5.00"
    assert str(L.balance("owner:dev_two")) == "60.00"
    assert str(L.balance("owner:alice_owner")) == "45.00"


def test_reject_keeps_listing_and_buy_now_cancels_offers(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
        make_manager_offer,
        purchase_manager_agent,
        reject_manager_offer,
    )

    dev = _world["create"](manager_name="Decider FC", owner_id="dev_decide")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="25.00", reserve_price_usdc="10.00", listed_by="dev_decide")

    o1 = make_manager_offer(agent_id=aid, offer_usdc="15.00", buyer_id="buyer_a")
    o2 = make_manager_offer(agent_id=aid, offer_usdc="18.00", buyer_id="buyer_b")
    reject_id = next(p["offer_id"] for p in o1["agent"]["pending_offers"] if p["buyer_id"] == "buyer_a")

    # rejecting one offer leaves the listing + the other offer untouched
    out = reject_manager_offer(agent_id=aid, offer_id=reject_id, reject_by="dev_decide")
    remaining = out["agent"]["pending_offers"]
    assert out["agent"]["listed"] is True
    assert len(remaining) == 1 and remaining[0]["buyer_id"] == "buyer_b"
    with pytest.raises(ValueError, match="not pending"):
        reject_manager_offer(agent_id=aid, offer_id=reject_id, reject_by="dev_decide")

    # buy-now by a third party voids the outstanding offer
    res = purchase_manager_agent(agent_id=aid, buyer_id="buyer_c")
    assert res["agent"]["owner_id"] == "buyer_c"
    assert res["agent"]["pending_offers"] == []
    assert res["agent"]["listed"] is False

    # no offers on an unlisted manager, and buying your own listing is blocked
    with pytest.raises(ValueError, match="not listed for sale"):
        make_manager_offer(agent_id=aid, offer_usdc="5.00", buyer_id="buyer_d")
    list_manager_for_sale(agent_id=aid, price_usdc="30.00", listed_by="buyer_c")
    with pytest.raises(ValueError, match="already own"):
        purchase_manager_agent(agent_id=aid, buyer_id="buyer_c")


def test_delist_cancels_pending_offers(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        delist_manager_agent,
        list_manager_for_sale,
        make_manager_offer,
    )

    dev = _world["create"](manager_name="Walkaway FC", owner_id="dev_walk")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="20.00", listed_by="dev_walk")
    make_manager_offer(agent_id=aid, offer_usdc="12.00", buyer_id="buyer_a")

    out = delist_manager_agent(agent_id=aid, listed_by="dev_walk")
    assert out["agent"]["listed"] is False and out["agent"]["pending_offers"] == []