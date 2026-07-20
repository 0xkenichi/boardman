"""Handler for the /balance command — multi-chain USDC + $PLAY."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from gaming.src.backend.services.clawstation_circle import (
    get_all_chain_balances,
    get_preferred_chain,
    get_usdc_balance,
)
from gaming.src.backend.services.play_points import tier_from_play_points, tier_label
from gaming.src.bot.keyboards import wallet_menu
from gaming.src.bot.utils.db import get_or_create_profile

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    """Show USDC (active chain first for speed) + $PLAY."""
    import asyncio

    user = message.from_user
    if user is None:
        return

    # Fast path: acknowledge immediately if called from a long chain of work
    profile = await get_or_create_profile(user)
    pref = "arc"
    try:
        pref = await get_preferred_chain(profile["id"])
    except Exception:
        pass

    lines = []
    address = ""

    # Parallel: preferred balance + deposit address + play stats (fast wallet open)
    async def _pref_bal():
        try:
            return await get_usdc_balance(profile["id"], chain_id=pref)
        except Exception:
            return None

    async def _address():
        try:
            from gaming.src.backend.services.clawstation_circle import get_deposit_address

            return await get_deposit_address(profile["id"], chain_id=pref)
        except Exception:
            return ""

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

    bal, address, play_tuple = await asyncio.gather(_pref_bal(), _address(), _play())
    play, streak, best = play_tuple

    from gaming.src.backend.services.chains import get_chain

    pref_label = get_chain(pref).get("label", pref)
    if bal is not None:
        gas = get_chain(pref).get("gas_token", "?")
        gas_note = "USDC gas" if get_chain(pref).get("gas_mode") == "usdc_native" else f"{gas} gas"
        lines.append(
            f"• <b>{escape(pref_label)}</b>: <b>${bal:,.2f}</b> USDC ({gas_note}) ← active"
        )
    else:
        lines.append(f"• <b>{escape(pref_label)}</b>: (could not load)")

    # Arc-first UI: other chains only if CLAW_WALLET_ALL_CHAINS=1
    import os

    addr_lines = []
    if address:
        addr_lines.append(f"<code>{escape(address)}</code>")

    if os.getenv("CLAW_WALLET_ALL_CHAINS", "0") == "1":
        try:
            rows = await asyncio.wait_for(get_all_chain_balances(profile["id"]), timeout=18)
            for r in rows:
                if r["id"] == pref:
                    if r.get("address"):
                        address = r["address"]
                        addr_lines = [f"<code>{escape(r['address'])}</code>"]
                    continue
                gas = "USDC gas" if r.get("gas_mode") == "usdc_native" else f"{r.get('gas_token')} gas"
                lines.append(
                    f"• <b>{escape(r['label'])}</b>: "
                    f"<b>${r['balance_usdc']:,.2f}</b> USDC ({gas})"
                )
                if r.get("address"):
                    addr_lines.append(
                        f"<b>{escape(r['label'])}</b>:\n<code>{escape(r['address'])}</code>"
                    )
        except Exception:
            logger.warning("[Balance] other chains timed out or failed")

    tier = tier_from_play_points(play)
    streak_txt = f"🔥 {streak}" if streak else "0"
    addr_block = (
        "\n\n<b>Your Arc address</b>\n" + "\n".join(addr_lines) + "\n" if addr_lines else "\n"
    )

    text = (
        f"💰 <b>Wallet</b>\n\n"
        f"<b>Balance</b>\n"
        + ("\n".join(lines) if lines else "—")
        + addr_block
        + f"\n"
        f"🎮 PLAY: <b>{play:,}</b> · streak <b>{streak_txt}</b> (best {best})\n"
        f"Tier: <b>{escape(tier_label(tier))}</b>\n\n"
        f"Need funds? Tap <b>Get USDC</b>.\n"
        f"Withdraw when you're ready."
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=wallet_menu())
