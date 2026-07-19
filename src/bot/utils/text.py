"""Safe Telegram text helpers (HTML parse mode)."""
from __future__ import annotations

from html import escape
from typing import Any


def h(value: Any) -> str:
    """Escape a value for Telegram HTML bodies."""
    if value is None:
        return ""
    return escape(str(value))


def code(value: Any) -> str:
    return f"<code>{h(value)}</code>"


def bold(value: Any) -> str:
    return f"<b>{h(value)}</b>"
