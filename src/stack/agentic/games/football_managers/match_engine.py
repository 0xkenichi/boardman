"""
Minimal match simulator (v0).

Not a full FM engine — strength from XI ratings + form, 90 ticks, seeded RNG.
Produces a minute-by-minute feed for spectators.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.catalog import get_player
from gaming.src.stack.agentic.games.football_managers.rules import MATCH_MINUTES, POINTS_DRAW, POINTS_LOSS, POINTS_WIN


def _seed_int(match_id: str) -> int:
    h = hashlib.sha256(match_id.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _side_strength(player_ids: list[str], rng: random.Random) -> dict[str, float]:
    att = mid = dfn = gk = 0.0
    n = 0
    for pid in player_ids:
        p = get_player(pid)
        if not p:
            continue
        if p.get("injury") or int(p.get("suspension_matches") or 0) > 0:
            continue
        n += 1
        rating = float(p.get("base_rating") or 70) + (float(p.get("form") or 6.5) - 6.5) * 2
        pos = (p.get("primary_pos") or "MID").upper()
        if pos == "GK":
            gk = max(gk, rating)
        elif pos == "DEF":
            dfn += rating
        elif pos == "MID":
            mid += rating
            att += rating * 0.35
        else:
            att += rating
            mid += rating * 0.25
    if n == 0:
        return {"att": 40.0, "mid": 40.0, "def": 40.0, "gk": 40.0}
    # noise
    jitter = lambda x: x * (0.95 + rng.random() * 0.1)
    return {
        "att": jitter(att / max(1, n) * 3.2),
        "mid": jitter(mid / max(1, n) * 3.0),
        "def": jitter(dfn / max(1, n) * 3.2),
        "gk": jitter(gk or 70.0),
    }


@dataclass
class MatchResult:
    match_id: str
    home_agent_id: str
    away_agent_id: str
    home_goals: int
    away_goals: int
    feed: list[dict[str, Any]] = field(default_factory=list)
    home_points: int = 0
    away_points: int = 0
    reason: str = "full_time"

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "home_agent_id": self.home_agent_id,
            "away_agent_id": self.away_agent_id,
            "score": f"{self.home_goals}-{self.away_goals}",
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_points": self.home_points,
            "away_points": self.away_points,
            "reason": self.reason,
            "feed": self.feed,
            "outcome": (
                "home_win"
                if self.home_goals > self.away_goals
                else "away_win"
                if self.away_goals > self.home_goals
                else "draw"
            ),
        }


def simulate_match(
    match_id: str,
    *,
    home_agent_id: str,
    away_agent_id: str,
    home_xi: list[str],
    away_xi: list[str],
) -> MatchResult:
    rng = random.Random(_seed_int(match_id))
    home = _side_strength(home_xi, rng)
    away = _side_strength(away_xi, rng)
    # home advantage
    home["att"] *= 1.03
    home["mid"] *= 1.02

    hg = ag = 0
    feed: list[dict[str, Any]] = [
        {
            "minute": 0,
            "type": "kickoff",
            "text": f"Kickoff · {home_agent_id} vs {away_agent_id}",
        }
    ]

    for minute in range(1, MATCH_MINUTES + 1):
        # chance of an attack event each minute
        if rng.random() > 0.22:
            continue
        # who attacks
        home_attack = home["att"] + home["mid"] * 0.5
        away_attack = away["att"] + away["mid"] * 0.5
        if rng.random() < home_attack / (home_attack + away_attack + 1e-6):
            attack, defence, gk, side = home, away, away["gk"], "home"
        else:
            attack, defence, gk, side = away, home, home["gk"], "away"

        chance = attack["att"] / (defence["def"] + gk * 0.4 + 1e-6)
        shot_p = min(0.55, 0.12 + chance * 0.08)
        if rng.random() > shot_p:
            feed.append(
                {
                    "minute": minute,
                    "type": "attack_broken",
                    "side": side,
                    "text": f"{minute}' · attack breaks down ({side})",
                }
            )
            continue

        # shot on target → goal?
        goal_p = min(0.45, 0.08 + chance * 0.06)
        if rng.random() < goal_p:
            if side == "home":
                hg += 1
            else:
                ag += 1
            feed.append(
                {
                    "minute": minute,
                    "type": "goal",
                    "side": side,
                    "score": f"{hg}-{ag}",
                    "text": f"{minute}' · GOAL ({side}) · {hg}-{ag}",
                }
            )
        else:
            feed.append(
                {
                    "minute": minute,
                    "type": "shot",
                    "side": side,
                    "text": f"{minute}' · shot saved/missed ({side})",
                }
            )

        # rare card
        if rng.random() < 0.015:
            feed.append(
                {
                    "minute": minute,
                    "type": "yellow",
                    "side": side,
                    "text": f"{minute}' · yellow card ({side})",
                }
            )

    feed.append(
        {
            "minute": 90,
            "type": "full_time",
            "score": f"{hg}-{ag}",
            "text": f"FT · {hg}-{ag}",
        }
    )

    if hg > ag:
        hp, ap = POINTS_WIN, POINTS_LOSS
    elif ag > hg:
        hp, ap = POINTS_LOSS, POINTS_WIN
    else:
        hp = ap = POINTS_DRAW

    return MatchResult(
        match_id=match_id,
        home_agent_id=home_agent_id,
        away_agent_id=away_agent_id,
        home_goals=hg,
        away_goals=ag,
        feed=feed,
        home_points=hp,
        away_points=ap,
    )
