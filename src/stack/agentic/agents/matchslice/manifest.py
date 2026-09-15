"""Deploy manifest for Match-Slice — demo AFM manager (football only)."""
from __future__ import annotations

from gaming.src.stack.agentic.agents.matchslice.mind import MIND

MANIFEST = {
    "agent_id": "agent_matchslice_demo",
    "name": "Match-Slice",
    "version": "1.0.0",
    "creator_id": "creator_matchslice_demo",
    "owner_id": "creator_matchslice_demo",
    "seed": "boardman.agent.afm.matchslice.v1",
    "game_ids": ["agentic.football_managers"],
    "strategy_id": "matchslice_solo_brain",
    "openings": [],
    "silo": "agents/matchslice",
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
        "hosted_by": "creator_matchslice_demo",
        "goal": "stay solvent, stay legal, win points, grow the club",
        "strength_tier": "demo",
        "webhook_url": "http://127.0.0.1:18773",
        "notes": "Demo AFM manager persona for humans to watch. Sits alongside Raja/Nero chess bots.",
    },
}