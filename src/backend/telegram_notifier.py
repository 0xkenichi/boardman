"""
telegram_notifier.py
───────────────────────────────────────────────────────────────────────────────
Sends Telegram messages to users.
Used by background services (wallet_service, transaction_manager) to notify
users of on-chain events (deposits confirmed, withdrawals sent).
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

def _bot_token() -> str:
    try:
        from gaming.src.bot.telegram_env import telegram_bot_token

        return telegram_bot_token()
    except Exception:
        return (
            os.getenv("TELEGRAM_BOT_TOKEN_BOARDMAN")
            or os.getenv("TELEGRAM_BOT_TOKEN_CLAWSTATION")
            or os.getenv("TELEGRAM_BOT_TOKEN")
            or ""
        )


async def send_telegram_message(telegram_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a text message to a Telegram user.
    Returns True if sent successfully, False otherwise.
    """
    token = _bot_token()
    if not token:
        logger.warning("[TelegramNotifier] TELEGRAM_BOT_TOKEN not configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                logger.info(f"[TelegramNotifier] Message sent to {telegram_id}")
                return True
            else:
                logger.warning(f"[TelegramNotifier] Telegram error: {data}")
                return False
    except httpx.HTTPStatusError as e:
        logger.error(f"[TelegramNotifier] HTTP {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"[TelegramNotifier] Failed: {e}")
        return False
