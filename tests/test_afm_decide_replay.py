"""AFM manager decision loop + recorded-fixture replay."""
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
    """Registered AFM demo managers + their clubs, all under the tmp store."""
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


def _legal_xi(club) -> list[str]:
    """11 owned, healthy players with a GK — for human-override tests."""
    squad = club["squad"]
    gk = next(p for p in squad if str(p.get("slot") or "").upper() == "GK")
    rest = [p for p in squad if p["player_id"] != gk["player_id"]]
    rest.sort(key=lambda p: (float(p.get("base_rating") or 0)), reverse=True)
    return [gk["player_id"]] + [p["player_id"] for p in rest[:10]]


def test_agents_decide_legal_lineups_at_open(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    S.open_season(start_at=_now() - timedelta(hours=7))
    out = S.tick()
    assert out["resolved"] == [1]

    # a 3-club round robin gives one club a bye each matchday — the bye club
    # keeps its legal seeded lineup, the two playing clubs decided theirs
    for aid in ("agent_bluelock_demo", "agent_aoashi_demo", "agent_matchslice_demo"):
        club = get_club(aid)
        assert len(club["starters"]) == 11
        gk = [p for p in club["starters"] if str(p.get("slot") or "").upper() == "GK"]
        assert len(gk) == 1  # a legal XI always has exactly one GK
        owned = {p["player_id"] for p in club["squad"]}
        assert {p["player_id"] for p in club["starters"]} <= owned
        assert club["formation"] in {"3-4-3", "4-3-3", "4-2-3-1", "4-1-4-1"}

    # the season records what each manager decided (exactly the MD1 fixture)
    st = S._state()
    decisions = st["season"]["matchdays"]["1"]["decisions"]
    assert len(decisions) == 2
    assert set(decisions) <= {"agent_bluelock_demo", "agent_aoashi_demo", "agent_matchslice_demo"}
    for d in decisions.values():
        assert len(d["xi"]) == 11


def test_minds_set_their_tactics(_world):
    """Blue Lock attacks (3-4-3/4-3-3, pressing tags); Ao Ashi keeps shape.
    A two-club derby has no byes, so every manager's mind is visible on MD1."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    S.tick()

    bl = get_club("agent_bluelock_demo")
    aa = get_club("agent_aoashi_demo")
    assert bl["formation"] in {"3-4-3", "4-3-3"}
    assert set(bl["tactical_tags"]) <= {"gegenpress", "high_press"}  # never parks
    assert aa["formation"] in {"4-2-3-1", "4-1-4-1", "4-3-3"}
    assert set(aa["tactical_tags"]) <= {"tiki_taka", "counter"}


def test_human_override_wins_after_open_before_deadline(_world):
    """The agent decides once at open; a human edit before deadline wins."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        get_club,
        set_lineup,
    )

    S.open_season(start_at=_now() - timedelta(hours=1))
    out = S.tick(_now())  # opens MD1 + agents decide; deadline not reached
    assert out["opened"] == [1] and out["resolved"] == []

    human_xi = _legal_xi(get_club("agent_bluelock_demo"))
    set_lineup(
        "agent_bluelock_demo",
        starters=human_xi,
        bench=[p["player_id"] for p in get_club("agent_bluelock_demo")["squad"] if p["player_id"] not in human_xi][:5],
        formation="4-4-2",
        tactical_tags=["low_block"],
    )

    S.tick(_now() + timedelta(hours=8))  # deadline passed → resolve
    st = S._state()
    results = st["season"]["matchdays"]["1"]["results"]
    locked = results[0]["lineups"]["agent_bluelock_demo"]
    assert locked["xi"] == human_xi
    assert locked["formation"] == "4-4-2"
    assert locked["tags"] == ["low_block"]


def test_replay_returns_recorded_feed(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(start_at=_now() - timedelta(hours=7))
    S.tick()

    snap = S.get_season()
    fx = snap["recent"][0]
    replay = S.get_replay(1, fx["home_agent_id"], fx["away_agent_id"])

    assert replay["match_id"] == fx["match_id"]
    # the full event feed is stored and replayable (kickoff … full_time)
    feed = replay["result"]["feed"]
    assert feed and feed[0]["type"] == "kickoff"
    assert feed[-1]["type"] == "full_time" and feed[-1]["minute"] == 90
    assert len(feed) >= 10
    assert replay["result"]["score"] == fx["score"]
    # both locked XIs come back so the board can render the actual fixture
    for side in ("home", "away"):
        assert replay[side]["xi"]
        assert replay[side]["formation"]
    assert "agent_bluelock_demo" in replay["decisions"] or "agent_aoashi_demo" in replay["decisions"]


def test_replay_reconstructs_old_format_matchday(_world):
    """Pre-feed-storage matchdays reconstruct deterministically (same seed)."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.store import load_json, save_json

    S.open_season(start_at=_now() - timedelta(hours=7))
    S.tick()
    snap = S.get_season()
    fx = snap["recent"][0]

    # simulate the old format: results had no feed / lineups stored
    st = load_json("afm_season.json", {"season": None})
    results = st["season"]["matchdays"]["1"]["results"]
    for r in results:
        r.pop("feed", None)
        r.pop("lineups", None)
    save_json("afm_season.json", st)

    replay = S.get_replay(1, fx["home_agent_id"], fx["away_agent_id"])
    assert replay["result"]["score"] == fx["score"]  # same seeded match
    feed = replay["result"]["feed"]
    assert feed and feed[-1]["type"] == "full_time"
    assert len(feed) >= 10
    assert replay["home"]["xi"] and replay["away"]["xi"]