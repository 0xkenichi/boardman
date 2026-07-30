"""Handler for the /balance command — abstracted $ balance + $PLAY."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from gaming.src.backend.services.clawstation_circle import get_balance_summary
from gaming.src.backend.services.play_points import tier_from_play_points, tier_label
from gaming.src.bot.keyboards import wallet_menu
from gaming.src.bot.utils.db import get_or_create_profile

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    """Show spendable $ (on-chain) clearly; surface ledger credit if any."""
    import asyncio

    user = message.from_user
    if user is None:
        return

    profile = await get_or_create_profile(user)

    async def _summary():
        try:
            return await get_balance_summary(profile["id"])
        except Exception:
            logger.exception("[Balance] summary failed")
            return {
                "spendable_usdc": 0,
                "ledger_usdc": 0,
                "address": "",
                "chain_id": "arc",
            }

    async def _play():
        try:
            from backend.supabase_client import get_supabase

            r = (
                get_supabase()
                .table("profiles")
                .select("play_points,play_win_streak,play_best_streak")
                .eq("id", profile["id"])
                .limit(1)
                .execute()
            )
            row = (r.data or [None])[0] if r.data else None
            if not row:
                return 0, 0, 0
            return (
                int(row.get("play_points") or 0),
                int(row.get("play_win_streak") or 0),
                int(row.get("play_best_streak") or 0),
            )
        except Exception:
            return 0, 0, 0

    summary, play_tuple = await asyncio.gather(_summary(), _play())
    play, streak, best = play_tuple
    spendable = float(summary.get("spendable_usdc") or 0)
    ledger = float(summary.get("ledger_usdc") or 0)
    address = summary.get("address") or ""

    tier = tier_from_play_points(play)
    streak_txt = f"🔥 {streak}" if streak else "0"

    # Primary number = what you can stake (abstracted — no chain name)
    text = (
        f"💰 <b>Wallet</b>\n\n"
        f"Balance: <b>${spendable:,.2f}</b>\n"
        f"<i>This is what you can stake right now.</i>\n"
    )

    if ledger > 0.009 and ledger > spendable + 0.009:
        text += (
            f"\n📒 Account credit on file: <b>${ledger:,.2f}</b>\n"
            f"<i>Not on your play address yet — it can't be staked until you "
            f"fund with <b>Get USDC</b> (on-chain).</i>\n"
        )
    elif spendable < 0.01:
        text += (
            "\nYou're empty for matches. Tap <b>Get USDC</b>, wait ~30s, then "
            "<b>Refresh</b>.\n"
        )

    if address:
        text += (
            f"\n<b>Your fund address</b> (tap to copy)\n"
            f"<code>{escape(address)}</code>\n"
        )

    text += (
        f"\n🎮 PLAY: <b>{play:,}</b> · streak <b>{streak_txt}</b> (best {best})\n"
        f"Tier: <b>{escape(tier_label(tier))}</b>"
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=wallet_menu())
