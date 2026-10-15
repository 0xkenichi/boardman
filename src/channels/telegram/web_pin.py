"""Telegram's legacy withdraw path, minus the typed password.

With ``TELEGRAM_WITHDRAW_WEB_PIN`` on (the default), the legacy ``/withdraw``
wizard still collects the destination and amount, but instead of asking for
the transaction password in the chat it sends the same one-time web link as
the core flow. ``/set_tx_password`` and ``/reset_tx_password`` move to the web
the same way. Turning the flag off restores the old typed-password steps.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from html import escape
from typing import Optional

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from gaming.src.channels.core import withdraw_links
from gaming.src.channels.core.actions import withdraw as wd
from gaming.src.channels.core.principal import Principal

logger = logging.getLogger(__name__)


def _keyboard(label: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, url=url)],
        [InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main")],
    ])


def _principal(user: types.User, profile: dict) -> Principal:
    from gaming.src.channels.core.identity.service import resolve

    try:
        p = resolve("telegram", str(user.id))
    except Exception:
        p = Principal("telegram", str(user.id))
    if p.profile_id != profile.get("id"):
        p.profile_id, p.profile = profile.get("id"), profile
    return p


async def send_withdraw_link(message: types.Message, user: types.User, profile: dict, *,
                             address: str, amount: Decimal, recipient_id: Optional[str],
                             tag: Optional[str]) -> bool:
    """Issue the link and answer; False (after explaining) if refused."""
    principal = await asyncio.to_thread(_principal, user, profile)
    dest = wd.Destination(address, recipient_id, tag)
    try:
        issued = await asyncio.to_thread(wd.request_link, principal, dest, amount)
    except wd.WithdrawRefused as exc:
        await message.answer(f"❌ {escape(str(exc))}", parse_mode=ParseMode.HTML)
        return False
    minutes = withdraw_links.ttl_ms() // 60000
    shown = f"@{escape(tag)}" if tag else f"<code>{escape(address)}</code>"
    await message.answer(
        "🔐 <b>Confirm your withdrawal</b>\n\n"
        f"Amount: <b>${amount:,.2f} USDC</b>\n"
        f"To: {shown}\n\n"
        "Open the secure page and enter your withdrawal PIN there "
        "(you'll set one the first time; an existing transaction password works too).\n"
        f"The link works once and expires in {minutes} minutes. "
        "Never type your PIN in a chat and never share this link.",
        parse_mode=ParseMode.HTML,
        reply_markup=_keyboard("Confirm withdrawal", issued.url),
        disable_web_page_preview=True,
    )
    return True


async def send_pin_reset_link(message: types.Message, user: types.User, profile: dict) -> None:
    try:
        issued = await asyncio.to_thread(
            withdraw_links.issue_pin_reset, profile["id"], channel="telegram", external_id=str(user.id)
        )
    except withdraw_links.LinkRefused as exc:
        await message.answer(f"❌ {escape(exc.message)}", parse_mode=ParseMode.HTML)
        return
    minutes = withdraw_links.ttl_ms() // 60000
    await message.answer(
        "🔐 <b>Set a new withdrawal PIN</b>\n\n"
        "Open the secure page to choose a new PIN. "
        f"The link works once and expires in {minutes} minutes. Never share it.",
        parse_mode=ParseMode.HTML,
        reply_markup=_keyboard("Set my PIN", issued.url),
        disable_web_page_preview=True,
    )


PIN_ON_WEB_TEXT = (
    "🔐 Your withdrawal PIN is set on a secure web page, never typed in this chat.\n\n"
    "Start a withdrawal with /withdraw: the first time, the page asks you to choose a PIN. "
    "Forgot it? Use /reset_tx_password for a one-time reset link."
)
