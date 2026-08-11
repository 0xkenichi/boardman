"""Resolve Boardman Telegram bot credentials from environment.

Priority prefers the Boardman (myboardmanOfficialBot) names, then legacy
ClawStation / generic aliases so existing deploy envs keep working.
"""
from __future__ import annotations

import os

# Default public bot after Boardman rebrand
DEFAULT_BOT_USERNAME = "myboardmanOfficialBot"
DEFAULT_BOT_URL = f"https://t.me/{DEFAULT_BOT_USERNAME}"


def telegram_bot_token() -> str:
    """Bot API token for the live Boardman bot."""
    return (
        os.getenv("TELEGRAM_BOT_TOKEN_BOARDMAN")
        or os.getenv("TELEGRAM_BOT_TOKEN_MYBOARDMAN")
        or os.getenv("TELEGRAM_BOT_TOKEN_CLAWSTATION")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()


def telegram_bot_username() -> str:
    """Public @username without leading @."""
    raw = (
        os.getenv("TELEGRAM_BOT_USERNAME_MYBOARDMAN")
        or os.getenv("TELEGRAM_BOT_USERNAME_BOARDMAN")
        or os.getenv("TELEGRAM_BOT_USERNAME_CLAWSTATION")
        or os.getenv("NEXT_PUBLIC_TELEGRAM_BOT_USERNAME")
        or os.getenv("TELEGRAM_BOT_USERNAME")
        or DEFAULT_BOT_USERNAME
    )
    return raw.strip().lstrip("@")


def telegram_bot_url() -> str:
    """https://t.me/<username> deep link."""
    explicit = (
        os.getenv("NEXT_PUBLIC_TELEGRAM_BOT_URL")
        or os.getenv("TELEGRAM_BOT_URL")
        or ""
    ).strip()
    if explicit:
        if not explicit.startswith("http"):
            explicit = f"https://{explicit.lstrip('/')}"
        return explicit.rstrip("/")
    return f"https://t.me/{telegram_bot_username()}"
