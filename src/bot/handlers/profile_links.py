"""Handlers for linking gaming profiles (PSN, Xbox, email, bio)."""
from __future__ import annotations

import logging
import re

from aiogram import Router, types
from aiogram.filters import Command

from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile

logger = logging.getLogger(__name__)

router = Router()


EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def _parse_args(text: str) -> str | None:
    """Extract the argument after the command."""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


@router.message(Command("link_psn"))
async def cmd_link_psn(message: types.Message) -> None:
    """Link a PlayStation Network ID to the user's profile."""
    user = message.from_user
    if user is None:
        return

    psn_id = _parse_args(message.text or "")
    if not psn_id:
        await message.answer(
            "Usage: `/link_psn <psn_username>`\n\n"
            "Example: `/link_psn my_psn_id`",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    try:
        from backend.supabase_client import get_supabase

        sb = get_supabase()
        sb.table("profiles").update({"gaming_psn_id": psn_id}).eq("id", profile["id"]).execute()
    except Exception:
        logger.exception("[ProfileLinks] Failed to save PSN ID for %s", profile["id"])
        await message.answer("❌ Could not save PSN ID. Please try again later.", reply_markup=back_menu())
        return

    await message.answer(
        f"✅ PlayStation Network ID linked: `{psn_id}`",
        reply_markup=back_menu(),
    )


@router.message(Command("link_xbox"))
async def cmd_link_xbox(message: types.Message) -> None:
    """Link an Xbox Gamertag to the user's profile."""
    user = message.from_user
    if user is None:
        return

    xbox_tag = _parse_args(message.text or "")
    if not xbox_tag:
        await message.answer(
            "Usage: `/link_xbox <xbox_gamertag>`\n\n"
            "Example: `/link_xbox MyGamertag123`",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    try:
        from backend.supabase_client import get_supabase

        sb = get_supabase()
        sb.table("profiles").update({"gaming_xbox_id": xbox_tag}).eq("id", profile["id"]).execute()
    except Exception:
        logger.exception("[ProfileLinks] Failed to save Xbox Gamertag for %s", profile["id"])
        await message.answer("❌ Could not save Xbox Gamertag. Please try again later.", reply_markup=back_menu())
        return

    await message.answer(
        f"✅ Xbox Gamertag linked: `{xbox_tag}`",
        reply_markup=back_menu(),
    )


@router.message(Command("link_email"))
async def cmd_link_email(message: types.Message) -> None:
    """Link a backup email to the user's profile."""
    user = message.from_user
    if user is None:
        return

    email = _parse_args(message.text or "")
    if not email:
        await message.answer(
            "Usage: `/link_email <email>`\n\n"
            "Example: `/link_email gamer@example.com`",
            reply_markup=back_menu(),
        )
        return

    if not EMAIL_REGEX.match(email):
        await message.answer(
            "❌ Invalid email format. Please provide a valid email address.",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    try:
        from backend.supabase_client import get_supabase

        sb = get_supabase()
        sb.table("profiles").update({"gaming_backup_email": email}).eq("id", profile["id"]).execute()
    except Exception:
        logger.exception("[ProfileLinks] Failed to save backup email for %s", profile["id"])
        await message.answer("❌ Could not save email. Please try again later.", reply_markup=back_menu())
        return

    await message.answer(
        f"✅ Backup email linked: `{email}`",
        reply_markup=back_menu(),
    )


@router.message(Command("set_bio"))
async def cmd_set_bio(message: types.Message) -> None:
    """Set the user's gaming bio."""
    user = message.from_user
    if user is None:
        return

    bio = _parse_args(message.text or "")
    if not bio:
        await message.answer(
            "Usage: `/set_bio <your bio>`\n\n"
            "Example: `/set_bio Competitive FIFA player, love co-op games`",
            reply_markup=back_menu(),
        )
        return

    if len(bio) > 500:
        await message.answer(
            "❌ Bio is too long (max 500 characters).",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    try:
        from backend.supabase_client import get_supabase

        sb = get_supabase()
        sb.table("profiles").update({"gaming_bio": bio}).eq("id", profile["id"]).execute()
    except Exception:
        logger.exception("[ProfileLinks] Failed to save bio for %s", profile["id"])
        await message.answer("❌ Could not save bio. Please try again later.", reply_markup=back_menu())
        return

    await message.answer(
        f"✅ Bio updated:\n`{bio}`",
        reply_markup=back_menu(),
    )
