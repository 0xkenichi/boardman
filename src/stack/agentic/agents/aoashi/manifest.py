"""Deploy manifest for Ao Ashi — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.aoashi.mind import MIND

MANIFEST = {
    "agent_id": "agent_aoashi_demo",
    "name": "Ao Ashi",
    "version": "1.1.0",
    "creator_id": "creator_aoashi_demo",
    "owner_id": "creator_aoashi_demo",
    "seed": "boardman.agent.afm.aoashi.v1",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "aoashi_total_football",
    "openings": [],
    "silo": "agents/aoashi",
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
        "hosted_by": "creator_aoashi_demo",
        "goal": "win matches & grow the club",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18772",
        "notes": "Demo AFM manager persona for humans to watch. Sits alongside Raja/Nero chess bots.",
    },
}
