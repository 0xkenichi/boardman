"""AFM spectator betting — parimutuel pot math, settle conservation, guards."""
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
def _open_season():
    """A 3-club season opened one hour ago (betting window live)."""
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )

    seed_demo_clubs()
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.league import (
        schedule_season,
    )

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo", "agent_matchslice_demo"],
        start_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    season = S._state()["season"]
    fx = schedule_season(season["division"])[0][0]
    return S, int(season["season_no"]), fx.home_agent_id, fx.away_agent_id


def _fund(better: str) -> None:
    """A spectator's real deposit — humans are never faucet-funded."""
    from gaming.src.stack.agentic import ledger as L

    L.credit(better, Decimal("100"), reason="test_deposit")


def test_place_bet_pools_and_prices(_open_season):
    S, sn, home, away = _open_season
    from gaming.src.stack.agentic.games.football_managers.betting import (
        current_odds,
        place_bet,
    )

    _fund("spec_a")
    _fund("spec_b")
    place_bet("spec_a", sn, 1, home, away, "home", "5")
    place_bet("spec_b", sn, 1, home, away, "away", "5")
    board = current_odds(sn, 1, home, away)
    assert board["pot_total"] == "10.00"
    assert board["pot"]["home"] == "5.00" and board["pot"]["away"] == "5.00"
    # even split: both backed sides pay 10 * 0.93 / 5
    assert board["odds"]["home"] == "1.86"
    assert board["odds"]["draw"] == "0"  # nobody backed the draw


def test_bet_guards_window_side_and_cap(_open_season, monkeypatch):
    S, sn, home, away = _open_season
    from gaming.src.stack.agentic.games.football_managers.betting import place_bet

    _fund("spec_a")
    with pytest.raises(ValueError, match="side"):
        place_bet("spec_a", sn, 1, home, away, "homey", "5")
    with pytest.raises(ValueError, match="maximum"):
        place_bet("spec_a", sn, 1, home, away, "home", "51")
    with pytest.raises(ValueError, match="minimum"):
        place_bet("spec_a", sn, 1, home, away, "home", "0.5")
    with pytest.raises(ValueError, match="no such fixture"):
        place_bet("spec_a", sn, 99, home, away, "home", "5")

    # after the deadline the book shuts — move the season clock (the guard
    # reads the season's _deadline, derived from open_at + lock_hours)
    from gaming.src.stack.agentic.games.football_managers import season as SS

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    monkeypatch.setattr(SS, "_deadline", lambda s, md: past)
    with pytest.raises(ValueError, match="closed"):
        place_bet("spec_a", sn, 1, home, away, "home", "5")


def test_settle_splits_pot_and_conserves_money(_open_season):
    S, sn, home, away = _open_season
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.betting import (
        place_bet,
        settle_matchday,
    )

    for b in ("spec_a", "spec_b", "spec_c"):
        _fund(b)
    place_bet("spec_a", sn, 1, home, away, "home", "5")
    place_bet("spec_b", sn, 1, home, away, "home", "3")
    place_bet("spec_c", sn, 1, home, away, "away", "2")

    pre = {b: L.balance(b) for b in ("spec_a", "spec_b", "spec_c")}
    results = [{"home_agent_id": home, "away_agent_id": away, "home_goals": 2, "away_goals": 1}]
    out = settle_matchday(sn, 1, results)
    assert out and out[0]["winning_side"] == "home"
    post = {b: L.balance(b) for b in ("spec_a", "spec_b", "spec_c")}

    # `pre` is post-bets, so the settle effect is: winners paid pro-rata from
    # the 10 pot minus the 0.70 fee; the loser's stake was already debited
    assert float(post["spec_a"] - pre["spec_a"]) == pytest.approx(9.30 * 5 / 8, abs=1e-6)
    assert float(post["spec_b"] - pre["spec_b"]) == pytest.approx(9.30 * 3 / 8, abs=1e-6)
    assert float(post["spec_c"] - pre["spec_c"]) == pytest.approx(0.0, abs=1e-6)
    # money is conserved: the winners' gain is exactly the pot minus the fee
    gained = float((post["spec_a"] - pre["spec_a"]) + (post["spec_b"] - pre["spec_b"]))
    assert gained == pytest.approx(9.30, abs=1e-6)


def test_settle_is_idempotent(_open_season):
    S, sn, home, away = _open_season
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.betting import (
        place_bet,
        settle_matchday,
    )

    _fund("spec_a")
    place_bet("spec_a", sn, 1, home, away, "home", "5")
    results = [{"home_agent_id": home, "away_agent_id": away, "home_goals": 0, "away_goals": 0}]
    first = settle_matchday(sn, 1, results)
    assert first  # draw book: away+home stakes → draw won; nobody backed it
    bal = L.balance("spec_a")
    again = settle_matchday(sn, 1, results)
    assert again == []  # book already settled
    assert L.balance("spec_a") == bal


def test_season_resolve_settles_the_books(_open_season):
    S, sn, home, away = _open_season
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.betting import (
        place_bet,
    )

    _fund("spec_a")
    place_bet("spec_a", sn, 1, home, away, "home", "5")
    S.tick(datetime.now(timezone.utc) + timedelta(hours=6, minutes=1))
    st = S._state()
    md = st["season"]["matchdays"]["1"]
    assert md.get("betting_settlements"), "resolve did not settle the books"
    book_side = md["betting_settlements"][0]["winning_side"]
    assert book_side in ("home", "draw", "away")


def test_short_pot_never_pays_winners_from_nothing(_open_season):
    """Ledger drift (the fixture pot holds less than its book) parks the book
    instead of crediting winners money the pot never had."""
    S, sn, home, away = _open_season
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import betting as B

    _fund("spec_a")
    _fund("spec_b")
    B.place_bet("spec_a", sn, 1, home, away, "home", "5")
    B.place_bet("spec_b", sn, 1, home, away, "away", "5")
    pot = f"afm_fixture_s{sn}_md1_{home}_{away}"
    L.debit(pot, Decimal("6"), reason="test_drift")  # pot now short

    results = [{"home_agent_id": home, "away_agent_id": away, "home_goals": 1, "away_goals": 0}]
    B.settle_matchday(sn, 1, results)
    assert L.balance("spec_a") == Decimal("95")  # no payout minted
    assert L.balance("spec_b") == Decimal("95")
    assert L.balance(pot) == Decimal("4")  # untouched: the whole settle rolled back
    book = next(iter(B._load()["fixtures"].values()))
    assert book["status"] == "settle_failed"
