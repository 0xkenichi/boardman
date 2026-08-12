"""
Boardman Stack — agentic economy layer.

Agents are economic actors: identity contract address + USDC wallet + strategy.
Matches reuse the dual-lock skill path (demo ledger now; Circle/ClawEscrow when live).
"""
from __future__ import annotations

from gaming.src.stack.agentic.registry import AgentRegistry, get_registry
from gaming.src.stack.agentic.matches import AgentMatchService, get_match_service

__all__ = [
    "AgentRegistry",
    "get_registry",
    "AgentMatchService",
    "get_match_service",
]
