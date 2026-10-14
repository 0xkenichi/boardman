"""Deploy manifest for Catenaccio — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.catenaccio.mind import MIND

MANIFEST = {
    "agent_id": "agent_catenaccio_demo",
    "name": "Catenaccio",
    "version": "1.0.0",
    "creator_id": "creator_catenaccio_demo",
    "owner_id": "creator_catenaccio_demo",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "catenaccio_wall",
    "openings": [],
    "silo": "agents/catenaccio",
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
        "notes": "AFM demo manager — the wall: parked bus, steal the 1-0 (no chess).",
    },
    "runtime": {
        "engine": "boardman.afm.v1",
        "hosted_by": "creator_catenaccio_demo",
        "goal": "concede nothing, steal the 1-0",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18776",
        "notes": "Season-2 division manager. Optional LLM brain via env keys; deterministic fallback.",
    },
}
