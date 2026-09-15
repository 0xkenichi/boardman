"""Blue Lock's brain — creator_bluelock_demo. Football managers only.

Answers the House's matchday ask (boardman.agent.football_managers.matchday.v1)
with the striker-ego playbook: best-rated XI, attack-first shapes, never
park the bus. Decides purely from the ask payload — own squad plus the
opposition lineup — never from hidden sliders (it never sees them).
"""
from __future__ import annotations

from typing import Any

from gaming.src.stack.agentic.agents.bluelock.mind import MIND

ARCHETYPE = str(MIND.get("archetype") or "striker")


def handle_webhook(body: dict[str, Any]) -> dict[str, Any]:
    """House POSTs a matchday ask here; we reply with our plan JSON."""
    from gaming.src.stack.agentic.games.football_managers.decide import decide_from_ask

    plan = decide_from_ask(ARCHETYPE, body or {})
    if plan is None:
        return {"error": "no playable squad in ask"}
    return {
        "formation": plan["formation"],
        "xi": list(plan["starters"]),
        "bench": list(plan["bench"]),
        "tactical_tags": list(plan["tags"]),
        "instructions": "Never settle for a draw — press high and outscore.",
    }