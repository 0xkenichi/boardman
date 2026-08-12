"""
Siloed agent packages — each agent is its own deployable identity.

HARD RULE: packages under agents/<name>/ must NOT import each other.
They only implement the Boardman agent interface and load via the registry.
That way two creators' bots meet as strangers, not as shared codebase twins.
"""
from __future__ import annotations

from typing import Any, Optional


def load_demo_manifests() -> list[dict[str, Any]]:
    from gaming.src.stack.agentic.agents.raja.manifest import MANIFEST as RAJA
    from gaming.src.stack.agentic.agents.nero.manifest import MANIFEST as NERO

    return [dict(RAJA), dict(NERO)]


def get_agent_manifest(agent_id: str) -> Optional[dict[str, Any]]:
    for m in load_demo_manifests():
        if m.get("agent_id") == agent_id:
            return m
    return None
