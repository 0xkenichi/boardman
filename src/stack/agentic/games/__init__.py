"""
Finite-outcome game modules for Boardman Stack agent arena.

Each game exposes the same interface so agents, escrow, clocks, and
spectator pots stay game-agnostic.
"""
from __future__ import annotations

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult
from gaming.src.stack.agentic.games.catalog import GAME_CATALOG, get_game, list_games

__all__ = [
    "GameModule",
    "GameResult",
    "MoveResult",
    "GAME_CATALOG",
    "get_game",
    "list_games",
]
