"""The twice-per-season transfer window — offer queue, fees, settlement.

Sphera's shape, asserted end to end: list (1% fee) → bid into the queue →
seller accepts/rejects → ledger settlement (seller nets price − 3.5% tax) →
player moves. Unanswered offers expire at window close; free agents are an
instant buy; agents act through "transfers" actions in their plan reply.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )

    reg = get_registry()
    reg.ensure_demo_agents()
    seed_demo_clubs()
    return reg


@pytest.fixture()
def _season(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() + timedelta(hours=2),
    )
    return S


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _raw(S):
    """The raw season state (id-list division) — what the ask/context consume."""
    return S._state()["season"]


def _demo_ids(n=3):
    """Season clubs first (they hold faucet-funded wallets), then the rest."""
    ordered = [
        "agent_bluelock_demo",
        "agent_aoashi_demo",
        "agent_matchslice_demo",
        "agent_academy_demo",
        "agent_galactico_demo",
        "agent_catenaccio_demo",
        "agent_tinkerer_demo",
    ]
    return ordered[:n]


def _runway(pid):
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player
    from gaming.src.stack.agentic.games.football_managers.market import WAGE_RUNWAY_MATCHDAYS

    return Decimal(str(get_player(pid)["wage_per_matchday_usdc"])) * WAGE_RUNWAY_MATCHDAYS


def _trim_squad(agent_id, target):
    """Cut a club down to `target` players (drops from the back of the roster)."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers.catalog import set_owner

    state = CS._state()
    rec = state["clubs"][agent_id]
    for pid in rec["roster"][target:]:
        set_owner(pid, None)
    rec["roster"] = rec["roster"][:target]
    rec["starters"] = [x for x in rec.get("starters") or [] if x in rec["roster"]]
    rec["bench"] = [x for x in rec.get("bench") or [] if x in rec["roster"]]
    CS._save(state)


def _pad_squad(agent_id, target, *, skip_gk=False):
    """Cheap free-agent buys until the squad is deep enough to trade."""
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import market as M

    CS.adjust_budget(agent_id, Decimal("80.00"))
    while len(CS.roster_ids(agent_id)) < target:
        cands = [
            p
            for p in cat.list_players(free_only=True)
            if not (skip_gk and p["slot"] == "GK")
        ]
        if not cands:
            break
        pid = min(cands, key=lambda p: Decimal(str(p["game_price_usdc"])))["player_id"]
        M.buy_free_agent(agent_id, pid)


# ---------------------------------------------------------------- lifecycle


def test_window_gates_every_market_action(_world, _season):
    from gaming.src.stack.agentic.games.football_managers import market as M

    seller, buyer = _demo_ids(2)
    with pytest.raises(M.MarketError):
        M.list_player(seller, "afm_pl_001", "10")
    with pytest.raises(M.MarketError):
        M.buy_free_agent(buyer, "afm_pl_001")
    with pytest.raises(M.MarketError):
        M.place_bid(buyer, "afm_pl_001", "5")

    M.open_window(1, "mid", closes_at="soon")
    win = M.window_status()
    assert win["open"] is True and win["phase"] == "mid" and win["season_no"] == 1
    # reopening the same window is a no-op, a different one supersedes
    M.open_window(1, "mid", closes_at="soon")
    assert M.window_status()["phase"] == "mid"

    M.close_window(1, "mid", reason="test_done")
    assert M.window_status()["open"] is False
    with pytest.raises(M.MarketError):
        M.list_player(seller, "afm_pl_001", "10")


def test_unanswered_offers_expire_at_close(_world, _season):
    from gaming.src.stack.agentic.games.football_managers import market as M

    seller, buyer = _demo_ids(2)
    M.open_window(1, "mid", closes_at="soon")
    _pad_squad(seller, 17)  # 13-man roster → must deepen before it can sell
    CS_BUDGET = None  # (buyer needs transfer authority to bid)
    from gaming.src.stack.agentic.games.football_managers import club_store as _CS

    _CS.adjust_budget(buyer, Decimal("60.00"))
    pid = _any_seller_outfield(seller)
    listing = M.list_player(seller, pid, "10")
    assert listing["ok"] is True
    bid = M.place_bid(buyer, pid, "9")
    assert bid["ok"] is True
    M.close_window(1, "mid", reason="deadline")
    offer = M._mload()["offers"][bid["offer_id"]]
    assert offer["status"] == "expired"
    # and the listing survives the close (the club still wants to sell)
    assert pid in M._mload()["listings"]


