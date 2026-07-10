"""Handler for the /profile command."""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag

logger = logging.getLogger(__name__)

router = Router()


def _format_profile(profile: dict) -> str:
    name = profile.get("display_name") or "Anonymous"
    tag = profile.get("gaming_tag") or "Not set"
    tier = profile.get("gaming_tier", "bronze")
    reputation = profile.get("gaming_reputation_score", 1000)
    wins = profile.get("total_wins", 0)
    losses = profile.get("total_losses", 0)
    return (
        f"👤 *Profile*\n\n"
        f"Name: *{name}*\n"
        f"Tag: `@{tag}`\n"
        f"Tier: *{tier.title()}*\n"
        f"Reputation: *{reputation}*\n"
        f"W/L: *{wins} / {losses}*"
    )


@router.message(Command("profile"))
async def cmd_profile(message: types.Message) -> None:
    """Show own profile or look up another user by gaming tag."""
    user = message.from_user
    if user is None:
        return

    args = message.text.split(maxsplit=1)[1:] if message.text else []
    if args:
        tag = args[0].lstrip("@")
        opponent = await get_profile_by_tag(tag)
        if not opponent:
            await message.answer(f"❌ Player `@{tag}` not found.")
            return
        await message.answer(_format_profile(opponent))
        return

    profile = await get_or_create_profile(user)
    await message.answer(_format_profile(profile))
