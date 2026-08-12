"""Chess reference module for Boardman agentic arena."""
from gaming.src.stack.agentic.chess.arena import play_match
from gaming.src.stack.agentic.chess.personas import DEMO_AGENTS, get_persona
from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine

__all__ = ["play_match", "DEMO_AGENTS", "get_persona", "HybridEngine"]
