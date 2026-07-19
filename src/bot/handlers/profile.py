"""Handler for /profile and /playbook."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag

logger = logging.getLogger(__name__)

router = Router()


def _format_profile(profile: dict) -> str:
    from gaming.src.backend.services.play_points import tier_from_play_points, tier_label

    name = escape(str(profile.get("display_name") or "Anonymous"))
    tag = escape(str(profile.get("gaming_tag") or "Not set"))
    play = int(profile.get("play_points") or 0)
    tier = tier_from_play_points(play)
    streak = int(profile.get("play_win_streak") or 0)
    best = int(profile.get("play_best_streak") or 0)
    wins = int(profile.get("gaming_wins") or profile.get("total_wins") or 0)
    losses = int(profile.get("gaming_losses") or profile.get("total_losses") or 0)
    draws = int(profile.get("gaming_draws") or 0)
    streak_txt = f"🔥 {streak}" if streak else "0"
    return (
        f"👤 <b>Profile</b>\n\n"
        f"Name: <b>{name}</b>\n"
        f"Tag: <code>@{tag}</code>\n\n"
        f"🎮 <b>$PLAY:</b> <b>{play:,}</b>\n"
        f"Tier: <b>{escape(tier_label(tier))}</b>\n"
        f"Hot streak: <b>{streak_txt}</b> (best {best})\n"
        f"W / L / D: <b>{wins}</b> / <b>{losses}</b> / <b>{draws}</b>\n\n"
        f"Tier climbs with $PLAY — /playbook"
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
            await message.answer(
                f"❌ Player <code>@{escape(tag)}</code> not found.",
                parse_mode=ParseMode.HTML,
            )
            return
        # Refresh play fields if missing from select
        await message.answer(_format_profile(opponent), parse_mode=ParseMode.HTML)
        return

    profile = await get_or_create_profile(user)
    # Reload with play columns
    try:
        from backend.supabase_client import get_supabase

        r = (
            get_supabase()
            .table("profiles")
            .select(
                "id,display_name,gaming_tag,gaming_tier,gaming_reputation_score,"
                "play_points,play_win_streak,play_best_streak,"
                "gaming_wins,gaming_losses,gaming_draws"
            )
            .eq("id", profile["id"])
            .limit(1)
            .execute()
        )
        row = r.data[0] if r.data else profile
        profile = {**profile, **row}
    except Exception:
        logger.warning("[Profile] extended select failed", exc_info=True)

    await message.answer(
        _format_profile(profile), parse_mode=ParseMode.HTML, reply_markup=back_menu()
    )


@router.message(Command("playbook"))
async def cmd_playbook(message: types.Message) -> None:
    """In-bot $PLAY playbook (short)."""
    text = (
        "📖 <b>$PLAY Playbook</b>\n\n"
        "$PLAY is ClawStation participation score — <b>not USDC</b>.\n"
        "Both winners <i>and</i> losers earn points. Streaks boost wins.\n"
        "May unlock perks later.\n\n"
        "<b>Earn</b>\n"
        "• Win: <b>+100</b> × hot streak\n"
        "• Loss: <b>+40</b> (you showed up)\n"
        "• Draw: <b>+50</b> each\n"
        "• No-show (ghosted): <b>−50</b> — never reward bad behaviour\n"
        "• Stake bonus: up to <b>+50</b>\n\n"
        "<b>Hot streak</b> (wins only)\n"
        "2-win: ×1.15 · 5-win: ×1.60 · 10-win: ×2.50\n"
        "A loss resets the streak.\n\n"
        "<b>Tier</b> (from $PLAY total)\n"
        "Bronze 0 · Silver 500 · Gold 2k · Platinum 5k · Diamond 10k\n"
        "Badge for how much you play — future perks possible.\n\n"
        "<b>Rules</b>\n"
        "• One match at a time\n"
        "• Report with FT photo so no-show can't steal your win\n"
        "• /balance · /profile\n\n"
        "Full doc: gaming/docs/PLAYBOOK.md"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=back_menu())
