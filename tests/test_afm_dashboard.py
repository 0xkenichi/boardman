"""AFM owner dashboard — owner seat step 5: follow your club.

Covers the read model: results + the agent's locked decisions per matchday,
table position, the spending log (club budget build + ledger movements) and
suspension / injury news for the squad.
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
    """Demo AFM managers + clubs under a tmp store."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    return {"registry": get_registry()}


def _play_matchday_one():
    """Open a bluelock-vs-aoashi season and resolve MD1 (the common fixture)."""
    from gaming.src.stack.agentic.games.football_managers import season as S

    start = datetime.now(timezone.utc) - timedelta(hours=7)
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=start,
    )
    out = S.tick()
    assert out["resolved"] == [1]
    return S._state()["season"]


def _dashboard(agent_id: str) -> dict:
    from gaming.src.stack.agentic.games.football_managers.dashboard import (
        owner_dashboard,
    )

    return owner_dashboard(agent_id)


def test_dashboard_without_season_still_shows_club_and_budget(_world):
    dash = _dashboard("agent_bluelock_demo")
    assert dash["club"]["club_name"] == "Blue Lock FC"
    assert dash["manager"]["archetype"] == "striker"
    assert dash["season"] is None
    assert dash["table"]["in_season"] is False and dash["table"]["rank"] is None
    assert dash["results"] == [] and dash["upcoming"] == []
    assert dash["squad_status"]["starters"] == 11

    labels = [s["label"] for s in dash["spending"]]
    assert "Starting club budget" in labels
    assert "Squad build (on create)" in labels
    # budget rows (no ledger yet) sort to the bottom, newest first otherwise
    assert dash["spending"][-1]["label"] == "Squad build (on create)"

    assert float(dash["finances"]["budget_usdc"]) >= float(dash["finances"]["spend_usdc"])


def test_dashboard_result_lands_with_table_position(_world):
    season = _play_matchday_one()
    dash = _dashboard("agent_bluelock_demo")

    assert dash["season"]["season_no"] == season["season_no"]
    assert dash["table"]["in_season"] is True
    assert dash["table"]["rank"] in (1, 2)
    row = dash["table"]["row"]
    assert row["played"] == 1 and row["points"] in (0, 1, 3)

    assert len(dash["results"]) == 1
    r = dash["results"][0]
    assert r["matchday"] == 1
    assert r["outcome"] in ("W", "D", "L")
    assert r["opponent_club"] == "Ao Ashi FC"
    # goals agree with the standings row
    assert row["goals_for"] == r["our_goals"]
    assert row["goals_against"] == r["their_goals"]
    assert dash["form"] == r["outcome"]


def test_dashboard_carries_the_agents_locked_decisions(_world):
    _play_matchday_one()
    dash = _dashboard("agent_bluelock_demo")
    dec = dash["results"][0]["decision"]
    # Blue Lock's striker mind: attacking shapes, never parks the bus
    assert dec["formation"] in {"3-4-3", "4-3-3", "4-2-3-1"}
    assert set(dec["tags"]) <= {"gegenpress", "high_press"}
    assert len(dec["xi"]) == 11
    assert dec["auto"] is False and dec["error"] is None


def test_dashboard_spending_log_has_budget_and_season_moves(_world):
    _play_matchday_one()
    dash = _dashboard("agent_aoashi_demo")
    spend = dash["spending"]

    labels = [s["label"] for s in spend]
    assert "Starting club budget" in labels
    assert "Squad build (on create)" in labels
    assert "Demo faucet (bankroll)" in labels
    assert "Season entry fee" in labels
    assert "Matchday wages" in labels
    assert any("Matchday stake" in l for l in labels)
    assert any("Season 1" in (s.get("detail") or "") or "MD 1" in s.get("label", "") for s in spend)

    # every ledger entry is a signed, parseable amount and no money vanishes
    for s in spend:
        assert s["amount"] is not None and s["amount"] != "0"
        Decimal(s["amount"])

    # newest first: ledger rows (timestamps) above the budget rows (ts = "")
    ledger_ts = [s["ts"] for s in spend if s["kind"] == "ledger"]
    assert ledger_ts == sorted(ledger_ts, reverse=True)

    assert Decimal(dash["finances"]["wallet_balance_usdc"]) > 0


def test_dashboard_news_flags_injuries_and_suspensions(_world):
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    _play_matchday_one()
    club = get_club("agent_bluelock_demo")
    squad = club["squad"]
    inj_pid = squad[0]["player_id"]
    sus_pid = next(p["player_id"] for p in squad if p["player_id"] != inj_pid)

    try:
        cat._catalog[inj_pid]["injury"] = "hamstring strain"
        cat._catalog[sus_pid]["suspension_matches"] = 2
        dash = _dashboard("agent_bluelock_demo")
    finally:
        cat._catalog[inj_pid]["injury"] = None
        cat._catalog[sus_pid]["suspension_matches"] = 0

    kinds = [n["type"] for n in dash["news"]]
    assert "injury" in kinds and "suspension" in kinds
    inj = next(n for n in dash["news"] if n["type"] == "injury")
    assert "hamstring" in inj["detail"] and inj["player_id"] == inj_pid
    sus = next(n for n in dash["news"] if n["type"] == "suspension" and n["player_id"] == sus_pid)
    assert "2 matchdays" in sus["detail"]
    assert dash["squad_status"]["injured"] == 1
    # suspended counts the flagged player + anyone banned by a MD1 red card
    assert dash["squad_status"]["suspended"] >= 1
    assert (
        dash["squad_status"]["available"]
        == dash["squad_status"]["total"] - dash["squad_status"]["injured"] - dash["squad_status"]["suspended"]
    )


def test_dashboard_rejects_clubless_agent(_world):
    with pytest.raises(ValueError, match="no AFM club"):
        _dashboard("agent_raja_kia_alekhine")  # chess-only agent, never owns an AFM club
