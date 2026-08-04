"""Admin-only pause / status commands (free — no paid dashboard)."""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command

from gaming.src.backend.services.safety import (
    is_admin,
    is_paused,
    pause_message,
    safety_status_text,
    set_paused,
)
from gaming.src.bot.keyboards import main_menu

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("safety"))
async def cmd_safety(message: types.Message) -> None:
    """Anyone can see public safety limits; admins see pause state."""
    await message.answer(safety_status_text(), parse_mode=ParseMode.HTML, reply_markup=main_menu())


@router.message(Command("pause"))
async def cmd_pause(message: types.Message) -> None:
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer("Admin only. Set CLAW_ADMIN_TELEGRAM_IDS in .env")
        return
    set_paused(True, reason=f"telegram:{user.id}")
    await message.answer(
        "⏸ <b>PAUSED</b>\nChallenges, locks, and withdrawals are frozen.",
        parse_mode=ParseMode.HTML,
    )
    logger.warning("[Admin] pause by %s", user.id)


@router.message(Command("unpause"))
async def cmd_unpause(message: types.Message) -> None:
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer("Admin only.")
        return
    set_paused(False, reason=f"telegram:{user.id}")
    await message.answer(
        "▶️ <b>UNPAUSED</b>\nMoney movement is open again.",
        parse_mode=ParseMode.HTML,
    )
    logger.warning("[Admin] unpause by %s", user.id)


@router.message(Command("paused"))
async def cmd_paused(message: types.Message) -> None:
    if is_paused():
        await message.answer(pause_message(), parse_mode=ParseMode.HTML)
    else:
        await message.answer("▶️ ClawStation is running normally.", parse_mode=ParseMode.HTML)


@router.message(Command("link_community"))
async def cmd_link_community(message: types.Message) -> None:
    """Run this *inside* the Rematch public group to save its chat id.

    Bot must be a member (prefer admin with post rights). After linking,
    new public challenges are announced in this group.
    """
    user = message.from_user
    chat = message.chat
    if not user:
        return

    # Allow admin, or any member when run in a group (first link sets target)
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        await message.answer(
            "Run this command <b>inside</b> your Rematch community group "
            "(not in a private DM with the bot).\n\n"
            "1. Add @ClawStationOfficialBot to the group\n"
            "2. Give it permission to post messages\n"
            "3. Send <code>/link_community</code> in that group",
            parse_mode=ParseMode.HTML,
        )
        return

    if not is_admin(user.id):
        # Non-admins: only group admins of this chat
        try:
            member = await message.bot.get_chat_member(chat.id, user.id)
            status = getattr(member, "status", None)
            if status not in ("creator", "administrator"):
                await message.answer("Group admin or Rematch admin only.")
                return
        except Exception:
            await message.answer("Could not verify group admin status.")
            return

    from gaming.src.bot.utils.community import rematch_group_chat_ref, save_linked_chat_id

    path = save_linked_chat_id(chat.id, title=chat.title or "")
    # Also write env-style hint into reply
    ref = rematch_group_chat_ref()
    await message.answer(
        f"✅ <b>Community group linked</b>\n\n"
        f"Title: <b>{chat.title or '—'}</b>\n"
        f"Chat id: <code>{chat.id}</code>\n"
        f"Saved: <code>{path}</code>\n"
        f"Active target: <code>{ref}</code>\n\n"
        f"Public challenges will post here.\n"
        f"Optional .env: <code>REMATCH_TELEGRAM_GROUP_CHAT_ID={chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )
    logger.warning("[Admin] link_community chat_id=%s by %s title=%s", chat.id, user.id, chat.title)

    # Smoke-test post
    try:
        await message.bot.send_message(
            chat.id,
            "📣 Rematch community linked — public open challenges will appear here.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        await message.answer(
            f"⚠️ Linked, but bot cannot post yet: <code>{exc}</code>\n"
            f"Make the bot an admin (or allow messages) in this group.",
            parse_mode=ParseMode.HTML,
        )
