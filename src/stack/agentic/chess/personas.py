"""
Persona loader — bridges siloed agent packages into the registry shape.

Does not merge strategies. Each agent remains a stranger to the other.
"""
from __future__ import annotations

from typing import Any, Optional

from gaming.src.stack.agentic.agents import get_agent_manifest, load_demo_manifests


def _manifest_to_persona(m: dict[str, Any]) -> dict[str, Any]:
    eco = m.get("economy") or {}
    return {
        "agent_id": m["agent_id"],
        "name": m["name"],
        "owner_id": m.get("owner_id") or m.get("creator_id"),
        "creator_id": m.get("creator_id") or m.get("owner_id"),
        "strategy_id": m.get("strategy_id"),
        "openings": list(m.get("openings") or []),
        "version": m.get("version", "1.0.0"),
        "seed": m.get("seed") or m["agent_id"],
        "mind": dict(m.get("mind") or {}),
        "economy": dict(eco),
        "creator_fee_bps": int(eco.get("creator_fee_bps", 500)),
        "silo": m.get("silo"),
        "local_books": m.get("local_books") or {},
        "preferred_time_controls": list(
            eco.get("preferred_time_controls")
            or ["blitz_3|2", "blitz_5|0", "rapid_10|0"]
        ),
    }


DEMO_AGENTS: list[dict[str, Any]] = [
    _manifest_to_persona(m) for m in load_demo_manifests()
]


def get_persona(agent_id: str) -> Optional[dict[str, Any]]:
    m = get_agent_manifest(agent_id)
    if m:
        return _manifest_to_persona(m)
    for a in DEMO_AGENTS:
        if a["agent_id"] == agent_id:
            return a
    return None
