"""Supabase-backed helpers for ClawStation bot profiles."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram.types import User

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


def _display_name(user: User) -> str:
    if user.full_name:
        return user.full_name
    return user.username or "Gamer"


def _gaming_tag(user: User) -> str | None:
    base = (user.username or f"gamer{user.id}")[:20]
    return f"sq_{base}_{user.id}"[:32]


async def get_or_create_profile(user: User) -> dict:
    """Get or create a profile for a Telegram user.

    The profile is identified by ``telegram_id``.  The legacy external-id
    format ``tg_<telegram_id>`` is preserved in the docstring contract but
    the canonical lookup is the native ``telegram_id`` column.
    """
    sb = _get_supabase()
    table = sb.table("profiles")
    existing = (
        table.select("id, display_name, gaming_tag, gaming_tier, gaming_reputation_score, telegram_id, gaming_tx_password_hash, circle_wallet_id, gaming_deposit_address, gaming_psn_id, gaming_xbox_id, gaming_backup_email, gaming_bio")
        .eq("telegram_id", user.id)
        .maybe_single()
        .execute()
    )
    if existing.data:
        return existing.data

    insert_data = {
        "telegram_id": user.id,
        "display_name": _display_name(user),
        "gaming_tag": _gaming_tag(user),
    }
    try:
        created = table.insert(insert_data).execute()
    except Exception as exc:
        logger.exception("[DB] Failed to create profile for telegram_id=%s", user.id)
        raise RuntimeError("Failed to create profile") from exc

    if not created.data:
        raise RuntimeError("Profile creation returned no data")
    return created.data[0]


async def get_profile_by_tag(tag: str) -> Optional[dict]:
    """Look up a profile by its ``gaming_tag``."""
    sb = _get_supabase()
    result = (
        sb.table("profiles")
        .select("id, display_name, gaming_tag, gaming_tier, gaming_reputation_score, gaming_telegram_chat_id, telegram_id, gaming_tx_password_hash, circle_wallet_id, gaming_deposit_address")
        .eq("gaming_tag", tag.lstrip("@"))
        .maybe_single()
        .execute()
    )
    return result.data if result.data else None


async def update_telegram_chat_id(user_id: str, chat_id: int) -> None:
    """Cache the user's Telegram chat id on their profile."""
    sb = _get_supabase()
    try:
        sb.table("profiles").update({"gaming_telegram_chat_id": chat_id}).eq("id", user_id).execute()
    except Exception:
        logger.exception("[DB] Failed to update gaming_telegram_chat_id for %s", user_id)
        raise
