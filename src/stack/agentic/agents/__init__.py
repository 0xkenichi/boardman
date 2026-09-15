"""
Siloed agent packages — each agent is its own deployable identity.

HARD RULE: packages under agents/<name>/ must NOT import each other.
Each silo is a builder-shipped agent (own creator_id, mind, webhook).
House only POSTs boardman.agent.move.v1 — it does not play.
"""
from __future__ import annotations

from typing import Any, Optional


def load_demo_manifests() -> list[dict[str, Any]]:
    from gaming.src.stack.agentic.agents.raja.manifest import MANIFEST as RAJA
    from gaming.src.stack.agentic.agents.nero.manifest import MANIFEST as NERO
    from gaming.src.stack.agentic.agents.boardman.manifest import MANIFEST as HOUSE
    # Demo AFM managers — football only, never chess. Raja/Nero stay chess-only.
    from gaming.src.stack.agentic.agents.bluelock.manifest import MANIFEST as BLUELOCK
    from gaming.src.stack.agentic.agents.aoashi.manifest import MANIFEST as AOASHI
    from gaming.src.stack.agentic.agents.matchslice.manifest import MANIFEST as MATCHSLICE

    return [dict(RAJA), dict(NERO), dict(HOUSE), dict(BLUELOCK), dict(AOASHI), dict(MATCHSLICE)]


def get_agent_manifest(agent_id: str) -> Optional[dict[str, Any]]:
    for m in load_demo_manifests():
        if m.get("agent_id") == agent_id:
            return m
    return None
