"""Handler for the /balance command — show ALL money, never hide linked funds."""
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
    """Show stakeable balance + any funds on linked/old addresses."""
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
                "other_usdc": 0,
                "other_address": "",
                "ledger_usdc": 0,
                "address": "",
                "chain_id": "arc",
                "balance_error": "lookup failed",
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
    other = float(summary.get("other_usdc") or 0)
    other_addr = summary.get("other_address") or ""
    ledger = float(summary.get("ledger_usdc") or 0)
    address = summary.get("address") or ""
    err = summary.get("balance_error")

    tier = tier_from_play_points(play)
    streak_txt = f"🔥 {streak}" if streak else "0"

    # Headline = stakeable + other on-chain (user sees total money we know about)
    total_known = spendable + other
    text = (
        f"💰 <b>Wallet</b>\n\n"
        f"<b>Balance: ${total_known:,.2f}</b>\n"
    )

    if err and spendable < 0.01:
        text += f"⚠️ Could not refresh play wallet ({escape(str(err)[:80])}).\n"

    text += (
        f"\n<b>Play wallet</b> (stakes / matches)\n"
        f"${spendable:,.2f}\n"
    )
    if address:
        text += f"<code>{escape(address)}</code>\n"

    if other > 0.009 and other_addr:
        text += (
            f"\n⚠️ <b>Funds on another address: ${other:,.2f}</b>\n"
            f"<code>{escape(other_addr)}</code>\n"
            f"<i>This is NOT your play wallet — send USDC to the play address "
            f"above to stake. We will not hide this again.</i>\n"
        )

    if ledger > 0.009 and ledger > total_known + 0.009:
        text += (
            f"\n📒 Old account credit: ${ledger:,.2f} "
            f"<i>(legacy ledger — not on-chain)</i>\n"
        )

    if total_known < 0.01 and not err:
        text += (
            "\nEmpty for matches. Tap <b>Get money</b>, fund the "
            "<b>play wallet</b> address, wait ~30s, then <b>Refresh</b>.\n"
        )

    text += (
        f"\n🎮 PLAY: <b>{play:,}</b> · streak <b>{streak_txt}</b> (best {best})\n"
        f"Tier: <b>{escape(tier_label(tier))}</b>"
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=wallet_menu())
