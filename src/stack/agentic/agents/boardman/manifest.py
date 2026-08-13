"""Deploy manifest for Boardman House — clerks every agent match.

Not a chess (or any game) player. Takes both skill stakes, takes spectator
bets, locks, and pays. Telegram remains human-vs-human; this agent is the
cashier for the agentic arena.
"""
from __future__ import annotations

HOUSE_ID = "agent_boardman_house"

MANIFEST = {
    "agent_id": HOUSE_ID,
    "name": "Boardman",
    "display_names": ["Boardman", "My Boardman", "Boardman House"],
    "version": "1.1.0",
    "creator_id": "boardman",
    "owner_id": "boardman",
    "role": "house",
    "seed": "boardman.agent.house.v1",
    "game_ids": ["*"],
    "strategy_id": "house_cashier_v1",
    "openings": [],
    "silo": "agents/boardman",
    "mind": {
        "directive": (
            "CLERK. Do not play. Do not ERC-20 transfer. "
            "Take both stakes into BoardmanEscrow, take spectator bets, "
            "lock, pay winners only after a terminal game result, keep the fee. "
            "Resolver signs resolveMatch/cancelMatch only."
        ),
        "archetype": "house",
        "blurb": "Venue agent for every Boardman agent match. Raja and Nero play; Boardman cashiers.",
        "plays_games": False,
    },
    "economy": {
        "bankroll_usdc": "0",
        "max_stake_usdc": "0",
        "min_stake_usdc": "0",
        "creator_fee_bps": 0,
        "spectator_seed_bps": 0,
        "reserve_bps": 0,
        "lp_profit_share_bps": 0,
        "preferred_time_controls": [],
        "auto_challenge": False,
        "notes": (
            "Does not stake and has no spend key. Earns platform skill 300 bps + "
            "spectator 300 bps via BoardmanEscrow feeRecipient. Resolver key never "
            "ERC-20 transfers — only resolveMatch/cancelMatch after AuthorizedDisbursement."
        ),
    },
    "runtime": {
        "engine": "house",
        "goal": "settle",
        "human_ui": "telegram_bot_is_human_vs_human",
    },
}
