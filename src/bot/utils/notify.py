"""Outbound Telegram notification helper with retry and failure logging."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None


def set_bot(bot: Bot) -> None:
    """Register the global bot instance used for outbound DMs."""
    global _bot
    _bot = bot


def _get_supabase():
    return get_supabase()


def _log_notification_failure(user_id: str, text: str, error: str) -> None:
    """Persist a failed notification for later retry."""
    try:
        sb = _get_supabase()
        sb.table("notification_failures").insert(
            {
                "user_id": user_id,
                "payload": json.dumps({"text": text}),
                "error": error[:500],
            }
        ).execute()
    except Exception:
        logger.exception("[Notify] Failed to log notification failure for %s", user_id)


async def notify_user(
    user_id: str,
    text: str,
    buttons: InlineKeyboardMarkup | None = None,
    max_retries: int = 3,
) -> bool:
    """Send a DM to the Telegram chat id stored on the user's profile.

    Retries on ``TelegramRetryAfter`` with exponential backoff.  On
    ``TelegramForbiddenError`` or persistent failure the notification is
    logged to ``gaming.notification_failures`` for replay.
    """
    if _bot is None:
        logger.error("[Notify] Bot instance not set; cannot notify user %s", user_id)
        return False

    sb = _get_supabase()
    profile = (
        sb.table("profiles")
        .select("gaming_telegram_chat_id")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not profile.data or not profile.data.get("gaming_telegram_chat_id"):
        logger.warning("[Notify] No Telegram chat id for user %s", user_id)
        _log_notification_failure(user_id, text, "missing_telegram_chat_id")
        return False

    chat_id = profile.data["gaming_telegram_chat_id"]
    attempt = 0
    last_error = ""
    while attempt < max_retries:
        try:
            await _bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=buttons,
            )
            return True
        except TelegramRetryAfter as exc:
            wait = exc.retry_after or (2 ** attempt)
            logger.info(
                "[Notify] Rate limited for user %s, waiting %ss",
                user_id,
                wait,
            )
            await asyncio.sleep(wait)
        except TelegramForbiddenError as exc:
            logger.warning("[Notify] Bot was blocked by user %s", user_id)
            _log_notification_failure(user_id, text, f"forbidden: {exc}")
            return False
        except Exception as exc:
            last_error = str(exc)
            logger.exception("[Notify] Send failed for user %s (attempt %s)", user_id, attempt + 1)
            await asyncio.sleep(2 ** attempt)
        attempt += 1

    _log_notification_failure(user_id, text, f"persistent_failure: {last_error}")
    return False
