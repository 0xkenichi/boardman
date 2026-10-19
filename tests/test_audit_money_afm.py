"""Money audit 2026-10 — AFM marketplace, AFM betting, wallet bridge.

PoCs for AUDIT_2026-10_money.md:

* M-03  Two buyers (or a buy and a delist) racing on one listing: both were
        charged and the seller was paid twice for one manager.
* M-04  A stake with sub-micro digits was debited rounded but booked raw:
        the book claimed more than the pot held and the whole fixture parked
        as settle_failed, freezing every honest bettor's stake.
* M-05  Book-entry money crossing into the mainnet realm: AFM bets and the
        football-wallet -> play-balance withdraw were open on mainnet.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    for name in ("NETWORK", "CLAW_DEFAULT_CHAIN", "BOARDMAN_SETTLEMENT_RAIL", "SPECTATOR_CHAIN"):
        monkeypatch.delenv(name, raising=False)
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


# ── M-03 marketplace ─────────────────────────────────────────────────────────


@pytest.fixture()
def listing(monkeypatch):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import agent_market as M
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    aid = M.create_manager_agent(manager_name="Race FC", archetype="possession", owner_id="dev_x")["agent"]["agent_id"]
    M.list_manager_for_sale(agent_id=aid, price_usdc="30.00", listed_by="dev_x")
    for b in ("buyer_a", "buyer_b"):
        L.credit(f"owner:{b}", Decimal("30"), reason="test_deposit")
    real = M._execute_sale

    def _slow(*a, **k):  # the on-chain rail waits seconds for Circle
        time.sleep(0.3)
        return real(*a, **k)

    monkeypatch.setattr(M, "_execute_sale", _slow)
    return aid


def _race(*calls):
    gate = threading.Barrier(len(calls))
    errs: list[Exception] = []

    def _run(fn):
        gate.wait()
        try:
            fn()
        except Exception as exc:  # the loser is refused, that is the point
            errs.append(exc)

    ts = [threading.Thread(target=_run, args=(c,)) for c in calls]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return errs


def _owner(aid: str) -> str:
    from gaming.src.stack.agentic.store import load_json

    return str(load_json("agents.json", {"agents": {}})["agents"][aid].get("owner_id"))


def test_two_buyers_one_manager_one_payment(listing):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import agent_market as M

    errs = _race(
        lambda: M.purchase_manager_agent(agent_id=listing, buyer_id="buyer_a"),
        lambda: M.purchase_manager_agent(agent_id=listing, buyer_id="buyer_b"),
    )
    assert len(errs) == 1, errs
    assert L.balance("owner:dev_x") == Decimal("30")
    paid = [b for b in ("buyer_a", "buyer_b") if L.balance(f"owner:{b}") == Decimal("0")]
    assert len(paid) == 1
    assert _owner(listing) == paid[0]


def test_buy_racing_delist_never_keeps_both(listing, monkeypatch):
    """The delist loads the record, the buy settles and saves, then the
    delist saves its stale copy: seller keeps the money AND the manager."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import agent_market as M

    real_log = M._log_market_event

    def _slow_log(a, kind, **kw):
        if kind == "delisted":
            time.sleep(0.6)
        return real_log(a, kind, **kw)

    monkeypatch.setattr(M, "_log_market_event", _slow_log)
    _race(
        lambda: M.delist_manager_agent(agent_id=listing, listed_by="dev_x"),
        lambda: (time.sleep(0.05), M.purchase_manager_agent(agent_id=listing, buyer_id="buyer_a")),
    )
    charged = L.balance("owner:buyer_a") == Decimal("0")
    # Either the sale happened (buyer owns it) or nothing was charged.
    assert (_owner(listing) == "buyer_a") == charged
    assert L.balance("owner:dev_x") == (Decimal("30") if charged else Decimal("0"))


# ── M-04 AFM betting precision ───────────────────────────────────────────────


@pytest.fixture()
def fixture_open():
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.games.football_managers.league import schedule_season
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo", "agent_matchslice_demo"],
        start_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    sn = int(S._state()["season"]["season_no"])
    fx = schedule_season(S._state()["season"]["division"])[0][0]
    return sn, fx.home_agent_id, fx.away_agent_id


def test_sub_micro_stakes_cannot_freeze_a_fixture(fixture_open):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import betting as B

    sn, h, a = fixture_open
    L.credit("victim", Decimal("50"), reason="t")
    L.credit("griefer", Decimal("5"), reason="t")
    B.place_bet("victim", sn, 1, h, a, "home", "50")
    B.place_bet("griefer", sn, 1, h, a, "away", "1.0000005")
    B.place_bet("griefer", sn, 1, h, a, "away", "1.0000005")
    B.settle_matchday(sn, 1, [{"home_agent_id": h, "away_agent_id": a, "home_goals": 2, "away_goals": 0}])
    book = B._load()["fixtures"][B._fixture_key(sn, 1, h, a)]
    from gaming.src.stack.agentic.party_wallet import football_wallet

    assert book["status"] == "settled", book.get("error")
    # pot 52 (50 + 2 x 1.000000) minus the 7% fee, all to the only winner
    assert L.balance(football_wallet("victim")) == Decimal("48.36")
    assert L.balance(f"afm_fixture_s{sn}_md1_{h}_{a}") == Decimal("0")


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_bets_are_refused(fixture_open, raw):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import betting as B

    sn, h, a = fixture_open
    L.credit("fan", Decimal("10"), reason="t")
    with pytest.raises(ValueError):
        B.place_bet("fan", sn, 1, h, a, "home", raw)
    assert L.balance("fan") == Decimal("10")


def test_bets_record_a_deadline_for_the_stale_book_guard(fixture_open):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import betting as B

    sn, h, a = fixture_open
    L.credit("fan", Decimal("10"), reason="t")
    B.place_bet("fan", sn, 1, h, a, "home", "2")
    assert B._load()["fixtures"][B._fixture_key(sn, 1, h, a)].get("deadline_at")


# ── M-05 realm separation ────────────────────────────────────────────────────


def test_afm_bets_refused_on_mainnet_even_with_the_switch_on(fixture_open, monkeypatch):
    from gaming.src.backend.services.spectator_policy import SpectatorBettingUnavailable
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import betting as B

    sn, h, a = fixture_open
    L.credit("fan_main", Decimal("10"), reason="t")
    monkeypatch.setenv("NETWORK", "mainnet")
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "1")
    monkeypatch.setattr(
        "gaming.src.backend.services.spectator_policy.assert_spectator_betting_allowed", lambda **_k: None
    )
    with pytest.raises(SpectatorBettingUnavailable):
        B.place_bet("fan_main", sn, 1, h, a, "home", "2")
    assert L.balance("fan_main") == Decimal("10")


def test_bridge_withdraw_refused_on_mainnet(monkeypatch):
    from gaming.src.backend.services import play_adjust
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic import wallet_bridge as wb

    L.credit(wb.party_ledger_wallet("p_main"), Decimal("25"), reason="legacy")
    monkeypatch.setenv("NETWORK", "mainnet")
    with pytest.raises(wb.BridgeError):
        wb.withdraw("p_main", "25", "wd-main-1")
    assert play_adjust.get_adjust("p_main") == Decimal("0")
    assert L.balance(wb.party_ledger_wallet("p_main")) == Decimal("25")
