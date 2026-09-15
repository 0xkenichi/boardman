"""Deploy manifest for Blue Lock — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.bluelock.mind import MIND

MANIFEST = {
    "agent_id": "agent_bluelock_demo",
    "name": "Blue Lock",
    "version": "1.1.0",
    "creator_id": "creator_bluelock_demo",
    "owner_id": "creator_bluelock_demo",
    "seed": "boardman.agent.afm.bluelock.v1",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "bluelock_striker_ego",
    "openings": [],
    "silo": "agents/bluelock",
    "mind": MIND,
    "local_books": {},
    "economy": {
        "bankroll_usdc": "500",
        "max_stake_usdc": "50",
        "min_stake_usdc": "1",
        "creator_fee_bps": 500,
        "spectator_seed_bps": 500,
        "reserve_bps": 1500,
        "lp_profit_share_bps": 4000,
        "preferred_time_controls": [],
        "auto_challenge": False,
        "notes": "AFM demo manager — club ownership, lineups, tactics (no chess).",
    },
    "runtime": {
        "engine": "boardman.afm.v1",
        "hosted_by": "creator_bluelock_demo",
        "goal": "win matches & grow the club",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18771",
        "notes": "Demo AFM manager persona for humans to watch. Sits alongside Raja/Nero chess bots.",
    },
}
