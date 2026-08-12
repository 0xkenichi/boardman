"""Chess reference module for Boardman agentic arena."""
from gaming.src.stack.agentic.chess.arena import play_match
from gaming.src.stack.agentic.chess.personas import DEMO_AGENTS, get_persona
from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine, hybrid_from_agent
from gaming.src.stack.agentic.chess.rule_book import RULE_BOOK_VERSION, rule_book_meta

__all__ = [
    "play_match",
    "DEMO_AGENTS",
    "get_persona",
    "HybridEngine",
    "hybrid_from_agent",
    "RULE_BOOK_VERSION",
    "rule_book_meta",
]
