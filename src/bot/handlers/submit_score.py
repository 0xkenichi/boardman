"""Submit match scores and screenshots for ClawStation challenges."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import F, Router, types
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.notify import notify_user

logger = logging.getLogger(__name__)

router = Router()


def _parse_args(text: str) -> tuple[Optional[str], Optional[int]]:
    parts = text.split(maxsplit=2)
    challenge_id = parts[1] if len(parts) > 1 else None
    try:
        score = int(parts[2]) if len(parts) > 2 else None
    except (ValueError, IndexError):
        score = None
    return challenge_id, score


async def _load_challenge(challenge_id: str) -> Optional[dict]:
    if not challenge_id:
        return None
    sb = get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    return result.data


async def _store_score(challenge_id: str, profile_id: str, score: int) -> dict:
    sb = get_supabase()
    challenge = await _load_challenge(challenge_id)
    if not challenge:
        raise ValueError("Challenge not found")

    is_creator = profile_id == challenge["creator_id"]
    is_opponent = profile_id == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        raise ValueError("Not a participant")

    status = challenge.get("status")
    if status not in ("locked", "creator_locked", "submitted"):
        raise ValueError(f"Challenge status is {status}, cannot submit score")

    column = "creator_score" if is_creator else "opponent_score"
    update: dict = {column: score}
    other_score = challenge.get("creator_score" if is_opponent else "opponent_score")
    if other_score is not None:
        update["status"] = "submitted"

    sb.schema("gaming").table("challenges").update(update).eq("id", challenge_id).execute()
    return challenge


@router.message(Command("submit_score"))
async def cmd_submit_score(message: types.Message) -> None:
    """Submit a numeric score for a challenge."""
    user = message.from_user
    if user is None or not message.text:
        return

    challenge_id, score = _parse_args(message.text)
    if not challenge_id or score is None:
        await message.answer(
            "Usage: `/submit_score <challenge_id> <score>`\n\n"
            "Example: `/submit_score 550e8400-e29b-41d4-a716-446655440000 3`",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    try:
        await _store_score(challenge_id, profile["id"], score)
    except ValueError as exc:
        await message.answer(f"❌ {exc}", reply_markup=back_menu())
        return

    await message.answer(
        f"✅ Score submitted: *{score}*\n\n"
        f"Challenge ID: `{challenge_id}`",
        reply_markup=back_menu(),
    )

    # Notify the other player if we now have both scores
    refreshed = await _load_challenge(challenge_id)
    if (
        refreshed
        and refreshed.get("creator_score") is not None
        and refreshed.get("opponent_score") is not None
    ):
        other_id = (
            refreshed["creator_id"]
            if profile["id"] == refreshed.get("opponent_id")
            else refreshed.get("opponent_id")
        )
        if other_id:
            await notify_user(
                other_id,
                f"📊 Both scores are in for challenge `{challenge_id}`.\n"
                f"Awaiting AI verification...",
            )


@router.message(F.photo)
async def photo_submit_score(message: types.Message) -> None:
    """Accept a screenshot as proof; caption must start with /submit_score <id>."""
    user = message.from_user
    caption = message.caption or ""
    if not caption.strip().startswith("/submit_score"):
        return

    challenge_id, score = _parse_args(caption)
    if not challenge_id:
        await message.answer(
            "❌ Photo caption must be: `/submit_score <challenge_id> [<score>]`",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    challenge = await _load_challenge(challenge_id)
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu())
        return

    is_creator = profile["id"] == challenge["creator_id"]
    is_opponent = profile["id"] == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        await message.answer("❌ You are not part of this challenge.", reply_markup=back_menu())
        return

    # Store largest photo file_id as the screenshot reference
    file_id = message.photo[-1].file_id if message.photo else None
    column = "screenshot_creator_url" if is_creator else "screenshot_opponent_url"

    sb = get_supabase()
    sb.schema("gaming").table("challenges").update({column: file_id}).eq("id", challenge_id).execute()

    reply = "✅ Screenshot received."
    if score is not None:
        try:
            await _store_score(challenge_id, profile["id"], score)
            reply += f" Score *{score}* recorded."
        except ValueError as exc:
            await message.answer(
                f"✅ Screenshot saved, but score error: {exc}",
                reply_markup=back_menu(),
            )
            return
    else:
        reply += " Now enter your score with `/submit_score <challenge_id> <score>`."

    await message.answer(reply, reply_markup=back_menu())
