"""AFM spatial overlay (engine v1.1): every event carries x/y/z/facing/actor_id.

The overlay is a pure, deterministic post-processing fold keyed on
(match_id, event index) — it must never change match outcomes (it does not
consume the match RNG) and must reproduce byte-identical coordinates for the
same seed. Placement must be football-shaped: kickoff centre, goals in the
box, corners at the flag, penalties on the spot.
"""
from __future__ import annotations

import pytest

from gaming.src.stack.agentic.games.football_managers import match_engine as M

_SLOTS = ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW"]


def _squad(side: str, rating: float) -> tuple[list[str], list[str], dict]:
    players: dict[str, dict] = {}
    xi: list[str] = []
    for i, slot in enumerate(_SLOTS):
        pid = f"{side}_xi_{i + 1}"
        players[pid] = {"player_id": pid, "name": f"{side} {i + 1}", "slot": slot,
                        "base_rating": rating, "form": 7.0}
        xi.append(pid)
    return xi, [], players


_H_XI, _, _H_PL = _squad("h", 92.0)
_A_XI, _, _A_PL = _squad("a", 62.0)
_ALL = {**_H_PL, **_A_PL}


@pytest.fixture()
def _fake_players(monkeypatch):
    def get(player_id):
        return _ALL.get(player_id)

    monkeypatch.setattr(M, "get_player", get)
    return get


def _run(match_id, **kw) -> M.MatchResult:
    return M.simulate_match(
        match_id,
        home_agent_id="home",
        away_agent_id="away",
        home_xi=_H_XI,
        away_xi=_A_XI,
        **kw,
    )


def _pos(ev) -> tuple[float, float, float]:
    return ev["x"], ev["y"], ev["z"]


def test_same_seed_reproduces_identical_positions(_fake_players):
    a = _run("spatial_det").to_dict()["feed"]
    b = _run("spatial_det").to_dict()["feed"]
    assert [_pos(e) for e in a] == [_pos(e) for e in b]
    assert [e["facing"] for e in a] == [e["facing"] for e in b]
    assert [e["actor_id"] for e in a] == [e["actor_id"] for e in b]


def test_every_event_carries_spatial_fields_within_bounds(_fake_players):
    feed = _run("spatial_bounds").to_dict()["feed"]
    assert feed
    for ev in feed:
        assert {"x", "y", "z", "facing", "actor_id"} <= set(ev)
        assert 0.0 <= ev["x"] <= M.PITCH_LENGTH
        assert 0.0 <= ev["y"] <= M.PITCH_WIDTH
        assert 0.0 <= ev["z"] <= 5.0
        assert 0.0 <= ev["facing"] <= 360.0
        assert isinstance(ev["actor_id"], str) and ev["actor_id"]


def test_placement_is_football_shaped(_fake_players):
    """Spot checks across many seeds: kickoff centre, goals in the box,
    corners at the flag, penalties on the spot."""
    for i in range(20):
        feed = _run(f"spatial_shape_{i}").to_dict()["feed"]
        ko = feed[0]
        assert ko["type"] == "kickoff"
        assert abs(ko["x"] - M.PITCH_LENGTH / 2.0) < 0.01
        assert abs(ko["y"] - M.PITCH_WIDTH / 2.0) < 0.01

        for ev in feed:
            t, side = ev["type"], ev.get("side")
            if t == "goal":
                goal_x = M._GOAL_X[side]
                # goals are scored from inside the attacking box (≤16.5m out)
                box_depth = abs(M._BOX_OUTER[side] - M._BOX_INNER[side])
                assert abs(ev["x"] - goal_x) <= box_depth + 0.1
                assert 0.0 <= ev["y"] <= M.PITCH_WIDTH
            elif t == "corner":
                assert abs(ev["x"] - M._GOAL_X[side]) < 0.01
                # corners sit within ~4m of a flag (width is 68m)
                assert ev["y"] <= 68.0 * 0.16 or ev["y"] >= 68.0 * 0.84
            elif t == "penalty":
                assert abs(ev["x"] - M._SPOT_X[side]) < 0.01
                assert abs(ev["y"] - M.PITCH_WIDTH / 2.0) < 0.01
            elif t == "throw_in":
                assert ev["y"] <= 1.0 or ev["y"] >= M.PITCH_WIDTH - 1.0


def test_spatial_overlay_is_purely_additive(_fake_players, monkeypatch):
    """With the overlay disabled, the feed is identical minus the new keys."""
    import copy

    d = _run("spatial_neutral", require_result=True).to_dict()
    stripped = []
    for ev in d["feed"]:
        e = copy.deepcopy(ev)
        for k in ("x", "y", "z", "facing", "actor_id"):
            e.pop(k, None)
        stripped.append(e)

    monkeypatch.setattr(M, "spatialize_feed", lambda feed, match_id: feed)
    raw = M.simulate_match(
        "spatial_neutral",
        home_agent_id="home",
        away_agent_id="away",
        home_xi=_H_XI,
        away_xi=_A_XI,
        require_result=True,
    ).to_dict()
    assert stripped == raw["feed"], "overlay must be additive: strip it and get the old feed back"


def test_scores_and_events_match_pre_overlay_behaviour(_fake_players):
    """Outcome distribution unchanged across seeds (spot: strong home wins)."""
    home = away = 0
    for i in range(30):
        r = _run(f"spatial_dist_{i}")
        home += r.home_goals
        away += r.away_goals
    assert home > away, "stronger home side should outscore away"


def test_possession_ball_advances_toward_attacking_goal(_fake_players):
    """Consecutive possessions of the same side drift toward that side's goal."""
    feed = _run("spatial_drift").to_dict()["feed"]
    poss = [ev for ev in feed if ev["type"] == "possession"]
    assert len(poss) >= 10
    home_delta = away_delta = 0.0
    home_n = away_n = 0
    prev = poss[0]
    for ev in poss[1:]:
        if ev["side"] == prev["side"] == "home":
            home_delta += ev["x"] - prev["x"]
            home_n += 1
        elif ev["side"] == prev["side"] == "away":
            away_delta += ev["x"] - prev["x"]
            away_n += 1
        prev = ev
    assert home_n >= 2 and away_n >= 2
    assert home_delta / home_n > 0.5, "home possession must drift toward +x"
    assert away_delta / away_n < -0.5, "away possession must drift toward −x"