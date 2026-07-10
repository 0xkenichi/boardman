"""Bot configuration loaded from environment variables."""
from __future__ import annotations

import os

from aiogram.enums import ParseMode


class Settings:
    """Runtime settings for the ClawStation Telegram bot."""

    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_CLAWSTATION") or os.getenv("TELEGRAM_BOT_TOKEN")
    BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME_CLAWSTATION") or os.getenv("TELEGRAM_BOT_USERNAME")
    MINIAPP_URL = os.getenv("MINIAPP_URL")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    ALLOWED_UPDATES = (
        [u.strip() for u in os.getenv("ALLOWED_UPDATES", "").split(",") if u.strip()]
        if os.getenv("ALLOWED_UPDATES")
        else None
    )
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PARSE_MODE = ParseMode.MARKDOWN


settings = Settings()
