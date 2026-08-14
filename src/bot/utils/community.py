"""Post public challenges to the Rematch Telegram community group."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Union

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

# Persist /link_community so laptop restarts keep the group without re-editing .env
_LINK_FILE = Path(
    os.getenv("REMATCH_COMMUNITY_LINK_FILE")
    or os.path.expanduser("~/.rematch/community_chat.json")
)


def _bot_username() -> str:
    try:
        from gaming.src.bot.telegram_env import telegram_bot_username

        return telegram_bot_username()
    except Exception:
        return (
            os.getenv("TELEGRAM_BOT_USERNAME_MYBOARDMAN")
            or os.getenv("TELEGRAM_BOT_USERNAME_BOARDMAN")
            or os.getenv("TELEGRAM_BOT_USERNAME_CLAWSTATION")
            or os.getenv("NEXT_PUBLIC_TELEGRAM_BOT_USERNAME")
            or os.getenv("TELEGRAM_BOT_USERNAME")
            or "myboardmanOfficialBot"
        ).lstrip("@")


def _load_linked_chat_id() -> Optional[Union[int, str]]:
    try:
        if not _LINK_FILE.is_file():
            return None
        data = json.loads(_LINK_FILE.read_text(encoding="utf-8"))
        cid = data.get("chat_id")
        if cid is None or cid == "":
            return None
        try:
            return int(cid)
        except (TypeError, ValueError):
            return str(cid)
    except Exception:
        logger.warning("[Community] failed to read link file %s", _LINK_FILE, exc_info=True)
        return None


def save_linked_chat_id(chat_id: Union[int, str], title: str = "") -> Path:
    """Persist group chat id from /link_community."""
    _LINK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"chat_id": chat_id, "title": title or ""}
    _LINK_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return _LINK_FILE


def rematch_group_chat_ref() -> Optional[Union[int, str]]:
    """Telegram chat id or @username for community posts.

    Order:
      1. REMATCH_TELEGRAM_GROUP_CHAT_ID / TELEGRAM_GROUP_CHAT_ID
      2. ~/.rematch/community_chat.json from /link_community
      3. Public @username parsed from group URL (not invite + links)
    """
    raw = (
        os.getenv("REMATCH_TELEGRAM_GROUP_CHAT_ID")
        or os.getenv("TELEGRAM_GROUP_CHAT_ID")
        or os.getenv("MONITOR_CHANNEL_ID")
        or ""
    ).strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            return raw if raw.startswith("@") else f"@{raw.lstrip('@')}"

    linked = _load_linked_chat_id()
    if linked is not None:
        return linked

    # t.me/SomePublicGroup → @SomePublicGroup (invite + hashes cannot be resolved)
    url = (
        os.getenv("REMATCH_TELEGRAM_GROUP_URL")
        or os.getenv("TELEGRAM_GROUP_URL")
        or os.getenv("NEXT_PUBLIC_TELEGRAM_GROUP_URL")
        or ""
    ).strip()
    if not url:
        return None
    m = re.search(r"(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,})", url)
    if m:
        name = m.group(1)
        if name.lower() in (
            "joinchat",
            "share",
            "addstickers",
            "clawstationofficialbot",
            "myboardmanofficialbot",
        ):
            return None
        return f"@{name}"
    return None


def room_label_for_game(game: str) -> str:
    """Map game id → live-room line for the group post."""
    g = (game or "").lower()
    if g.startswith("imessage") or "gamepigeon" in g or "8_ball" in g:
        return "📱 iMessage room"
    if g.startswith("mobile") or g in ("free_fire", "cod_mobile", "pubg"):
        return "📲 Mobile room"
    try:
        from gaming.src.backend.services.game_catalog import is_imessage, is_mobile

        if is_imessage(game):
            return "📱 iMessage room"
        if is_mobile(game):
            return "📲 Mobile room"
    except Exception:
        pass
    if g.startswith("pc") or g in ("valorant", "cs2", "lol"):
        return "💻 PC room"
    return "🎮 Console room"


def public_group_challenge_menu(challenge_id: str, public_code: str) -> InlineKeyboardMarkup:
    """Accept in-group + open bot deep link (works even if privacy mode hides text)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Accept challenge",
            callback_data=f"challenge:accept:{challenge_id}",
        )
    )
    deep = f"https://t.me/{_bot_username()}?start=m_{public_code}"
    builder.row(InlineKeyboardButton(text="🤖 Open bot", url=deep))
    try:
        from gaming.src.bot.brand_assets import boardman_leaderboard_url

        board = boardman_leaderboard_url()
    except Exception:
        board = "https://boardman.playingsidequest.fun/leaderboard"
    builder.row(InlineKeyboardButton(text="🏅 Leaderboard", url=board))
    return builder.as_markup()


def format_public_challenge_post(
    *,
    public_code: str,
    creator_tag: str,
    amount: Any,
    game_label: str,
    game: str = "",
) -> str:
    room = room_label_for_game(game or game_label)
    try:
        amt = f"${float(amount):,.2f}"
    except Exception:
        amt = f"${amount}"
    tag = (creator_tag or "player").lstrip("@")
    return (
        f"📣 <b>Open public challenge</b>\n"
        f"{room}\n\n"
        f"From: <code>@{tag}</code>\n"
        f"Match: <code>{public_code}</code>\n"
        f"Stake: <b>{amt}</b> · {game_label}\n\n"
        f"Tap <b>Accept</b> to take it — then both lock stakes in the bot."
    )


async def post_public_challenge(
    *,
    challenge_id: str,
    public_code: str,
    creator_tag: str,
    amount: Any,
    game_label: str,
    game: str = "",
) -> bool:
    """Send public challenge to the community group. Returns True if sent."""
    chat = rematch_group_chat_ref()
    if chat is None:
        logger.warning(
            "[Community] No group chat configured — public challenge %s only on board. "
            "Set REMATCH_TELEGRAM_GROUP_CHAT_ID or run /link_community in the group.",
            public_code,
        )
        return False

    from gaming.src.bot.utils.notify import _ensure_bot

    bot = _ensure_bot()
    if bot is None:
        logger.error("[Community] No bot instance to post public challenge")
        return False

    text = format_public_challenge_post(
        public_code=public_code,
        creator_tag=creator_tag,
        amount=amount,
        game_label=game_label,
        game=game,
    )
    buttons = public_group_challenge_menu(challenge_id, public_code)
    try:
        await bot.send_message(
            chat_id=chat,
            text=text,
            reply_markup=buttons,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("[Community] Posted public challenge %s to %s", public_code, chat)
        return True
    except Exception as exc:
        logger.exception(
            "[Community] Failed to post challenge %s to %s: %s", public_code, chat, exc
        )
        return False
