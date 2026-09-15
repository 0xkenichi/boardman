"""AFM season league: schedule generation (M=2 derby, M>=3 RR, byes) + standings."""
from __future__ import annotations

from gaming.src.stack.agentic.games.football_managers.league import (
    Fixture,
    apply_result,
    new_standings,
    ranked,
    schedule_season,
    season_outcome,
    season_rounds,
)

TWO = ["agent_aoashi_demo", "agent_bluelock_demo"]
FOUR = ["agent_a", "agent_b", "agent_c", "agent_d"]


def test_derby_two_club_season_alternates_home_away() -> None:
    sched = schedule_season(TWO)
    assert len(sched) == 30  # DERBY_MATCHDAYS default
    assert all(len(day) == 1 for day in sched)
    home1 = sched[0][0].home_agent_id
    for i, day in enumerate(sched):
        fx = day[0]
        if i % 2 == 0:
            assert fx.home_agent_id == home1
        else:
            assert fx.home_agent_id != home1
        assert {fx.home_agent_id, fx.away_agent_id} == set(TWO)


def test_double_round_robin_four_clubs() -> None:
    sched = schedule_season(FOUR)
    assert len(sched) == 2 * (4 - 1)
    # each pair appears exactly twice, once per venue
    seen: dict[frozenset, int] = {}
    for day in sched:
        assert len(day) == 2  # every club plays
        for fx in day:
            key = frozenset((fx.home_agent_id, fx.away_agent_id))
            seen[key] = seen.get(key, 0) + 1
    assert len(seen) == 6
    assert all(v == 2 for v in seen.values())
    # no club plays twice in one matchday
    for day in sched:
        players = [pid for fx in day for pid in (fx.home_agent_id, fx.away_agent_id)]
        assert len(set(players)) == len(players)
    # every club has balanced venues across the season
    for club in FOUR:
        home = sum(1 for day in sched for fx in day if fx.home_agent_id == club)
        assert home == len(FOUR) - 1


def test_odd_division_gets_byes() -> None:
    odd = ["x1", "x2", "x3"]
    sched = schedule_season(odd)
    assert len(sched) == 2 * 3  # byes each matchday → 2*M matchdays
    for day in sched:
        playing = {fx.home_agent_id for fx in day} | {fx.away_agent_id for fx in day}
        assert len(playing) == 2  # one club rests
    pairs = {
        frozenset((fx.home_agent_id, fx.away_agent_id))
        for day in sched
        for fx in day
    }
    assert len(pairs) == 3


def test_rounds_override_and_min_division() -> None:
    assert schedule_season(["only_one"]) == []
    short = schedule_season(TWO, matchdays=4)
    assert len(short) == 4
    assert season_rounds(FOUR) == 6
    assert season_rounds(TWO) == 30
    assert season_rounds(["solo"]) == 0


def test_standings_points_goal_diff_and_ranking() -> None:
    table = new_standings(TWO)
    a, b = TWO
    fx1 = Fixture(matchday=1, round=1, home_agent_id=a, away_agent_id=b)
    table = apply_result(table, fx1, 2, 1)
    fx2 = Fixture(matchday=2, round=2, home_agent_id=b, away_agent_id=a)
    table = apply_result(table, fx2, 0, 0)
    assert table[a].points == 4  # win + draw
    assert table[b].points == 1
    assert table[a].goals_for == 2 and table[a].goals_against == 1
    ranked_rows = ranked(table)
    assert ranked_rows[0].agent_id == a
    assert season_outcome(table) == [a, b]

    # GD breaks a points tie
    t3 = new_standings(["p", "q", "r"])
    t3 = apply_result(t3, Fixture(1, 1, "p", "r"), 2, 0)
    t3 = apply_result(t3, Fixture(1, 1, "q", "r"), 1, 0)
    assert t3["p"].points == t3["q"].points == 3
    assert ranked(t3)[0].agent_id == "p"  # +2 GD over +1
    assert season_outcome(t3)[:2] == ["p", "q"]
