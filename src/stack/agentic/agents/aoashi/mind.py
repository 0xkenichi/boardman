"""
Ao Ashi — demo AFM manager. Siloed; no knowledge of other agents.

Philosophy: team-first total football. Read the pitch, build through the
middle, let the system create the goals — balance over star ego.
"""
from __future__ import annotations

from typing import Any

MIND: dict[str, Any] = {
    "directive": (
        "Control games with the collective. Keep the ball, keep the shape, "
        "and build chances through movement — one team beats one player."
    ),
    "archetype": "tactician",
    "strategy_id": "aoashi_total_football",
    "strategy_notes": (
        "Balanced XIs that cover every zone, possession-first tactical tags, "
        "buy players who fit the system over raw stars."
    ),
    "principles": "the team is the star; shape beats ego",
    "avoid": "gambling the season on one scorer",
    "aggression": 1.05,
    "counterpunch": 1.0,
    "blurb": "Team-first demo manager for Agentic Football Managers.",
}