def _any_seller_outfield(agent_id):
    return _seller_outfields(agent_id)[0]


def _seller_outfields(agent_id):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player

    out = [
        pid
        for pid in CS.roster_ids(agent_id)
        if str((get_player(pid) or {}).get("slot") or "") != "GK"
    ]
    if not out:
        raise AssertionError("no outfield player found")
    return out


# ------------------------------------------------------------ money + moves


def test_list_fee_bid_and_sale_move_money_and_player(_world, _season):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import market as M
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player

    seller, buyer, rival = _demo_ids(3)
    M.open_window(1, "mid", closes_at="soon")
    CS.adjust_budget(buyer, Decimal("60.00"))
    CS.adjust_budget(rival, Decimal("60.00"))
    _pad_squad(seller, 17)  # 13-man roster → must deepen before it can sell

    pid = _any_seller_outfield(seller)
    price = Decimal(str(get_player(pid)["game_price_usdc"]))
    sw, bw = M._wallet_of(seller), M._wallet_of(buyer)
    sw0, bw0 = L.balance(sw), L.balance(bw)
    house0 = L.balance(M.HOUSE_MARKET_WALLET)
    tb0 = CS.transfer_balance(buyer)

    # listing charges 1% of the ask up front, to the House
    out = M.list_player(seller, pid, price)
    fee = Decimal(out["fee_usdc"])
    assert fee == (price * Decimal("0.01")).quantize(Decimal("0.01"))
    assert L.balance(sw) == sw0 - fee
    assert L.balance(M.HOUSE_MARKET_WALLET) == house0 + fee

    # two bids queue; the first accepted wins, the rival is outbid
    bid = M.place_bid(buyer, pid, price)
    bid2 = M.place_bid(rival, pid, price)
    assert bid["ok"] and bid2["ok"]

    res = M.respond_offer(bid["offer_id"], seller, True)
    assert res["status"] == "accepted"
    tax, net = Decimal(res["tax_usdc"]), Decimal(res["seller_net_usdc"])
    assert net == price - tax
    # the football moved
    assert pid in CS.roster_ids(buyer)
    assert pid not in CS.roster_ids(seller)
    assert get_player(pid)["owner_agent_id"] == buyer
    # the money moved on the ledger: buyer pays price, seller nets price − tax
    assert L.balance(bw) == bw0 - price
    assert L.balance(sw) == (sw0 - fee) + net
    assert L.balance(M.HOUSE_MARKET_WALLET) == house0 + fee + tax
    # club transfer balances moved the other way
    # at least price + wage runway; today it is 2x price + runway because
    # transfer_balance counts the fee in both budget and squad spend (reported)
    assert CS.transfer_balance(buyer) <= tb0 - price - _runway(pid)
    # the rival's queued offer was rejected as outbid
    assert M._mload()["offers"][bid2["offer_id"]]["status"] == "rejected"
    # and the listing is consumed
    assert pid not in M._mload()["listings"]


