"""AFM knockout cup: bracket builder, open/tick lifecycle, and the rule that a
knockout draw must be settled (extra time + penalties via require_result).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gaming.src.stack.agentic.games.football_managers.cup import (
    build_bracket,
    get_cup,
    get_cup_replay,
    open_cup,
    reset_cup,
    tick,
)


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


def _demo_ids() -> list[str]:
    from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

    return [c["agent_id"] for c in list_clubs()]


def _derby_ids() -> list[str]:
    """A two-club field — single-round cup, finishes in one tick.

    The demo universe grew to three managers, so tests that assume the old
    one-round cup pin the field to two clubs explicitly."""
    return sorted(_demo_ids())[:2]


def _past(days: int = 3) -> datetime:
    """Start far enough back that every round of a 3-round cup is due."""
    return _now() - timedelta(days=days)


# ---------------------------------------------------------------- bracket


def test_bracket_structure() -> None:
    for n in range(2, 9):
        ids = [f"t{i}" for i in range(n)]
        bracket = build_bracket(ids)
        rounds = max(1, (n - 1).bit_length())
        assert len(bracket) == rounds
        assert len(bracket[-1]["ties"]) == 1  # a final
        r1_ties = bracket[0]["ties"]
        # every club appears in round 1 exactly once (bye counts as an entry)
        seen = []
        for tie in r1_ties:
            assert tie["home_agent_id"] is not None
            seen.append(tie["home_agent_id"])
            if tie["away_agent_id"] is not None:
                seen.append(tie["away_agent_id"])
        assert sorted(seen) == sorted(ids)
        # no empty tie, and a bye is one team + no opponent
        for tie in r1_ties:
            assert tie["away_agent_id"] is not None or tie["home_agent_id"] is not None
        # later rounds halve each time down to a single final
        for rnd in bracket[1:]:
            prev = rnd["round_no"] - 1
            assert len(rnd["ties"]) == len(bracket[prev - 1]["ties"]) // 2


def test_bracket_requires_two_entries() -> None:
    with pytest.raises(ValueError):
        build_bracket(["only"])


# ---------------------------------------------------------------- service


def _fake_clubs(n: int, monkeypatch) -> list[str]:
    """Stand in an AFM universe of n identical-ish clubs (no registry needed)."""
    import gaming.src.stack.agentic.games.football_managers.club_store as cs

    ids = [f"cup_club_{i:02d}" for i in range(n)]

    def _club(aid: str):
        if aid not in ids:
            return None
        return {
            "agent_id": aid,
            "club_name": f"Club {aid}",
            "starters": [f"{aid}_p{i}" for i in range(1, 12)],
            "bench": [f"{aid}_p{i}" for i in range(12, 17)],
            "squad": [f"{aid}_p{i}" for i in range(1, 17)],
            "formation": "4-3-3",
            "tactical_tags": ["balanced"],
        }

    monkeypatch.setattr(cs, "list_clubs", lambda: [_club(i) for i in ids])
    monkeypatch.setattr(cs, "get_club", _club)
    return ids


def test_open_cup_guards(_world) -> None:
    with pytest.raises(ValueError):
        open_cup(["not_a_club", "also_not"])
    cup = open_cup(_derby_ids(), start_at=_now() + timedelta(hours=2))
    assert cup["status"] == "open"
    assert cup["rounds_total"] == 1
    assert cup["division"][0]["agent_id"] == sorted(_derby_ids())[0]  # deterministic
    with pytest.raises(ValueError):
        open_cup(_derby_ids())  # already running
    # force replaces, cup_no advances
    cup2 = open_cup(_derby_ids(), force=True, salt="second")
    assert cup2["cup_no"] == 2


def test_two_club_cup_crowns_champion(_world) -> None:
    # start 7h back → the (only) round's deadline already passed
    open_cup(_derby_ids(), start_at=_now() - timedelta(hours=7))
    out = tick()
    assert out["opened"] == [1]
    assert out["resolved"] == [1]
    snap = get_cup()
    assert snap["status"] == "finished"
    assert snap["champion"] in set(_derby_ids())
    final = snap["rounds"][0]["ties"][0]
    assert final["winner_agent_id"] == snap["champion"]
    assert final["reason"] in ("full_time", "extra_time", "penalties")
    assert final["outcome"] in ("home_win", "away_win")

    # second (or third) caller never re-resolves
    out2 = tick()
    assert out2["action"] == "idle"
    assert get_cup()["champion"] == snap["champion"]


def test_eight_club_knockout_runs_to_a_single_final(monkeypatch) -> None:
    ids = _fake_clubs(8, monkeypatch)
    open_cup(ids, start_at=_past(days=3), salt="afm_cup_eight")
    out = tick()
    assert out["opened"] == [1, 2, 3]
    assert out["resolved"] == [1, 2, 3]

    snap = get_cup()
    assert snap["status"] == "finished"
    assert snap["champion"] in ids
    assert len(snap["rounds"]) == 3
    # 4 quarter-finals + 2 semis + 1 final, all played, each decisive
    r1, r2, r3 = (r["ties"] for r in snap["rounds"])
    assert len(r1) == 4 and all(t["status"] == "played" for t in r1)
    assert len(r2) == 2 and all(t["status"] == "played" for t in r2)
    assert len(r3) == 1 and r3[0]["status"] == "played"
    # every winner keeps playing — the final's winner is the champion
    winners1 = {t["winner_agent_id"] for t in r1}
    winners2 = {t["winner_agent_id"] for t in r2}
    assert winners2 <= winners1
    assert r3[0]["winner_agent_id"] == snap["champion"]
    # each real tie produced a full, decisive engine result
    for tie in r1 + r2 + r3:
        assert tie["score"]
        assert tie["outcome"] in ("home_win", "away_win")
        assert tie["reason"] in ("full_time", "extra_time", "penalties")


def test_byes_advance_without_playing(monkeypatch) -> None:
    ids = _fake_clubs(5, monkeypatch)  # 4-team round 2 + 1 bye
    open_cup(ids, start_at=_past(days=3), salt="afm_cup_five")
    out = tick()
    assert out["opened"] == [1, 2, 3]
    assert out["resolved"] == [1, 2, 3]
    snap = get_cup()
    assert snap["champion"] in ids
    r1_ties = snap["rounds"][0]["ties"]
    byes = [t for t in r1_ties if t["bye"]]
    assert len(byes) == 3  # 8-slot bracket, 5 clubs
    for t in byes:
        assert t["status"] == "played" and t["winner_agent_id"]
        assert not t.get("score")  # no engine result for a bye


def test_knockout_draws_are_settled_extra_time_or_penalties(_world) -> None:
    """A level 90' knockout tie must go to extra time / pens — never a draw."""
    deciders = 0
    for i in range(60):
        open_cup(_derby_ids(), start_at=_now() - timedelta(hours=7), salt=f"afm_cup_draw_{i}", force=True)
        out = tick()
        assert out["resolved"] == [1]
        snap = get_cup()
        assert snap["status"] == "finished"
        final = snap["rounds"][0]["ties"][0]
        assert final["outcome"] in ("home_win", "away_win")  # never a draw decider
        assert final["winner_agent_id"] == snap["champion"]
        if final["reason"] in ("extra_time", "penalties"):
            deciders += 1
    assert deciders > 0, "no knockout tie ever reached extra time across 60 seeded cups"


