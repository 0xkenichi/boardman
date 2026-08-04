"""Handler for /profile and /playbook."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from gaming.src.bot.keyboards import back_menu, main_menu
from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag

logger = logging.getLogger(__name__)

router = Router()


def _format_profile(profile: dict, history: list | None = None) -> str:
    from gaming.src.backend.services.play_points import tier_from_play_points, tier_label
    from gaming.src.backend.services.rematch_public import reputation_score

    name = escape(str(profile.get("display_name") or "Anonymous"))
    tag = escape(str(profile.get("gaming_tag") or "Not set"))
    play = int(profile.get("play_points") or 0)
    tier = tier_from_play_points(play)
    streak = int(profile.get("play_win_streak") or 0)
    best = int(profile.get("play_best_streak") or 0)
    wins = int(profile.get("gaming_wins") or profile.get("total_wins") or 0)
    losses = int(profile.get("gaming_losses") or profile.get("total_losses") or 0)
    draws = int(profile.get("gaming_draws") or 0)
    rep = reputation_score(wins, losses, draws, play)
    streak_txt = f"🔥 {streak}" if streak else "0"
    text = (
        f"👤 <b>Rematch profile</b>\n\n"
        f"Name: <b>{name}</b>\n"
        f"Tag: <code>@{tag}</code>\n\n"
        f"🎮 <b>PLAY:</b> <b>{play:,}</b>\n"
        f"Tier: <b>{escape(tier_label(tier))}</b>\n"
        f"Reputation: <b>{rep}/100</b>\n"
        f"Hot streak: <b>{streak_txt}</b> (best {best})\n"
        f"W / L / D: <b>{wins}</b> / <b>{losses}</b> / <b>{draws}</b>\n"
    )
    if history:
        text += "\n📜 <b>Recent matches</b>\n"
        for h in history[:8]:
            text += (
                f"• <code>{escape(str(h.get('code')))}</code> "
                f"{escape(str(h.get('result') or '—'))} "
                f"${h.get('stake') or '?'} {escape(str(h.get('chain') or ''))} "
                f"({escape(str(h.get('status') or ''))})\n"
            )
    text += "\nLeaderboard: playingsidequest.fun/rematch/leaderboard"
    return text


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
        history = []
        try:
            from gaming.src.backend.services.rematch_public import get_match_history

            history = get_match_history(opponent["id"], 6)
        except Exception:
            pass
        await message.answer(
            _format_profile(opponent, history), parse_mode=ParseMode.HTML
        )
        return

    profile = await get_or_create_profile(user)
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

    history = []
    try:
        from gaming.src.backend.services.rematch_public import get_match_history

        history = get_match_history(profile["id"], 8)
    except Exception:
        logger.warning("[Profile] history failed", exc_info=True)

    await message.answer(
        _format_profile(profile, history),
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.message(Command("playbook"))
async def cmd_playbook(message: types.Message) -> None:
    """In-bot PLAY score guide (short — what players need only)."""
    from gaming.src.bot.utils.flow import play_points_short

    await message.answer(
        play_points_short(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


def _can_view_ops_metrics(user: types.User | None) -> bool:
    """Full ops metrics are owner-only (@stillkenichi / admin Telegram IDs)."""
    if not user:
        return False
    from gaming.src.backend.services.safety import is_admin

    if is_admin(user.id):
        return True
    # Hard-allow owner handle even if CLAW_ADMIN_TELEGRAM_IDS is unset
    uname = (user.username or "").strip().lower()
    if uname == "stillkenichi":
        return True
    return False


@router.message(Command("leaderboard"))
@router.message(Command("board"))
@router.message(Command("stats"))
async def cmd_board(message: types.Message) -> None:
    """Public leaderboard only (no internal ops metrics)."""
    from gaming.src.backend.services.rematch_public import (
        format_leaderboard_text,
        get_leaderboard,
    )

    try:
        import asyncio

        lb = await asyncio.to_thread(get_leaderboard, 15)
        text = format_leaderboard_text(lb, 15)
    except Exception as exc:
        text = f"❌ Could not load board: {escape(str(exc))}"
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())


@router.message(Command("metrics"))
async def cmd_metrics(message: types.Message) -> None:
    """Owner-only testnet ops metrics (users, volume, fees, gas)."""
    user = message.from_user
    if not _can_view_ops_metrics(user):
        await message.answer(
            "That command is for the operator only.\n"
            "Use /board or /leaderboard for the public standings.",
            reply_markup=main_menu(),
        )
        return

    from gaming.src.backend.services.rematch_public import (
        format_metrics_text,
        get_ops_metrics,
    )

    try:
        import asyncio

        metrics = await asyncio.to_thread(get_ops_metrics)
        text = format_metrics_text(metrics)
    except Exception as exc:
        text = f"❌ Could not load metrics: {escape(str(exc))}"
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())
