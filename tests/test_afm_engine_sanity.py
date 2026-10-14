"""AFM engine sanity: no impossible matches.

Folds every event log back into a pitch roster and checks the laws the
engine claims to obey: at most eleven on the pitch per side, a sent-off
player never acts again (and never comes back on as a substitute), subs only
come from the unused bench, the goal events add up to the score, and the
same match id replays to the identical feed. Uses the real seeded catalog
plus generated AI filler squads — the squads production actually fields.
"""
from __future__ import annotations

from collections import Counter

import pytest

from gaming.src.stack.agentic.games.football_managers import catalog as C
from gaming.src.stack.agentic.games.football_managers import fillers as F
from gaming.src.stack.agentic.games.football_managers.match_engine import (
    MAX_SUBS_90,
    MAX_SUBS_WITH_ET,
    simulate_match,
)

_SHAPE = ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW"]
_BENCH = ["GK", "CB", "CM", "ST", "RW"]


def _catalog_team(offset: int) -> tuple[list[str], list[str]]:
    """offset 0 / 1 → two disjoint star squads (no player on both sides)."""
    by_slot: dict[str, list[dict]] = {}
    for p in C.seed_catalog():
        by_slot.setdefault(p["slot"], []).append(p)
    for pool in by_slot.values():
        pool.sort(key=lambda p: -p["base_rating"])
    used: Counter = Counter()
    picked: list[list[str]] = [[], []]
    for out, slots in zip(picked, (_SHAPE, _BENCH)):
        for slot in slots:
            pool = by_slot[slot]
            # interleave: team 0 takes ranks 0, 2, 4…; team 1 takes 1, 3, 5…
            out.append(pool[(2 * used[slot] + offset) % len(pool)]["player_id"])
            used[slot] += 1
    return picked[0], picked[1]


def _filler_team(idx: int) -> tuple[list[str], list[str]]:
    squad = F._gen_squad(idx)
    return squad[:11], squad[11:16]


def _violations(result, home, away, *, require_result: bool) -> list[str]:
    on = {"home": set(home[0]), "away": set(away[0])}
    bench = {"home": set(home[1]), "away": set(away[1])}
    gone = {"home": set(), "away": set()}  # subbed off or sent off
    sent_off = {"home": set(), "away": set()}
    goals: Counter = Counter()
    subs: Counter = Counter()
    yellows: Counter = Counter()
    bad: list[str] = []
    for i, ev in enumerate(result.feed):
        typ, side, pid = ev.get("type"), ev.get("side"), ev.get("player_id")
        if typ == "substitution":
            off, new = ev.get("off"), ev.get("on")
            if off not in on[side]:
                bad.append(f"#{i} {side} subs off {off} who is not on the pitch")
            if new not in bench[side] or new in gone[side]:
                bad.append(f"#{i} {side} sends on {new} who is not an unused sub")
            on[side].discard(off)
            gone[side].add(off)
            bench[side].discard(new)
            on[side].add(new)
            subs[side] += 1
        elif typ == "red":
            if pid not in on[side]:
                bad.append(f"#{i} red card for {pid} who is not on the pitch")
            on[side].discard(pid)
            gone[side].add(pid)
            sent_off[side].add(pid)
        elif pid and side in on and typ != "injury":
            if pid in sent_off[side]:
                bad.append(f"#{i} sent-off {pid} plays on ({typ} {ev.get('minute')}')")
            elif pid not in on[side]:
                bad.append(f"#{i} {pid} acts ({typ}) while off the pitch")
        if typ == "goal":
            goals[side] += 1
        if typ == "yellow":
            yellows[pid] += 1
        for s in ("home", "away"):
            if len(on[s]) > 11:
                bad.append(f"#{i} {s} has {len(on[s])} players on the pitch")
    if result.home_goals < 0 or result.away_goals < 0:
        bad.append("negative goals")
    if (goals["home"], goals["away"]) != (result.home_goals, result.away_goals):
        bad.append(f"goal events {dict(goals)} != score {result.home_goals}-{result.away_goals}")
    cap = MAX_SUBS_WITH_ET if require_result else MAX_SUBS_90
    for s in ("home", "away"):
        if subs[s] > cap:
            bad.append(f"{s} made {subs[s]} substitutions (max {cap})")
    if any(n > 2 for n in yellows.values()):
        bad.append("a player was booked three times")
    return bad


def _play(mid: str, home, away, *, tactics=None, require_result=False):
    return simulate_match(
        mid,
        home_agent_id="home_club",
        away_agent_id="away_club",
        home_xi=home[0],
        away_xi=away[0],
        home_bench=home[1],
        away_bench=away[1],
        home_tactics=tactics,
        away_tactics={"formation": "4-3-3", "tags": ["balanced"]},
        require_result=require_result,
    )


def test_red_carded_substitute_never_comes_back_on():
    """Regression: a sub sent off was left on the bench list, so a later
    substitution could bring him back on (inv_221: Pedri, red at 60', back on
    at 72' and tackling at 73')."""
    home = _filler_team(1)
    away = (
        ["afm_pl_043", "afm_pl_035", "afm_pl_030", "afm_pl_031", "afm_pl_039", "afm_pl_026",
         "afm_pl_019", "afm_pl_016", "afm_pl_010", "afm_pl_001", "afm_pl_006"],
        ["afm_pl_044", "afm_pl_033", "afm_pl_020", "afm_pl_005", "afm_pl_009"],
    )
    r = _play("inv_221", home, away, tactics={"formation": "4-3-3", "tags": ["balanced"]},
              require_result=True)
    assert _violations(r, home, away, require_result=True) == []


@pytest.mark.parametrize(
    "tactics",
    [
        {"formation": "4-3-3", "tags": ["balanced"]},
        {"formation": "3-4-3", "tags": ["gegenpress"]},
        {"formation": "5-3-2", "tags": ["park_bus"]},
    ],
)
def test_no_impossible_matches_across_seeds(tactics):
    pairs = [(_catalog_team(0), _catalog_team(1)), (_filler_team(1), _catalog_team(0))]
    for n in range(16):
        home, away = pairs[n % 2]
        require_result = n % 4 == 0
        r = _play(f"sanity_{tactics['tags'][0]}_{n}", home, away, tactics=tactics,
                  require_result=require_result)
        assert _violations(r, home, away, require_result=require_result) == [], r.match_id
        assert r.feed[0]["type"] == "kickoff"
        if not require_result:
            assert r.feed[-1]["type"] == "full_time"


def test_same_match_id_replays_identically_with_real_squads():
    home, away = _filler_team(2), _catalog_team(1)
    a = _play("sanity_replay", home, away, require_result=True).to_dict()
    b = _play("sanity_replay", home, away, require_result=True).to_dict()
    assert a == b
    c = _play("sanity_replay_other", home, away, require_result=True).to_dict()
    assert c["feed"] != a["feed"]
