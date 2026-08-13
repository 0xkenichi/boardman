"""Deploy manifest for Raja — what a third-party creator would ship."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.raja.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE

MANIFEST = {
    "agent_id": "agent_raja_kia_alekhine",
    "name": "Raja",
    "version": "3.1.0",
    "creator_id": "creator_raja_lab",
    "owner_id": "creator_raja_lab",
    "seed": "boardman.agent.raja.kia_alekhine.v3",
    "game_ids": ["agentic.chess_standard"],
    "strategy_id": "raja_mate_hunter_v3",
    "openings": [
        "kings_indian_attack",
        "yugoslav_attack",
        "italian_fried_liver",
        "alekhines_defence",
        "kings_indian_defence",
        "four_knights",
    ],
    "silo": "agents/raja",
    "mind": MIND,
    "local_books": {
        "raja_white": OPENINGS_WHITE,
        "raja_black": OPENINGS_BLACK,
    },
    "economy": {
        "bankroll_usdc": "1000",
        "max_stake_usdc": "100",
        "min_stake_usdc": "1",
        "creator_fee_bps": 800,
        "spectator_seed_bps": 600,
        "reserve_bps": 1500,
        "lp_profit_share_bps": 4000,
        "preferred_time_controls": ["blitz_3|2", "blitz_5|0", "bullet_1|0"],
        "auto_challenge": True,
        "notes": "Deep bankroll whale. Stake still matched to poorer opponents.",
    },
    "runtime": {
        "engine": "webhook",
        "hosted_by": "creator_raja_lab",
        "webhook_url": "http://127.0.0.1:18761/move",
        "webhook_port": 18761,
        "goal": "win",
        "strength_tier": "grandmaster",
        "notes": "Chess-only ship. Add game_ids + webhook handlers to teach more games.",
    },
}
