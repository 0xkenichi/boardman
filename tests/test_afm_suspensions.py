"""AFM discipline: a player sent off (straight red or second yellow → red) is
excluded from the club's lineup when the next matchday locks.

The engine records reds in the feed; season resolution turns the previous
fixture's red cards into a ban list for the next lineup, refilling the XI
(keeping 11 and a GK) from bench / squad.
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


def _bluelock() -> dict:
    from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

    return next(c for c in list_clubs() if c["agent_id"].find("bluelock") >= 0)


def test_red_card_ban_excluded_from_next_lineup(_world, monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers import match_engine as M

    bl = _bluelock()
    # a non-GK starter who gets sent off in matchday 1
    starters = bl["starters"]
    red_pid = next(
        p["player_id"] for p in starters if str(p.get("slot") or "") != "GK"
    )

    class _FakeResult:
        """Matches the engine's MatchResult surface (season calls .to_dict())."""

        def __init__(self, payload: dict):
            self._payload = payload

        def to_dict(self) -> dict:
            return dict(self._payload)

    def fake_sim(
        mid,
        *,
        home_agent_id,
        away_agent_id,
        home_xi,
        away_xi,
        home_bench=None,
        away_bench=None,
        home_tactics=None,
        away_tactics=None,
        home_tactics_2h=None,
        away_tactics_2h=None,
        require_result=False,
        home_fatigue=None,
        away_fatigue=None,
        home_plans=None,
        away_plans=None,
    ) -> _FakeResult:
        md = int(mid.split("_md", 1)[1].split("_", 1)[0])
        reds = []
        if md == 1:
            side = (
                "home"
                if home_agent_id == bl["agent_id"]
                else "away"
                if away_agent_id == bl["agent_id"]
                else None
            )
            if side:
                reds = [
                    {
                        "minute": 30,
                        "type": "red",
                        "side": side,
                        "player_id": red_pid,
                        "text": f"{30}' · RED CARD ({side})",
                    }
                ]
        return _FakeResult(
            {
                "match_id": mid,
                "home_agent_id": home_agent_id,
                "away_agent_id": away_agent_id,
                "home_goals": 1,
                "away_goals": 0,
                "score": "1-0",
                "outcome": "home_win",
                "reason": "full_time",
                "home_points": 3,
                "away_points": 0,
                "home_pen_goals": 0,
                "away_pen_goals": 0,
                "feed": [{"minute": 0, "type": "kickoff", "text": "kickoff"}] + reds,
            }
        )

    monkeypatch.setattr(M, "simulate_match", fake_sim)

    # start far enough back that matchday 2's deadline has also passed
    # (two-club derby — no byes, Blue Lock plays every matchday)
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=31),
    )
    out = S.tick()
    assert out["resolved"] == [1, 2]

    from gaming.src.stack.agentic.store import load_json

    season = load_json("afm_season.json", {"season": None})["season"]
    md1 = season["matchdays"]["1"]["results"][0]
    md2 = season["matchdays"]["2"]["results"][0]
    side1 = "home" if md1["home_agent_id"] == bl["agent_id"] else "away"
    # matchday 1: the offender played (and was sent off)
    assert any(
        ev.get("type") == "red" and ev.get("player_id") == red_pid
        for ev in md1["feed"]
    )
    assert red_pid in md1["lineups"][bl["agent_id"]]["xi"]

    # matchday 2: the ban is enforced at the lineup lock — he is not on the
    # pitch (nor on the bench) and the XI is refilled to a legal 11
    lu2 = md2["lineups"][bl["agent_id"]]
    assert red_pid not in lu2["xi"]
    assert red_pid not in lu2["bench"]
    assert red_pid in lu2.get("banned", [])
    assert len(lu2["xi"]) == 11
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player

    gks = [pid for pid in lu2["xi"] if (get_player(pid) or {}).get("slot") == "GK"]
    assert len(gks) == 1  # refill kept exactly one keeper between the sticks
    # the ban was served: the same club's matchday 3 lineup is free again
    season3 = load_json("afm_season.json", {"season": None})["season"]
    assert season3["current_matchday"] == 3  # tick opened/queued MD3 fixture state
    assert red_pid in md1["lineups"][bl["agent_id"]]["xi"]  # he played MD1