def test_extra_time_tie_actually_goes_to_extra_time(_world) -> None:
    """Find a decider and verify the stored feed really shows ET / the shootout."""
    found = None
    for i in range(80):
        open_cup(_derby_ids(), start_at=_now() - timedelta(hours=7), salt=f"afm_cup_et_{i}", force=True)
        tick()
        tie = get_cup()["rounds"][0]["ties"][0]
        if tie["reason"] in ("extra_time", "penalties"):
            found = tie
            break
    assert found is not None, "no decider across 80 seeds"
    replay = get_cup_replay(found["round_no"], found["home_agent_id"], found["away_agent_id"])
    feed = replay["result"]["feed"]
    types = [e["type"] for e in feed]
    assert "extra_time_end" in types  # the match really went past 90'
    if found["reason"] == "penalties":
        assert "penalties_start" in types and "penalties_end" in types
        assert found["home_pen_goals"] != found["away_pen_goals"]
    else:
        assert found["home_goals"] != found["away_goals"]


def test_replay_returns_recorded_tie_and_reconstructs(_world) -> None:
    from gaming.src.stack.agentic.store import load_json, save_json

    open_cup(_derby_ids(), start_at=_now() - timedelta(hours=7), salt="afm_cup_replay")
    tick()
    snap = get_cup()
    ids = sorted(_derby_ids())
    replay = get_cup_replay(1, ids[0], ids[1])
    assert replay["result"]["score"] == snap["rounds"][0]["ties"][0]["score"]
    feed = replay["result"]["feed"]
    assert feed and feed[0]["type"] == "kickoff"
    assert feed[-1]["type"] in ("full_time", "extra_time_end", "penalties_end")
    assert replay["home"]["xi"] and replay["away"]["xi"]
    # deterministic replay — the recorded result is returned as-is
    again = get_cup_replay(1, ids[0], ids[1])
    assert again["result"] == replay["result"]

    # legacy state (feed not stored) reconstructs deterministically: same seed
    # + locked lineups → same match
    st = load_json("afm_cup.json", {"cup": None})
    for tie in st["cup"]["rounds"]["1"]["ties"]:
        if tie.get("result"):
            tie["result"].pop("feed", None)
    save_json("afm_cup.json", st)
    rebuilt = get_cup_replay(1, ids[0], ids[1])
    assert rebuilt["result"]["score"] == replay["result"]["score"]
    assert rebuilt["result"]["feed"]  # reconstructed feed present


def test_reset_clears_cup(_world) -> None:
    open_cup(_demo_ids(), start_at=_now() + timedelta(hours=2))
    assert reset_cup()["reset"] is True
    assert get_cup() is None
