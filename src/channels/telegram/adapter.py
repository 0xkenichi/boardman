"""aiogram router that hands flagged entry points to the shared core.

Included first in ``src/bot/main.py``. Every handler here is filtered by
``CHANNELS_CORE_FLOWS`` at call time, so with the flag empty no filter
matches and every update falls through to the legacy handlers exactly as
before. Rollback is a config change.

Taken over per flow:
  balance   /balance, menu:wallet
  deposit   /deposit, ui:get_money
  withdraw  /withdraw, /send, ui:withdraw, menu:withdraw, m_send
  link      /link [code], /start link_<code>
  naira     /naira and the "Top up with naira (Paycrest)" button, only while the
            Paycrest rail is live (PAYCREST_ENABLED + REAL_MONEY_ENABLED)
plus core buttons (``v1|…``) and text while a core conversation is active
(only when no legacy wizard holds the chat).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart, Filter
from aiogram.fsm.context import FSMContext

from gaming.src.channels import config
from gaming.src.channels.core import state as conv_state
from gaming.src.channels.core.events import Inbound
from gaming.src.channels.core.principal import Principal

logger = logging.getLogger(__name__)

router = Router(name="channels_core")


class CoreFlow(Filter):
    def __init__(self, flow: str) -> None:
        self.flow = flow

    async def __call__(self, event: Any) -> bool:
        return config.flow_enabled("telegram", self.flow)


class ActiveCoreConversation(Filter):
    """Text belongs to the core only mid-flow, and never over a legacy wizard."""

    async def __call__(self, message: types.Message, state: Optional[FSMContext] = None) -> bool:
        if message.from_user is None:
            return False
        if not config.enabled_flows("telegram") and not config.naira_enabled():
            return False
        if state is not None and await state.get_state() is not None:
            return False
        return await asyncio.to_thread(conv_state.has_active_flow, "telegram", str(message.from_user.id))


async def principal_for(user: types.User, chat_id: Any) -> Principal:
    """Profile via the legacy lookup (which also dual-writes the identity)."""
    from gaming.src.bot.utils.db import get_or_create_profile
    from gaming.src.channels.core.identity.service import resolve

    profile = await get_or_create_profile(user)
    p = await asyncio.to_thread(resolve, "telegram", str(user.id), address=str(chat_id))
    if p.profile_id != profile.get("id"):
        # identity row missing or stale: the legacy profile is the truth for now
        p.profile_id = profile.get("id")
        p.profile = profile
        p.display_name = profile.get("gaming_tag") or ""
    return p


async def run(message: types.Message, user: types.User, ev: Inbound, fsm: Optional[FSMContext]) -> None:
    from gaming.src.channels.core.engine import default_engine
    from gaming.src.channels.telegram import render as tg

    if fsm is not None:
        await fsm.clear()  # leaving any legacy wizard
    principal = await principal_for(user, message.chat.id)
    outs = await default_engine().handle(ev, principal)
    for msg in tg.render_dicts(outs):
        tg.validate(msg)
        await message.answer(
            msg["text"],
            parse_mode=ParseMode.HTML,
            reply_markup=tg.to_aiogram(msg),
            disable_web_page_preview=True,
        )


def _ev(user: types.User, chat_id: Any, *, text: str = "", button: str = "") -> Inbound:
    return Inbound(
        channel="telegram",
        external_id=str(user.id),
        kind="button" if button else "text",
        text=text,
        button_id=button,
        address=str(chat_id),
        profile_name=user.username or "",
    )


async def _cmd(message: types.Message, state: FSMContext, text: str) -> None:
    if message.from_user is None:
        return
    await run(message, message.from_user, _ev(message.from_user, message.chat.id, text=text), state)


async def _cb(callback: types.CallbackQuery, state: FSMContext, *, text: str = "", button: str = "") -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if callback.message is None:
        return
    ev = _ev(callback.from_user, callback.message.chat.id, text=text, button=button)
    await run(callback.message, callback.from_user, ev, state)


# ── entry points, per flow ──────────────────────────────────────────────────


@router.message(Command("balance"), CoreFlow("balance"))
async def core_balance(message: types.Message, state: FSMContext) -> None:
    await _cmd(message, state, "balance")


@router.callback_query(F.data == "menu:wallet", CoreFlow("balance"))
async def core_balance_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _cb(callback, state, text="balance")


@router.message(Command("deposit"), CoreFlow("deposit"))
async def core_deposit(message: types.Message, state: FSMContext) -> None:
    await _cmd(message, state, "deposit")


@router.callback_query(F.data == "ui:get_money", CoreFlow("deposit"))
async def core_deposit_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _cb(callback, state, text="deposit")


@router.message(Command("naira"), CoreFlow("naira"))
async def core_naira(message: types.Message, state: FSMContext) -> None:
    await _cmd(message, state, "naira")


@router.message(Command("withdraw", "send"), CoreFlow("withdraw"))
async def core_withdraw(message: types.Message, state: FSMContext) -> None:
    await _cmd(message, state, "withdraw")


@router.callback_query(F.data.in_({"ui:withdraw", "menu:withdraw", "m_send"}), CoreFlow("withdraw"))
async def core_withdraw_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _cb(callback, state, text="withdraw")


@router.message(CommandStart(deep_link=True), F.text.regexp(r"^/start link_[A-Za-z0-9]+$"), CoreFlow("link"))
async def core_link_deeplink(message: types.Message, command: CommandObject, state: FSMContext) -> None:
    code = (command.args or "").removeprefix("link_")
    await _cmd(message, state, f"link {code}")


@router.message(Command("link"), CoreFlow("link"))
async def core_link(message: types.Message, command: CommandObject, state: FSMContext) -> None:
    await _cmd(message, state, f"link {command.args or ''}".strip())


@router.callback_query(F.data.startswith("v1|"))
async def core_button(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _cb(callback, state, button=callback.data or "")


@router.message(F.text, ~F.text.startswith("/"), ActiveCoreConversation())
async def core_text(message: types.Message, state: FSMContext) -> None:
    await _cmd(message, state, message.text or "")
