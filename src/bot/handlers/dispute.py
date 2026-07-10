"""Player dispute handling for ClawStation challenges."""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_escrow import flag_dispute
from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.notify import notify_user

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("dispute"))
async def cmd_dispute(message: types.Message) -> None:
    """Raise a dispute for a challenge before auto-payout."""
    user = message.from_user
    if user is None or not message.text:
        return

    parts = message.text.split(maxsplit=2)
    challenge_id = parts[1].strip() if len(parts) > 1 else None
    if not challenge_id:
        await message.answer(
            "Usage: `/dispute <challenge_id>`\n\n"
            "Example: `/dispute 550e8400-e29b-41d4-a716-446655440000`",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)

    sb = get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    challenge = result.data
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu())
        return

    is_creator = profile["id"] == challenge["creator_id"]
    is_opponent = profile["id"] == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        await message.answer("❌ You are not part of this challenge.", reply_markup=back_menu())
        return

    if challenge.get("status") not in ("submitted", "locked", "creator_locked"):
        await message.answer(
            f"❌ Challenge status is *{challenge.get('status')}*. Disputes can only be raised after scores are submitted.",
            reply_markup=back_menu(),
        )
        return

    reason = parts[2] if len(parts) > 2 else "Player disputed result"

    try:
        await flag_dispute(challenge_id)
    except Exception as exc:
        logger.exception("[Dispute] Failed to flag dispute for %s", challenge_id)
        await message.answer(f"❌ Could not raise dispute: {exc}", reply_markup=back_menu())
        return

    # Update dispute reason in DB
    sb.schema("gaming").table("challenges").update(
        {
            "dispute_reason": reason,
            "status": "disputed",
        }
    ).eq("id", challenge_id).execute()

    await message.answer(
        f"⚠️ *Dispute raised* for challenge `{challenge_id}`.\n\n"
        f"Reason: `{reason}`\n\n"
        f"An admin will review the screenshots and resolve the match.",
        reply_markup=back_menu(),
    )

    other_id = challenge["creator_id"] if not is_creator else challenge.get("opponent_id")
    if other_id:
        await notify_user(
            other_id,
            f"⚠️ Your opponent disputed challenge `{challenge_id}`.\n"
            f"Reason: `{reason}`\n\n"
            f"An admin will review and resolve the match.",
        )
