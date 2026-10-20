"""Keep money and account actions out of group chats.

The bot sits in the public community group (``/link_community``), so anyone
can type ``/withdraw``, ``/link``, ``/deposit`` or ``/reset_tx_password`` there.
Every handler answers in the chat it was called from, so without this guard a
one-time withdraw or PIN-reset link, a link code, a deposit address or a
balance would be posted where every member can read and use it, and ``/start``
in a group used to make the group the player's private notification chat.

Outer middleware (runs before any router's filters):

* private chats: untouched;
* groups / supergroups / channels: only the commands and buttons in the
  allowlists below run. Any other command gets one short "open me in a
  private chat" reply; other text, photos and files are ignored (group
  chatter is not for the bot); any other button tap gets an alert.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

# Read-only or operator commands that are safe to answer in front of a group.
GROUP_COMMANDS = frozenset({
    "link_community", "safety", "paused", "pause", "unpause",
    "board", "leaderboard", "stats", "tlist", "tournaments", "tstatus",
    "help", "howto", "rules", "chains",
})
# Buttons that live on group posts (public challenge cards, cup cards).
GROUP_CALLBACK_PREFIXES = ("challenge:accept:", "t:status:")

DM_ONLY_TEXT = "🔒 Open me in a private chat for that: {link}"
DM_ONLY_ALERT = "Open the Boardman bot in a private chat for that."


def is_private(chat: Any) -> bool:
    kind = getattr(chat, "type", "") or ""
    return str(getattr(kind, "value", kind)) == "private"


def _command(text: str) -> str:
    """'/withdraw@BoardmanBot 5' -> 'withdraw' ('' when not a command)."""
    if not text.startswith("/"):
        return ""
    head = text[1:].split(maxsplit=1)[0] if len(text) > 1 else ""
    return head.split("@", 1)[0].lower()


def _bot_link() -> str:
    try:
        from gaming.src.bot.telegram_env import telegram_bot_username

        name = telegram_bot_username()
    except Exception:
        name = ""
    return f"https://t.me/{name}" if name else "the Boardman bot"


class PrivateChatGuard(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            if is_private(event.chat):
                return await handler(event, data)
            cmd = _command(event.text or event.caption or "")
            if cmd and cmd in GROUP_COMMANDS:
                return await handler(event, data)
            if cmd:
                logger.info("[guard] refused /%s in non-private chat", cmd)
                try:
                    await event.answer(DM_ONLY_TEXT.format(link=_bot_link()), parse_mode=None,
                                       disable_web_page_preview=True)
                except Exception:
                    pass
            return None
        if isinstance(event, CallbackQuery):
            msg = event.message
            chat = getattr(msg, "chat", None)
            # Inline-mode buttons (no message) and private chats pass through.
            if chat is None or is_private(chat):
                return await handler(event, data)
            if (event.data or "").startswith(GROUP_CALLBACK_PREFIXES):
                return await handler(event, data)
            logger.info("[guard] refused button in non-private chat")
            try:
                await event.answer(DM_ONLY_ALERT, show_alert=True)
            except Exception:
                pass
            return None
        return await handler(event, data)
