"""Wallet snapshot: the same numbers as Telegram /balance."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class WalletSnapshot:
    spendable: Decimal
    other: Decimal
    other_address: str
    ledger: Decimal
    address: str
    error: str
    play_points: int
    streak: int
    best_streak: int
    tier: str


async def snapshot(profile_id: str) -> WalletSnapshot:
    from gaming.src.backend.services.clawstation_circle import get_balance_summary
    from gaming.src.backend.services.play_points import tier_from_play_points, tier_label

    try:
        s = await get_balance_summary(profile_id)
    except Exception:
        logger.exception("[channels] balance summary failed")
        s = {"balance_error": "lookup failed"}

    def _play() -> tuple[int, int, int]:
        try:
            from backend.supabase_client import get_supabase

            r = (
                get_supabase().table("profiles")
                .select("play_points,play_win_streak,play_best_streak")
                .eq("id", profile_id).limit(1).execute()
            )
            row = (r.data or [None])[0] if r.data else None
            if not row:
                return 0, 0, 0
            return (int(row.get("play_points") or 0), int(row.get("play_win_streak") or 0),
                    int(row.get("play_best_streak") or 0))
        except Exception:
            return 0, 0, 0

    play, streak, best = await asyncio.to_thread(_play)
    return WalletSnapshot(
        spendable=Decimal(str(s.get("spendable_usdc") or 0)),
        other=Decimal(str(s.get("other_usdc") or 0)),
        other_address=str(s.get("other_address") or ""),
        ledger=Decimal(str(s.get("ledger_usdc") or 0)),
        address=str(s.get("address") or ""),
        error=str(s.get("balance_error") or ""),
        play_points=play,
        streak=streak,
        best_streak=best,
        tier=tier_label(tier_from_play_points(play)),
    )


async def play_address(profile_id: str) -> str:
    from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

    wallet = await ensure_user_wallet(profile_id, chain_id="arc")
    return str(wallet.get("address") or "")
