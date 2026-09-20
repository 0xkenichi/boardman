"""AFM pre-match board: season.prematch_view — the spectator-facing read of
both managers' locked plans for one fixture (formation, tags, XI, pre-committed
HT contingency plans, ban/injury news), plus the API contract.

Reuses the two-club universe from the season suite (demo registry + seeded
clubs under a tmp store).
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
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()

    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )

    seed_demo_clubs()
    return reg


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def _open_season(_world):
    """Season 1 with matchday 1 open (managers already decided at open).

    MD1 opens at `start_at` and locks 6h later — starting 1h ago leaves the
    window open and decided, not yet resolved.
    """
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=1),
    )
    S.tick()  # opens MD1 → managers decide
    return S


def _fixture(_open_season):
    snap = _open_season.get_season()
    md = int(snap["current_matchday"])
    home = snap["division"][0]["agent_id"]
    away = snap["division"][1]["agent_id"]
    return md, home, away


def test_prematch_after_open_carries_both_plans(_open_season):
    S = _open_season
    md, home, away = _fixture(_open_season)
    view = S.prematch_view(md, home, away)

    assert view["matchday"] == md
    assert view["season_no"] == 1
    assert view["home"]["agent_id"] == home
    assert view["away"]["agent_id"] == away
    # managers decide at open → both sides are decided with a legal XI
    assert view["home"]["decided"] and view["away"]["decided"]
    for side in (view["home"], view["away"]):
        assert len(side["xi"]) == 11
        assert all(row["name"] and row["slot"] for row in side["xi"])
        assert side["formation"] in (
            "4-3-3", "4-2-3-1", "4-4-2", "3-5-2", "5-3-2", "4-1-4-1", "3-4-3",
        )
        assert isinstance(side["tags"], list)
        # plans ride along even when the playbook supplied none (empty dict ok)
        assert isinstance(side["plans"], dict)


def test_prematch_is_spectator_safe(_open_season):
    """The board never leaks hidden state: no attribute numbers, no ratings,
    no wages — names, slots, formations, tags and news only."""
    S = _open_season
    md, home, away = _fixture(_open_season)
    view = S.prematch_view(md, home, away)

    banned_keys = {"base_rating", "rating", "wage", "attributes", "condition", "xg"}
    for side in (view["home"], view["away"]):
        assert banned_keys.isdisjoint(side.keys())
        for row in side["xi"]:
            assert banned_keys.isdisjoint(row.keys())
        for n in side["news"]:
            assert set(n.keys()) == {"type", "player_id", "name", "detail"}


def test_prematch_before_open_projects_window_with_empty_sides(_world):
    """An un-opened matchday still lists: projected window, empty sides."""
    from gaming.src.stack.agentic.games.football_managers import season as S

    # open a season that starts far in the future — MD1 is not open yet
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() + timedelta(days=30),
    )
    home, away = "agent_bluelock_demo", "agent_aoashi_demo"
    view = S.prematch_view(1, home, away)

    assert view["status"] == "scheduled"
    assert view["home"]["decided"] is False
    assert view["away"]["xi"] == []
    # window is projected from the schedule, not missing
    assert view["open_at"] and view["deadline_at"]


def test_prematch_carries_decided_plans(_open_season):
    """When a manager pre-commits HT plans at decide time, they surface."""
    S = _open_season
    md, home, away = _fixture(_open_season)
    plans = {"trailing": {"formation": "4-2-3-1", "tags": ["high_press"]}}
    # record the decision the way _agents_decide stores it (with plans)
    s = S._state()["season"]
    s["matchdays"][str(md)]["decisions"][home] = {
        "formation": "4-3-3",
        "tags": ["counter"],
        "xi": _any_xi(home),
        "plans": plans,
    }
    S._save({"season": s})

    view = S.prematch_view(md, home, away)
    assert view["home"]["plans"]["trailing"]["formation"] == "4-2-3-1"
    assert view["home"]["tags"] == ["counter"]


def _any_xi(agent_id: str) -> list[str]:
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    club = get_club(agent_id) or {}
    return [str(p.get("player_id")) for p in (club.get("starters") or club.get("squad"))[:11]]


def test_prematch_rejects_unknown_fixture(_open_season):
    S = _open_season
    with pytest.raises(ValueError, match="no fixture"):
        S.prematch_view(1, "agent_bluelock_demo", "agent_nonexistent")
    with pytest.raises(ValueError, match="out of range"):
        S.prematch_view(999, "agent_bluelock_demo", "agent_aoashi_demo")


def test_prematch_works_after_resolution(_open_season):
    """The board survives resolution — a late viewer reads the shape the
    match was actually played in."""
    S = _open_season
    md, home, away = _fixture(_open_season)
    # force-resolve: rewind the season start so the lock deadline has passed
    # (deadlines are computed from started_at at tick time)
    s = S._state()["season"]
    s["started_at"] = (_now() - timedelta(days=2)).isoformat()
    S._save({"season": s})
    S.tick()

    assert S.get_season()["status"] in ("open", "finished")
    view = S.prematch_view(md, home, away)
    assert view["status"] == "played"
    assert view["home"]["decided"] and view["away"]["decided"]


# ------------------------------------------------------------------ API layer

def test_api_prematch_endpoint(_world, monkeypatch):
    """GET /football/season/prematch returns the board wrapped in `prematch`."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from gaming.src.stack.agentic import api as api_mod
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=1),
    )
    S.tick()

    app = FastAPI()
    app.include_router(api_mod.router)
    client = TestClient(app)
    res = client.get(
        "/api/stack/agentic/football/season/prematch",
        params={"matchday": 1, "home": "agent_bluelock_demo", "away": "agent_aoashi_demo"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["prematch"]["matchday"] == 1
    assert {body["prematch"]["home"]["agent_id"], body["prematch"]["away"]["agent_id"]} == {
        "agent_bluelock_demo",
        "agent_aoashi_demo",
    }

    # unknown fixture → 404
    res404 = client.get(
        "/api/stack/agentic/football/season/prematch",
        params={"matchday": 1, "home": "agent_bluelock_demo", "away": "agent_nope"},
    )
    assert res404.status_code == 404
