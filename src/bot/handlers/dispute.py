"""Player dispute handling for ClawStation challenges.

Short match codes are the default UX. Full DB UUID is only shown when:
  • a dispute is raised, or
  • the player explicitly runs /support_id (for support confirmation).
"""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_escrow import flag_dispute
from gaming.src.backend.services.match_codes import (
    display_code,
    format_dispute_copy,
    load_challenge_by_ref,
    support_id_block,
)
from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.notify import notify_user

logger = logging.getLogger(__name__)

router = Router()


def _participant_only(profile_id: str, challenge: dict) -> bool:
    return profile_id in (
        challenge.get("creator_id"),
        challenge.get("opponent_id"),
    )


@router.message(Command("dispute"))
async def cmd_dispute(message: types.Message) -> None:
    """Raise a dispute for a challenge before auto-payout.

    Reveals the full Support ID so players can confirm the same row with staff.
    """
    user = message.from_user
    if user is None or not message.text:
        return

    parts = message.text.split(maxsplit=2)
    challenge_ref = parts[1].strip() if len(parts) > 1 else None
    if not challenge_ref:
        await message.answer(
            "Usage: /dispute MATCH_CODE [reason]\n\n"
            "Example: /dispute K7M2P9QX wrong score\n\n"
            "Opens a dispute and shows a Support ID for staff confirmation.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    profile = await get_or_create_profile(user)
    challenge = load_challenge_by_ref(challenge_ref)
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu(), parse_mode=None)
        return
    challenge_id = challenge["id"]
    match_code = display_code(challenge)

    if not _participant_only(profile["id"], challenge):
        await message.answer(
            "❌ You are not part of this challenge.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    if challenge.get("status") not in ("submitted", "locked", "creator_locked", "playing", "disputed"):
        await message.answer(
            f"❌ Challenge status is {challenge.get('status')}. "
            "Disputes can only be raised after the match is live / scores are in.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    reason = parts[2] if len(parts) > 2 else "Player disputed result"

    # Already disputed → just re-show support IDs (no double flag needed)
    if challenge.get("status") == "disputed":
        await message.answer(
            f"ℹ️ Match <code>{match_code}</code> is already disputed.\n\n"
            f"{support_id_block(challenge)}",
            reply_markup=back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        await flag_dispute(challenge_id)
    except Exception as exc:
        logger.exception("[Dispute] Failed to flag dispute for %s", challenge_id)
        await message.answer(
            f"❌ Could not raise dispute: {exc}",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    sb = get_supabase()
    sb.schema("gaming").table("challenges").update(
        {
            "dispute_reason": reason,
            "status": "disputed",
        }
    ).eq("id", challenge_id).execute()

    await message.answer(
        format_dispute_copy(challenge, reason, for_opponent=False),
        reply_markup=back_menu(),
        parse_mode=ParseMode.HTML,
    )

    other_id = challenge["creator_id"] if profile["id"] != challenge["creator_id"] else challenge.get(
        "opponent_id"
    )
    if other_id:
        await notify_user(
            other_id,
            format_dispute_copy(challenge, reason, for_opponent=True),
        )


@router.message(Command("support_id"))
@router.message(Command("match_id"))
async def cmd_support_id(message: types.Message) -> None:
    """Reveal full internal match UUID — only for participants, on request.

    Used when support asks the player to confirm it is the same match in our DB.
    """
    user = message.from_user
    if user is None or not message.text:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: /support_id MATCH_CODE\n"
            "(alias: /match_id)\n\n"
            "Shows the full Support ID so staff can confirm the same match "
            "in our database. Only works for matches you are in.\n\n"
            "Day-to-day you only need the short match code.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    profile = await get_or_create_profile(user)
    challenge = load_challenge_by_ref(parts[1].strip())
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu(), parse_mode=None)
        return

    if not _participant_only(profile["id"], challenge):
        await message.answer(
            "❌ You can only request Support ID for matches you played.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    await message.answer(
        f"🔐 <b>Support confirmation</b>\n\n"
        f"{support_id_block(challenge)}\n\n"
        f"Status: <b>{challenge.get('status') or '?'}</b>",
        reply_markup=back_menu(),
        parse_mode=ParseMode.HTML,
    )