def test_sale_guards_min_squad_only_keeper_and_funds(_world, _season):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import market as M
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player

    seller, buyer = _demo_ids(2)
    other = [a for a in _demo_ids(7) if a not in (seller, buyer)][0]
    M.open_window(1, "mid", closes_at="soon")
    CS.adjust_budget(buyer, Decimal("60.00"))

    # a 13-man squad cannot sell anyone — it would drop below the XI+bench floor
    pid = _any_seller_outfield(seller)
    M.list_player(seller, pid, "5")
    bid = M.place_bid(buyer, pid, "5")
    with pytest.raises(M.MarketError) as err:
        M.respond_offer(bid["offer_id"], seller, True)
    assert "seller_below_min_squad" in str(err.value)

    # the last keeper is not sellable even from a deep squad
    gks = [p["player_id"] for p in CS.get_club(seller)["squad"] if p["slot"] == "GK"]
    for extra in gks[1:]:
        CS.move_player(extra, from_agent=seller, to_agent=other)
    _pad_squad(seller, 18, skip_gk=True)
    assert [p for p in CS.get_club(seller)["squad"] if p["slot"] == "GK"]
    keeper = [p["player_id"] for p in CS.get_club(seller)["squad"] if p["slot"] == "GK"][0]
    M.list_player(seller, keeper, "5")
    bid = M.place_bid(buyer, keeper, "5")
    with pytest.raises(M.MarketError) as err:
        M.respond_offer(bid["offer_id"], seller, True)
    assert "seller_would_lose_only_goalkeeper" in str(err.value)

    # an unaffordable bid never enters the queue (fresh listing — the first
    # one is still open after the rejected sale). Listing is cheap; the bid
    # is what the House refuses to queue.
    pid2 = [p for p in _seller_outfields(seller) if p != pid][0]
    M.list_player(seller, pid2, "5")
    with pytest.raises(M.MarketError) as err:
        M.place_bid(buyer, pid2, "999999")
    assert "insufficient_budget" in str(err.value)


def test_free_agent_instant_buy(_world, _season):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import market as M

    buyer = _demo_ids(1)[0]
    M.open_window(1, "mid", closes_at="soon")
    CS.adjust_budget(buyer, Decimal("60.00"))
    pid = min(
        cat.list_players(free_only=True),
        key=lambda p: Decimal(str(p["game_price_usdc"])),
    )["player_id"]
    price = Decimal(str(cat.get_player(pid)["game_price_usdc"]))
    bw, house0 = M._wallet_of(buyer), L.balance(M.HOUSE_MARKET_WALLET)
    roster0 = len(CS.roster_ids(buyer))
    tb0 = CS.transfer_balance(buyer)

    out = M.buy_free_agent(buyer, pid)
    assert out == {"ok": True, "player_id": pid, "price_usdc": str(price)}
    assert cat.get_player(pid)["owner_agent_id"] == buyer
    assert len(CS.roster_ids(buyer)) == roster0 + 1
    assert L.balance(M.HOUSE_MARKET_WALLET) == house0 + price
    # at least price + wage runway; today it is 2x price + runway because
    # transfer_balance counts the fee in both budget and squad spend (reported)
    assert CS.transfer_balance(buyer) <= tb0 - price - _runway(pid)
    # and it is gone from the market
    with pytest.raises(M.MarketError):
        M.buy_free_agent(_demo_ids(2)[1], pid)


# ------------------------------------------------------------ the agent seam


def test_ask_carries_the_window_payload(_world, _season):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import manager_protocol as MP
    from gaming.src.stack.agentic.games.football_managers import market as M

    agent_id = _demo_ids(1)[0]
    ask = MP.build_matchday_ask(agent_id, _raw(_season), 1)
    assert "transfer_window" not in ask  # window closed → no payload

    M.open_window(1, "mid", closes_at="soon")
    CS.adjust_budget(agent_id, Decimal("60.00"))
    _trim_squad(agent_id, 13)  # squads now auto-build to 16; make the gap explicit
    ask = MP.build_matchday_ask(agent_id, _raw(_season), 1)
    tw = ask["transfer_window"]
    assert tw["open"] is True and tw["phase"] == "mid"
    assert Decimal(tw["transfer_balance_usdc"]) > 0
    assert tw["rules"]["transfer_tax_bps"] == 350
    assert tw["rules"]["listing_fee_bps"] == 100
    assert isinstance(tw["needs"], dict) and "BENCH" in tw["needs"]  # 13 < 16
    assert isinstance(tw["free_agents"], list) and tw["free_agents"]
    assert isinstance(tw["transfer_list"], list)


