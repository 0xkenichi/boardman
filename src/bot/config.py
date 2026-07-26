"""Bot configuration loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Load .env from likely roots:
    # - standalone: rematch/src/bot/config.py -> parents[2] = rematch/
    # - monorepo:   gaming/src/bot/config.py  -> parents[3] = sideQuest/
    _here = Path(__file__).resolve()
    for _root in (_here.parents[2], _here.parents[3], Path.cwd()):
        load_dotenv(_root / ".env")
    load_dotenv()  # cwd fallback
except ImportError:
    pass

from aiogram.enums import ParseMode


class Settings:
    """Runtime settings for the ClawStation Telegram bot."""

    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_CLAWSTATION") or os.getenv("TELEGRAM_BOT_TOKEN")
    BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME_CLAWSTATION") or os.getenv("TELEGRAM_BOT_USERNAME")
    MINIAPP_URL = os.getenv("MINIAPP_URL")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    # Default to polling so local demos work even if WEBHOOK_URL is set for other services.
    # Production: set CLAWSTATION_BOT_MODE=webhook (and WEBHOOK_URL).
    BOT_MODE = (os.getenv("CLAWSTATION_BOT_MODE") or os.getenv("BOT_MODE") or "polling").lower()
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
    ALLOWED_UPDATES = (
        [u.strip() for u in os.getenv("ALLOWED_UPDATES", "").split(",") if u.strip()]
        if os.getenv("ALLOWED_UPDATES")
        else None
    )
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    # HTML is safer than Markdown: gaming tags / addresses often contain `_`.
    PARSE_MODE = ParseMode.HTML

    @property
    def use_webhook(self) -> bool:
        return self.BOT_MODE in ("webhook", "wh") and bool(self.WEBHOOK_URL)


settings = Settings()
