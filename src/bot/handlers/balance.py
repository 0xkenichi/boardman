"""Handler for the /balance command."""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from gaming.src.backend.services.clawstation_circle import get_usdc_balance
from gaming.src.bot.utils.db import get_or_create_profile

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("balance"))
async def cmd_balance(message: types.Message) -> None:
    """Show USDC balance plus reputation score and tier."""
    user = message.from_user
    if user is None:
        return

    profile = await get_or_create_profile(user)
    try:
        balance = await get_usdc_balance(profile["id"])
    except Exception as exc:
        logger.exception("[Balance] Failed to fetch balance for %s", profile["id"])
        await message.answer(f"❌ Could not fetch balance: {exc}")
        return

    reputation = profile.get("gaming_reputation_score", 1000)
    tier = profile.get("gaming_tier", "bronze")
    text = (
        f"💰 *Wallet Balance*\n\n"
        f"USDC: *${balance:,.2f}*\n"
        f"Reputation: *{reputation}*\n"
        f"Tier: *{tier.title()}*"
    )
    await message.answer(text)