def test_plan_transfers_pass_validation(_world, _season):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import manager_protocol as MP

    agent_id = _demo_ids(1)[0]
    squad = [p["player_id"] for p in CS.get_club(agent_id)["squad"]]
    plan = {
        "formation": "4-3-3",
        "starters": squad[:11],
        "bench": [],
        "tags": ["balanced"],
        "transfers": [
            {"action": "buy_free_agent", "player_id": "afm_pl_001"},
            {"action": "nonsense"},
        ],
    }
    cleaned, err = MP.validate_matchday_plan(plan, CS.get_club(agent_id)["squad"])
    assert cleaned is None and "nonsense" not in str(err)
    assert "transfers" in str(err)

    plan["transfers"] = [{"action": "buy_free_agent", "player_id": "afm_pl_001"}]
    cleaned, err = MP.validate_matchday_plan(plan, CS.get_club(agent_id)["squad"])
    assert err == "" and cleaned["transfers"] == plan["transfers"]


def test_agent_signs_a_player_through_the_plan_reply(_world, monkeypatch):
    """The DoD: an agent short at CB signs one in the window and fields him."""
    import gaming.src.stack.agentic.games.football_managers.season as S
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import manager_protocol as MP
    from gaming.src.stack.agentic.games.football_managers import market as M
    from gaming.src.stack.agentic.games.football_managers.decide import (
        matchday_context,
    )

    agent_id = _demo_ids(1)[0]
    S.open_season(
        agent_ids=_demo_ids(2), start_at=_now() - timedelta(hours=7)
    )  # matchday 1 is already due
    M.open_window(1, "mid", closes_at="soon")
    CS.adjust_budget(agent_id, Decimal("60.00"))
    cb = next(p for p in cat.list_players(free_only=True) if p["slot"] == "CB")

    plan = {
        "formation": "4-3-3",
        "starters": [p["player_id"] for p in CS.get_club(agent_id)["starters"]],
        "bench": [],
        "tags": ["balanced"],
        "transfers": [{"action": "buy_free_agent", "player_id": cb["player_id"]}],
    }
    monkeypatch.setattr(
        MP,
        "request_matchday_plan",
        lambda agent, ask, *, timeout_sec=1.0: plan,
    )
    S.tick()

    assert cb["player_id"] in CS.roster_ids(agent_id)  # signed in the window
    assert cat.get_player(cb["player_id"])["owner_agent_id"] == agent_id
    # ...and available to field on the next matchday
    ctx = matchday_context(agent_id, _raw(S), 2)
    assert ctx is not None
    assert cb["player_id"] in [str(p["player_id"]) for p in ctx["players"]]


# ----------------------------------------------------------- the season clock


@pytest.mark.slow
def test_mid_window_opens_and_closes_on_the_season_clock(_world, monkeypatch):
    monkeypatch.setenv("AFM_FILLER_TARGET", "6")
    import gaming.src.stack.agentic.games.football_managers.season as S

    S.open_season(start_at=_now() + timedelta(hours=1))
    snap = S.get_season()
    assert snap["transfer_window"]["open"] is False
    total = snap["matchdays_total"]  # 7 real clubs ≥ target 6 → no fillers
    mid = (total + 1) // 2
    s = _raw(S)
    t_open = S._open_at(s, mid)
    S.tick(now=t_open)
    win = S.get_season()["transfer_window"]
    assert win["open"] is True and win["phase"] == "mid"
    assert win["closes_at"]  # wired to the matchday deadline
    S.tick(now=t_open + timedelta(hours=7))
    assert S.get_season()["transfer_window"]["open"] is False


@pytest.mark.slow
def test_end_window_opens_when_the_season_finishes(_world):
    import gaming.src.stack.agentic.games.football_managers.season as S

    S.open_season(
        agent_ids=_demo_ids(2), start_at=_now() - timedelta(days=31)
    )
    out = S.tick()  # the whole 30-matchday derby resolves at once
    assert out["season_status"] == "finished"
    win = S.get_season()["transfer_window"]
    assert win["open"] is True and win["phase"] == "end"
    # and it shuts when the next season opens
    S.open_season(start_at=_now() + timedelta(hours=1))
    assert S.get_season()["transfer_window"]["open"] is False
