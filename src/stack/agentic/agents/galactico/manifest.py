"""Deploy manifest for Galáctico — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.galactico.mind import MIND

MANIFEST = {
    "agent_id": "agent_galactico_demo",
    "name": "Galáctico",
    "version": "1.0.0",
    "creator_id": "creator_galactico_demo",
    "owner_id": "creator_galactico_demo",
    "seed": "boardman.agent.afm.galactico.v1",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "galactico_stars",
    "openings": [],
    "silo": "agents/galactico",
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
        "notes": "AFM demo manager — stars-first club, all-out attack (no chess).",
    },
    "runtime": {
        "engine": "boardman.afm.v1",
        "hosted_by": "creator_galactico_demo",
        "goal": "sign the stars, win beautifully, never park the bus",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18775",
        "notes": "Season-2 division manager. Optional LLM brain via env keys; deterministic fallback.",
    },
}
