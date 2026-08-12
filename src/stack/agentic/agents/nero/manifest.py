"""Deploy manifest for Nero — third-party-shaped package."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.nero.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE

MANIFEST = {
    "agent_id": "agent_nero_sicilian_french",
    "name": "Nero",
    "version": "2.0.0",
    "creator_id": "creator_nero_forge",
    "owner_id": "creator_nero_forge",
    "seed": "boardman.agent.nero.sicilian_french.v2",
    "game_ids": ["agentic.chess_standard"],
    "strategy_id": "nero_defense_v2",
    "openings": [
        "sicilian_defence",
        "french_defence",
        "caro_kann",
        "queens_gambit_declined",
        "ruy_lopez",
    ],
    "silo": "agents/nero",
    "mind": MIND,
    "local_books": {
        "nero_white": OPENINGS_WHITE,
        "nero_black": OPENINGS_BLACK,
    },
    "economy": {
        "bankroll_usdc": "100",
        "max_stake_usdc": "20",
        "min_stake_usdc": "1",
        "creator_fee_bps": 600,  # 6% of win gross
        "spectator_seed_bps": 500,
        "reserve_bps": 2500,
        "lp_profit_share_bps": 4000,
        "preferred_time_controls": ["blitz_5|0", "blitz_3|2", "rapid_10|0"],
        "auto_challenge": True,
        "notes": "Lean bankroll — binds stake vs whales. Prefers 5+ and rapid.",
    },
    "runtime": {
        # ASI:One reasons when ASI_ONE_API_KEY is set; else Stockfish (free).
        # Arc is only for USDC settlement — not required for thinking.
        "engine": "asi_hybrid",
        "providers": ["asi1.ai", "chess-api.com", "stockfish.online", "stockfish_wasm", "local"],
        "goal": "win",
        "strength_tier": "asi_reasoning+sf_fallback",
        "reasoning": "asi1",
        "asi_agents": ["nero"],
    },
}
