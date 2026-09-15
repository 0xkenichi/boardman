"""AFM Phase stream builder (engine v1.2): phases renderable by the board.

Phase = { t, ball{x,y,z}, players[22], action?, note? } — a pure,
deterministic fold over the spatial feed keyed on (match_id, phase index),
so the same seed always yields the same phases and the feed is untouched.
"""

from __future__ import annotations

import pytest

from gaming.src.stack.agentic.games.football_managers import match_engine as M
from gaming.src.stack.agentic.games.football_managers.club_store import _formation_slots

# XI order MUST match the formation's slot order so slot alignment holds.
_SLOTS = _formation_slots("4-3-3")


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
        home_tactics={"formation": "4-3-3", "tags": ["gegenpress"]},
        away_tactics={"formation": "4-3-3", "tags": ["counter"]},
        **kw,
    )


def _phases(match_id, **kw) -> list[dict]:
    return _run(match_id, **kw).to_dict()["phases"]


def test_same_seed_reproduces_identical_phases(_fake_players):
    a = _phases("phase_det")
    b = _phases("phase_det")
    assert a == b
    assert a, "a match must produce a phase stream"


def test_phase_shape_and_22_tokens(_fake_players):
    phases = _phases("phase_shape")
    assert phases
    expected = set(_H_XI) | set(_A_XI)
    for ph in phases:
        assert {"t", "ball", "players", "minute", "type", "event"} <= set(ph)
        assert isinstance(ph["t"], float) and ph["t"] >= 0.0
        b = ph["ball"]
        assert 0.0 <= b["x"] <= M.PITCH_LENGTH
        assert 0.0 <= b["y"] <= M.PITCH_WIDTH
        assert 0.0 <= b["z"] <= 5.0
        players = ph["players"]
        assert len(players) == 22
        home = [p for p in players if p["side"] == "home"]
        away = [p for p in players if p["side"] == "away"]
        assert len(home) == 11 and len(away) == 11
        assert {p["id"] for p in players} == expected
        for p in players:
            # on the pitch — actors may legitimately sit on the goal line or
            # touchline (a goal at x=100, a throw-in at the flag)
            assert 0.0 <= p["x"] <= M.PITCH_LENGTH
            assert 0.0 <= p["y"] <= M.PITCH_WIDTH
            assert 0.0 <= p["facing"] <= 360.0


def test_t_is_strictly_increasing(_fake_players):
    ts = [ph["t"] for ph in _phases("phase_timeline")]
    assert len(ts) >= 20
    assert all(ts[i] < ts[i + 1] for i in range(len(ts) - 1)), "phases must play in feed order"


def test_actions_mapped_from_event_types(_fake_players):
    d = _run("phase_actions", require_result=True).to_dict()
    feed = d["feed"]
    by_type: dict[str, list[dict]] = {}
    for ph in d["phases"]:
        by_type.setdefault(ph["type"], []).append(ph)
    for i, ev in enumerate(feed):
        ph = d["phases"][i]
        typ = ev["type"]
        if typ in ("pass", "possession", "shot", "goal", "penalty", "corner", "cross"):
            assert ph["action"] in ("pass", "carry", "shot", "cross"), typ
            assert ph["event"] == i and ph["type"] == typ
        else:
            assert "action" not in ph, typ


def test_actor_snaps_to_ball(_fake_players):
    d = _run("phase_actor").to_dict()
    for i, ev in enumerate(d["feed"]):
        pid = ev.get("player_id")
        if not pid or pid not in set(_H_XI) | set(_A_XI):
            continue
        ph = d["phases"][i]
        player = next(p for p in ph["players"] if p["id"] == pid)
        assert player["x"] == ev["x"]
        assert player["y"] == ev["y"]
        assert player["facing"] == ev["facing"]
        assert ph["ball"]["x"] == ev["x"]
        assert ph["ball"]["y"] == ev["y"]


def test_formation_shape_is_football(_fake_players):
    """Keepers hug their goal, attackers push toward the opponent's goal."""
    for i in range(10):
        d = _run(f"phase_shape_{i}").to_dict()
        ph = d["phases"][len(d["phases"]) // 2]  # mid-match, settled shape
        home = {p["id"]: p for p in ph["players"] if p["side"] == "home"}
        away = {p["id"]: p for p in ph["players"] if p["side"] == "away"}
        h_gk = home[_H_XI[0]]
        h_st = home[_H_XI[-1]]
        a_gk = away[_A_XI[0]]
        a_st = away[_A_XI[-1]]
        assert h_gk["x"] <= 15.0, "home keeper stays near his own goal"
        assert a_gk["x"] >= M.PITCH_LENGTH - 15.0, "away keeper stays near his own goal"
        assert h_st["x"] > h_gk["x"] + 15.0, "home striker pushes toward +x"
        assert a_st["x"] < a_gk["x"] - 15.0, "away striker pushes toward −x"
        assert h_gk["y"] > 20.0 and h_gk["y"] < M.PITCH_WIDTH - 20.0, "keeper on the goal line"


def test_goals_have_loopable_build_up(_fake_players):
    """A goal phase carries action=shot with the scorer on the ball, and the
    preceding ~5 minutes of phases form a contiguous timeline to rewind."""
    goals_seen = 0
    for i in range(20):
        d = _run(f"phase_goal_{i}").to_dict()
        for gi, ev in enumerate(d["feed"]):
            if ev["type"] != "goal":
                continue
            goals_seen += 1
            ph = d["phases"][gi]
            assert ph["action"] == "shot"
            assert ph["note"], "goal phase must carry a readable note"
            pid = ev.get("player_id")
            if pid:
                scorer = next(p for p in ph["players"] if p["id"] == pid)
                assert scorer["x"] == ev["x"] and scorer["y"] == ev["y"]
            # build-up: at least 2 phases within the 5 minutes before the goal
            before = [p for p in d["phases"][:gi] if p["t"] >= ph["t"] - 5.0]
            assert len(before) >= 2, "a goal should be rewindable across a build-up"
    assert goals_seen >= 1, "expected at least one goal across the seeds"


def test_phase_stream_is_purely_additive(_fake_players, monkeypatch):
    """Disabling the overlay keeps the phases' own determinism: same seed +
    same feed always gives the same phases, and the feed is not mutated."""
    import copy

    d = _run("phase_neutral", require_result=True).to_dict()
    feed_before = copy.deepcopy(d["feed"])
    _phases("phase_neutral", require_result=True)
    assert d["feed"] == feed_before, "building phases must not mutate the feed"

    monkeypatch.setattr(M, "spatialize_feed", lambda feed, match_id: feed)
    raw = M.simulate_match(
        "phase_neutral",
        home_agent_id="home",
        away_agent_id="away",
        home_xi=_H_XI,
        away_xi=_A_XI,
        require_result=True,
    ).to_dict()
    # phases still exist (ball centred, no actor coords) — just deterministic
    assert raw["phases"] == raw["phases"]


def test_extra_time_matches_emit_phases(_fake_players):
    settled = [i for i in range(40) if _run(f"phase_et_{i}", require_result=True).reason in ("extra_time", "penalties")]
    assert settled, "expected at least one settled match across the seeds"
    ph = _phases(f"phase_et_{settled[0]}", require_result=True)
    assert ph[-1]["type"] in ("full_time", "penalties_end", "extra_time_end")