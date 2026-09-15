"""AFM season league — divisions, fixtures, standings.

The game-of-record model (docs/games/AGENTIC_FOOTBALL_MANAGERS_GAME.md):
a season is R matchdays; each matchday every club in the division plays once.

Scheduling:
  M >= 3  → double round-robin: R = 2*(M-1) for even M, 2*M for odd M
            (odd divisions have a bye each matchday)
  M == 2  → derby division: DERBY_MATCHDAYS alternating home/away days so a
            two-club season has real length
  M odd   → circle method leaves one club on a bye each matchday (no points)

Standings: 3/1/0 points, goal difference, goals for. Pure functions — the
matchday executor and USDC settlement live in a later layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DERBY_MATCHDAYS = 30  # v1: 1 matchday/day → a ~month-long two-club season
POINTS_WIN = 3
POINTS_DRAW = 1
POINTS_LOSS = 0


@dataclass(frozen=True)
class Fixture:
    """One locked fixture in a matchday. Result set at resolution."""

    matchday: int
    round: int
    home_agent_id: str
    away_agent_id: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    status: str = "scheduled"  # scheduled | locked | played
    match_id: Optional[str] = None

    def result(self) -> Optional[tuple[int, int]]:
        if self.home_goals is None or self.away_goals is None:
            return None
        return (self.home_goals, self.away_goals)


def _single_round_robin(ids: list[str]) -> list[list[tuple[str, str]]]:
    """Canonical circle method. Odd counts pad with a bye (club skips that
    matchday). Home/away alternate by slot so the fixed club alternates too;
    the return leg flips every pairing for a double round robin."""
    clubs: list[Optional[str]] = list(dict.fromkeys(ids))
    n = len(clubs)
    if n < 2:
        return []
    if n % 2 == 1:
        clubs.append(None)
        n += 1
    rounds: list[list[tuple[str, str]]] = []
    for _ in range(n - 1):
        pairs: list[tuple[str, str]] = []
        for i in range(n // 2):
            h, a = clubs[i], clubs[n - 1 - i]
            if h is None or a is None:
                continue  # bye matchday for the club paired with the spare
            pairs.append((a, h) if i % 2 == 1 else (h, a))
        rounds.append(pairs)
        clubs = [clubs[0], clubs[-1]] + clubs[1:-1]
    return rounds


def _double_round_robin(ids: list[str]) -> list[list[tuple[str, str]]]:
    """Two full round robins; the return leg flips home/away."""
    first = _single_round_robin(ids)
    return first + [[(b, a) for a, b in rd] for rd in first]


def _derby_pairs(a: str, b: str, matchdays: int) -> list[list[tuple[str, str]]]:
    out: list[list[tuple[str, str]]] = []
    for m in range(matchdays):
        if m % 2 == 0:
            out.append([(a, b)])
        else:
            out.append([(b, a)])
    return out


def season_rounds(ids: list[str]) -> int:
    """Total matchdays for a double round robin of M clubs.

    Even M: 2*(M-1). Odd M: every matchday has a bye, so 2*M.
    """
    m = len(ids)
    if m < 2:
        return 0
    if m == 2:
        return DERBY_MATCHDAYS
    return 2 * (m - 1) if m % 2 == 0 else 2 * m


def schedule_season(
    club_ids: list[str],
    *,
    matchdays: Optional[int] = None,
) -> list[list[Fixture]]:
    """One entry per matchday, in order. Deterministic given input order."""
    ids = sorted(set(club_ids))
    m = len(ids)
    if m < 2:
        return []
    if m == 2:
        rounds = _derby_pairs(ids[0], ids[1], matchdays or DERBY_MATCHDAYS)
    else:
        rounds = _double_round_robin(ids)
        if matchdays is not None:
            rounds = rounds[:matchdays]
    out: list[list[Fixture]] = []
    for r, pairs in enumerate(rounds, start=1):
        out.append(
            [
                Fixture(matchday=r, round=r, home_agent_id=h, away_agent_id=a)
                for h, a in pairs
            ]
        )
    return out


# ---------------------------------------------------------------- standings

@dataclass
class Row:
    agent_id: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against


def new_standings(club_ids: list[str]) -> dict[str, Row]:
    return {aid: Row(agent_id=aid) for aid in sorted(set(club_ids))}


def apply_result(
    table: dict[str, Row],
    fixture: Fixture,
    home_goals: int,
    away_goals: int,
) -> dict[str, Row]:
    """Return a copy of the standings after this fixture (3/1/0)."""
    out = {aid: Row(**{**vars(r)}) for aid, r in table.items()}
    h = out[fixture.home_agent_id]
    a = out[fixture.away_agent_id]
    for row, gf, ga in ((h, home_goals, away_goals), (a, away_goals, home_goals)):
        row.played += 1
        row.goals_for += gf
        row.goals_against += ga
    if home_goals > away_goals:
        h.wins += 1
        a.losses += 1
        h.points += POINTS_WIN
    elif home_goals < away_goals:
        a.wins += 1
        h.losses += 1
        a.points += POINTS_WIN
    else:
        h.draws += 1
        a.draws += 1
        h.points += POINTS_DRAW
        a.points += POINTS_DRAW
    return out


def ranked(table: dict[str, Row]) -> list[Row]:
    """Standings order: points, goal difference, goals for, id asc."""
    return sorted(
        table.values(),
        key=lambda r: (-r.points, -r.goal_diff, -r.goals_for, r.agent_id),
    )


def season_outcome(table: dict[str, Row]) -> list[str]:
    """Champion (then runners-up) — for season-pot payout ordering."""
    return [r.agent_id for r in ranked(table)]
