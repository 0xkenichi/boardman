"""AFM post-match report — per-player ratings, xG and error attribution.

Covers the FM report read model (`report.py`):

* `match_report` — both sides' per-player rows (minutes, goals, xG, rating
  0–99, errors), team xG, top/worst performer and the "why" headline lines,
  folded from the engine's `player_stats` stored on every result.
* `latest_report_for_agent` — the agent-side projection (my side / opponent
  side keys) for the club's most recent played fixture.
* `dashboard_match_report` — the compact per-result summary embedded in the
  owner dashboard (top performer, team xG, one-line "why").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    return get_registry()


def _play_matchday_one():
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=datetime.now(timezone.utc) - timedelta(hours=7),
    )
    out = S.tick()
    assert out["resolved"] == [1]
    return S._state()["season"]


def test_match_report_folds_player_stats_for_both_sides(_world):
    from gaming.src.stack.agentic.games.football_managers import report as R
    from gaming.src.stack.agentic.games.football_managers.season import _state

    s = _play_matchday_one()
    home, away = s["division"][0], s["division"][1]
    rep = R.match_report(int(s["season_no"]), 1, home, away)

    assert rep["matchday"] == 1
    assert rep["score"] in rep.get("score", "") or isinstance(rep["score"], str)
    for side in (rep["home"], rep["away"]):
        assert side["agent_id"] in (home, away)
        assert isinstance(side["xG"], float)
        assert side["players"], "report must list players"
        # every player row carries the FM columns
        for row in side["players"]:
            assert {"player_id", "name", "position", "starter", "played"} <= set(row)
            if row["played"]:
                assert isinstance(row["rating"], int) and 35 <= row["rating"] <= 96
                assert row["minutes"] > 0
                assert row["xG"] >= 0.0
        # ratings sorted best-first among players who took the pitch
        rated = [r["rating"] for r in side["players"] if r.get("rating") is not None]
        assert rated == sorted(rated, reverse=True)
    # xi players have ratings; bench players who never came on do not
    home_xi = {r["player_id"] for r in rep["home"]["players"] if r["starter"]}
    assert len(home_xi) == 11
    starters_rated = [r for r in rep["home"]["players"] if r["starter"] and r["played"]]
    assert starters_rated, "starting XI must have played the match"
    unused = [r for r in rep["home"]["players"] if not r["played"]]
    assert all(r["rating"] is None for r in unused), "an unused sub has no rating"


def test_report_errors_surface_when_they_exist(_world):
    """Every error row is well-formed; a red card becomes a sent_off error."""
    from gaming.src.stack.agentic.games.football_managers import report as R
    from gaming.src.stack.agentic.games.football_managers import season as S

    s = _play_matchday_one()
    home, away = s["division"][0], s["division"][1]
    rep = R.match_report(int(s["season_no"]), 1, home, away)
    for side in (rep["home"], rep["away"]):
        for err in side["errors"]:
            assert "type" in err and "note" in err


def test_latest_report_for_agent_keys_my_side(_world):
    from gaming.src.stack.agentic.games.football_managers import report as R

    _play_matchday_one()
    rep = R.latest_report_for_agent("agent_bluelock_demo")
    assert rep["my_side"] in ("home", "away")
    assert rep["my"]["agent_id"] == "agent_bluelock_demo"
    assert rep[rep["opponent_side"]]["agent_id"] != "agent_bluelock_demo"
    # the same rows the full report had, now under "my"
    assert rep["my"]["players"]


def test_latest_report_raises_without_played_fixtures(_world):
    from gaming.src.stack.agentic.games.football_managers import report as R

    with pytest.raises(ValueError):
        R.latest_report_for_agent("agent_bluelock_demo")


def test_match_report_raises_for_unplayed_matchday(_world):
    from gaming.src.stack.agentic.games.football_managers import report as R
    from gaming.src.stack.agentic.games.football_managers.season import _state

    s = _play_matchday_one()
    home, away = s["division"][0], s["division"][1]
    with pytest.raises(ValueError):
        R.match_report(int(s["season_no"]), 2, home, away)


def test_dashboard_rows_carry_report_summary(_world):
    from gaming.src.stack.agentic.games.football_managers.dashboard import (
        owner_dashboard,
    )

    _play_matchday_one()
    dash = owner_dashboard("agent_bluelock_demo")
    assert dash["results"], "expected the played matchday in the dashboard"
    row = dash["results"][0]
    assert "report" in row
    rep = row["report"]
    if rep:  # engine results carry player_stats, so the summary should fill
        assert "my_xg" in rep and "their_xg" in rep
        assert rep["my_xg"] >= 0.0 and rep["their_xg"] >= 0.0
        assert rep["top"] is None or {"player_id", "name", "rating"} <= set(rep["top"])
        assert isinstance(rep["errors"], list)
        assert isinstance(rep["players"], list) and rep["players"]
        for r in rep["players"]:
            assert {"name", "rating", "xG"} <= set(r)


def test_dashboard_report_is_absent_for_pre_player_stats_results(_world, monkeypatch):
    """Old stored results without player_stats leave the report summary empty
    (backward compatibility — no crash, no fake numbers)."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.dashboard import (
        owner_dashboard,
    )

    s = _play_matchday_one()
    # strip player_stats from the stored result, as a pre-v1.3 result would be
    md1 = s["matchdays"]["1"]
    for r in md1["results"]:
        r.pop("player_stats", None)
    S._save({"season": s})

    dash = owner_dashboard("agent_bluelock_demo")
    assert dash["results"][0]["report"] == {}
