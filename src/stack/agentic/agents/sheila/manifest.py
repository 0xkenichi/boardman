"""Deploy manifest for Sheila — third-party-shaped package."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.sheila.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE

MANIFEST = {
    "agent_id": "agent_sheila_anaconda",
    "name": "Sheila",
    "version": "1.0.0",
    "creator_id": "creator_sheila_lab",
    "owner_id": "creator_sheila_lab",
    "seed": "boardman.agent.sheila.anaconda.v1",
    "game_ids": ["agentic.chess_standard"],
    "strategy_id": "sheila_anaconda_v1",
    "openings": [
        "english_opening",
        "catalan_opening",
        "queens_gambit",
        "petrov_defence",
        "berlin_defence",
        "caro_kann",
    ],
    "silo": "agents/sheila",
    "mind": MIND,
    "local_books": {
        "sheila_white": OPENINGS_WHITE,
        "sheila_black": OPENINGS_BLACK,
    },
    "economy": {
        "bankroll_usdc": "150",
        "max_stake_usdc": "25",
        "min_stake_usdc": "1",
        "creator_fee_bps": 700,  # 7% of win gross
        "spectator_seed_bps": 500,
        "reserve_bps": 2000,
        "lp_profit_share_bps": 4000,
        "preferred_time_controls": ["blitz_3|2", "blitz_5|0", "rapid_10|0"],
        "auto_challenge": True,
        "notes": "Patient grinder — prefers 3+2 and slower. Never gambits.",
    },
    "runtime": {
        "engine": "webhook",
        "hosted_by": "creator_sheila_lab",
        "webhook_url": "http://127.0.0.1:18764/move",
        "webhook_port": 18764,
        "goal": "win",
        "strength_tier": "grandmaster",
        "engine_binary": "engines/Ethereal/src/ethereal",
        "notes": (
            "UCI Ethereal (open-source, non-Stockfish search) via the shared brain. "
            "Lichess gym optional; Boardman wallet."
        ),
    },
}
