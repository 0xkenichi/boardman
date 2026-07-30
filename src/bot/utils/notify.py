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


def _ensure_bot() -> Optional[Bot]:
    """Use registered bot, or build one from env (background jobs / scripts)."""
    global _bot
    if _bot is not None:
        return _bot
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN_CLAWSTATION") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        _bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        logger.info("[Notify] Created bot instance from env for outbound DMs")
        return _bot
    except Exception:
        logger.exception("[Notify] Failed to create bot from env")
        return None


async def get_balance_snapshot(user_id: str) -> str:
    """HTML lines: spendable $ (abstracted) + $PLAY — no chain names."""
    usdc_s = "—"
    play_s = "—"
    streak_s = ""
    note = ""
    try:
        from gaming.src.backend.services.clawstation_circle import get_balance_summary

        s = await get_balance_summary(user_id)
        spend = float(s.get("spendable_usdc") or 0)
        ledger = float(s.get("ledger_usdc") or 0)
        usdc_s = f"${spend:,.2f}"
        if ledger > 0.009 and ledger > spend + 0.009:
            note = f"\n📒 Credit on file: ${ledger:,.2f} (not stakeable yet)"
    except Exception:
        logger.warning("[Notify] USDC balance fetch failed for %s", user_id, exc_info=True)
    try:
        sb = _get_supabase()
        r = (
            sb.table("profiles")
            .select("play_points,play_win_streak")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = (r.data or [None])[0] if r.data else None
        if row:
            play_s = f"{int(row.get('play_points') or 0):,}"
            st = int(row.get("play_win_streak") or 0)
            if st:
                streak_s = f" · 🔥 streak {st}"
    except Exception:
        logger.warning("[Notify] PLAY balance fetch failed for %s", user_id, exc_info=True)
    return f"💵 Balance: <b>{usdc_s}</b>{note}\n🎮 $PLAY: <b>{play_s}</b>{streak_s}"


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
    bot = _ensure_bot()
    if bot is None:
        logger.error("[Notify] Bot instance not set; cannot notify user %s", user_id)
        return False

    sb = _get_supabase()
    try:
        result = (
            sb.table("profiles")
            .select("gaming_telegram_chat_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.exception("[Notify] profile lookup failed for %s", user_id)
        _log_notification_failure(user_id, text, f"profile_lookup: {exc}")
        return False

    row = None
    if result is not None and result.data:
        row = result.data[0] if isinstance(result.data, list) else result.data
    if not row or not row.get("gaming_telegram_chat_id"):
        logger.warning("[Notify] No Telegram chat id for user %s", user_id)
        _log_notification_failure(user_id, text, "missing_telegram_chat_id")
        return False

    chat_id = row["gaming_telegram_chat_id"]
    attempt = 0
    last_error = ""
    while attempt < max_retries:
        try:
            # Prefer HTML (tags/addresses). Fall back to plain if parse fails.
            try:
                from aiogram.enums import ParseMode

                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=buttons,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as parse_exc:
                if "parse entities" in str(parse_exc).lower() or "can't parse" in str(parse_exc).lower():
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=buttons,
                        parse_mode=None,
                    )
                else:
                    raise
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
