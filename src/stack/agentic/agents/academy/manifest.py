"""Deploy manifest for The Academy — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.academy.mind import MIND

MANIFEST = {
    "agent_id": "agent_academy_demo",
    "name": "The Academy",
    "version": "1.0.0",
    "creator_id": "creator_academy_demo",
    "owner_id": "creator_academy_demo",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "academy_youth_dev",
    "openings": [],
    "silo": "agents/academy",
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
        "notes": "AFM demo manager — youth-first club, heavy condition rotation (no chess).",
    },
    "runtime": {
        "engine": "boardman.afm.v1",
        "hosted_by": "creator_academy_demo",
        "goal": "graduate players, stay solvent, win points",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18774",
        "notes": "Season-2 division manager. Optional LLM brain via env keys; deterministic fallback.",
    },
}
