"""Channel flags and settings, all read from the environment at call time.

Flags (see docs/RUNBOOK.md, "Channels"):

``CHANNELS_CORE_FLOWS``
    Comma list of flows the shared core handles (``balance,deposit,link,withdraw``
    or ``all``). Default empty: Telegram keeps its legacy handlers.
``CHANNELS_CORE_FLOWS_<CHANNEL>``
    Per-channel override, e.g. ``CHANNELS_CORE_FLOWS_WHATSAPP=all``.
``WHATSAPP_ENABLED``
    ``1`` mounts the WhatsApp webhook. Off by default.
``TELEGRAM_WITHDRAW_WEB_PIN``
    Default on: Telegram withdrawals confirm through a one-time web link and a
    PIN entered on the site, never a password typed into the chat.
"""
from __future__ import annotations

import os

PORTED_FLOWS = ("balance", "deposit", "link", "withdraw")

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def _parse_flows(raw: str) -> frozenset[str]:
    parts = {p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()}
    if "all" in parts:
        return frozenset(PORTED_FLOWS)
    return frozenset(p for p in parts if p in PORTED_FLOWS)


def enabled_flows(channel: str) -> frozenset[str]:
    """Flows the core owns on ``channel`` (per-channel override wins)."""
    specific = os.getenv(f"CHANNELS_CORE_FLOWS_{channel.upper()}")
    if specific is not None:
        return _parse_flows(specific)
    return _parse_flows(os.getenv("CHANNELS_CORE_FLOWS") or "")


def flow_enabled(channel: str, flow: str) -> bool:
    return flow in enabled_flows(channel)


def whatsapp_enabled() -> bool:
    return _flag("WHATSAPP_ENABLED", False)


def telegram_web_pin() -> bool:
    return _flag("TELEGRAM_WITHDRAW_WEB_PIN", True)


def site_url() -> str:
    """Public site base for one-time links (no trailing slash)."""
    raw = (
        os.getenv("CHANNELS_SITE_URL")
        or os.getenv("BOARDMAN_URL")
        or os.getenv("BOARDMAN_SITE_URL")
        or "https://boardman.playingsidequest.fun"
    )
    return raw.strip().rstrip("/")


def whatsapp_display_number() -> str:
    """Business number in international digits (for wa.me links), or ''."""
    return "".join(c for c in (os.getenv("WHATSAPP_DISPLAY_NUMBER") or "") if c.isdigit())


def telegram_bot_username() -> str:
    try:
        from gaming.src.bot.telegram_env import telegram_bot_username as _u

        return _u() or ""
    except Exception:
        return (os.getenv("TELEGRAM_BOT_USERNAME_BOARDMAN") or "").lstrip("@")


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default
