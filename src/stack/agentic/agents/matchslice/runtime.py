"""Match-Slice's brain — creator_matchslice_demo. Football managers only.

Answers the House's matchday ask (boardman.agent.football_managers.matchday.v1)
with the solo-brain playbook: position-disciplined XI, 4-3-3 / 4-2-3-1 with
always one pivot, a mid-block, and a counter when the opponent is aggressive
or the fixture is a must-not-lose. Decides purely from the ask payload — own
squad plus the opposition lineup — never from hidden sliders (it never sees
them).
"""
from __future__ import annotations

from typing import Any

from gaming.src.stack.agentic.agents.matchslice.mind import MIND

ARCHETYPE = str(MIND.get("archetype") or "balanced")


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
        # v1.4: half-time contingency plans must ride along — the House stores
        # what the webhook replied, and a reply without `plans` means the
        # engine gets none at the lock
        "plans": dict(plan.get("plans") or {}),
        "instructions": "Stay solvent, stay in shape, and punish their mistakes.",
    }