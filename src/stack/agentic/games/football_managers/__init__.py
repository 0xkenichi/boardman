"""
Agentic Football Managers (AFM) — Boardman flagship game (v0).

Status: work-in-progress. Public page: /agentic/football-managers.html
Spec: docs/games/AGENTIC_FOOTBALL_MANAGERS_V1.md
Game id: agentic.football_managers
"""
from __future__ import annotations

from gaming.src.stack.agentic.games.football_managers.catalog import (
    GAME_ID,
    list_players,
    get_player,
    seed_catalog,
)
from gaming.src.stack.agentic.games.football_managers.club import Club, create_club
from gaming.src.stack.agentic.games.football_managers.market import Market, MarketError
from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match
from gaming.src.stack.agentic.games.football_managers.pricing import game_price_from_real_value
from gaming.src.stack.agentic.games.football_managers.rules import AFM_RULES_VERSION, match_laws_summary

__all__ = [
    "GAME_ID",
    "AFM_RULES_VERSION",
    "list_players",
    "get_player",
    "seed_catalog",
    "Club",
    "create_club",
    "Market",
    "MarketError",
    "simulate_match",
    "game_price_from_real_value",
    "match_laws_summary",
]
