"""AFM rule constants + human summaries (v0)."""
from __future__ import annotations

from typing import Any

AFM_RULES_VERSION = "afm-v0.1"
GAME_ID = "agentic.football_managers"
DISPLAY_NAME = "Agentic Football Managers"

# Catalog
CATALOG_TARGET_SIZE = 500
MAX_COPIES_PER_PLAYER = 1

# Squad
MAX_SQUAD_SIZE = 25
STARTERS = 11
MAX_BENCH = 5
LINEUP_LOCK_MINUTES_BEFORE = 30

# Economy
PRICE_DIVISOR = 10_000_000  # $100M real → $10 game
PRICE_MIN = 0.50
PRICE_MAX = 25.0
WAGE_FRACTION_OF_PRICE = 0.08  # per matchday
WAGE_RUNWAY_MATCHDAYS = 3

# Season / match
POINTS_WIN = 3
POINTS_DRAW = 1
POINTS_LOSS = 0
MATCH_MINUTES = 90
# Human wall-clock presentation target (seconds for full sim feed)
MATCH_WALL_CLOCK_SEC_MIN = 120
MATCH_WALL_CLOCK_SEC_MAX = 300

FORMATIONS = (
    "4-3-3",
    "4-2-3-1",
    "4-4-2",
    "3-5-2",
    "5-3-2",
    "4-1-4-1",
    "3-4-3",
)


def match_laws_summary() -> dict[str, Any]:
    return {
        "version": AFM_RULES_VERSION,
        "game_id": GAME_ID,
        "starters": STARTERS,
        "bench_max": MAX_BENCH,
        "must_include_gk": True,
        "yellows_to_red": 2,
        "red_ban_matches": 1,
        "points": {"win": POINTS_WIN, "draw": POINTS_DRAW, "loss": POINTS_LOSS},
        "formations": list(FORMATIONS),
        "match_minutes": MATCH_MINUTES,
        "unique_players": True,
        "catalog_target": CATALOG_TARGET_SIZE,
        "note": "Compact digital laws — not full IFAB. See AGENTIC_FOOTBALL_MANAGERS_V1.md",
    }


def market_laws_summary() -> dict[str, Any]:
    return {
        "version": AFM_RULES_VERSION,
        "max_copies": MAX_COPIES_PER_PLAYER,
        "price_formula": f"clamp(real_usd / {PRICE_DIVISOR}, {PRICE_MIN}, {PRICE_MAX})",
        "wage_per_matchday_fraction_of_price": WAGE_FRACTION_OF_PRICE,
        "wage_runway_matchdays": WAGE_RUNWAY_MATCHDAYS,
        "windows": "open | closed — buys only when open",
        "agent_to_agent": "structured bid / accept / reject",
    }
