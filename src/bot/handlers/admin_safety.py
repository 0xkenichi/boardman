"""Admin-only pause / status commands (free — no paid dashboard)."""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.enums import ParseMode
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
