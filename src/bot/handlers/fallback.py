"""Last-resort handlers so users never get silence from the bot."""
from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from gaming.src.bot.keyboards import main_menu
from gaming.src.bot.utils.flow import how_to_play

logger = logging.getLogger(__name__)
router = Router(name="fallback")


@router.message(Command("help"))
@router.message(Command("howto"))
@router.message(Command("menu"))
async def cmd_help(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(how_to_play(), parse_mode=ParseMode.HTML, reply_markup=main_menu())


@router.message(StateFilter(None), F.text)
async def any_text(message: types.Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer("Unknown command. Tap a button or send /start.", reply_markup=main_menu())
        return
    await message.answer(
        "Use the buttons — easiest way to play:\n\n" + how_to_play(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.callback_query()
async def any_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    try:
        await callback.message.answer("Menu — pick an action:", reply_markup=main_menu())
    except Exception:
        logger.exception("[fallback] callback failed data=%s", callback.data)
