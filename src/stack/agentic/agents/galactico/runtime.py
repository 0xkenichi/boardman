"""Galáctico's brain — creator_galactico_demo. Football managers only.

Answers the House's matchday ask (boardman.agent.football_managers.matchday.v1).
Builders' seam: if an LLM key is configured the model gets the ask and picks
the plan; the House validates the reply either way, and any failure falls
back to the deterministic stars-first mind — a club is never defaulted.
"""
from __future__ import annotations

from typing import Any

from gaming.src.stack.agentic.agents.galactico.mind import MIND

ARCHETYPE = str(MIND.get("archetype") or "galactico")


def handle_webhook(body: dict[str, Any]) -> dict[str, Any]:
    """House POSTs a matchday ask here; we reply with our plan JSON."""
    ask = body or {}
    plan = None
    try:
        from gaming.src.stack.agentic.games.football_managers.llm_brain import (
            plan_from_ask,
        )

        plan = plan_from_ask(MIND, ask)
    except Exception:
        plan = None
    if plan is None:
        from gaming.src.stack.agentic.games.football_managers.decide import (
            decide_from_ask,
        )

        plan = decide_from_ask(ARCHETYPE, ask)
    if plan is None:
        return {"error": "no playable squad in ask"}
    return {
        "formation": plan["formation"],
        "xi": list(plan["starters"]),
        "bench": list(plan["bench"]),
        "tactical_tags": list(plan["tags"]),
        "plans": dict(plan.get("plans") or {}),
        "instructions": "Give the ball to the stars and get out of the way.",
    }
