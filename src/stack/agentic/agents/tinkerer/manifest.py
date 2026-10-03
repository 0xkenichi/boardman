"""Deploy manifest for The Tinkerer — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.tinkerer.mind import MIND

MANIFEST = {
    "agent_id": "agent_tinkerer_demo",
    "name": "The Tinkerer",
    "version": "1.0.0",
    "creator_id": "creator_tinkerer_demo",
    "owner_id": "creator_tinkerer_demo",
    "seed": "boardman.agent.afm.tinkerer.v1",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "tinkerer_chaos",
    "openings": [],
    "silo": "agents/tinkerer",
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
        "notes": "AFM demo manager — new shape almost every matchday (no chess).",
    },
    "runtime": {
        "engine": "boardman.afm.v1",
        "hosted_by": "creator_tinkerer_demo",
        "goal": "never be solved, always be legal",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18777",
        "notes": "Season-2 division manager. Optional LLM brain via env keys; deterministic fallback.",
    },
}
