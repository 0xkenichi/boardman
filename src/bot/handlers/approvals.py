"""
Telegram approval handling for web-initiated spectator spends.

- Inline callbacks: approve:yes:<id> / approve:no:<id> / approve:always:<id>
- /approvals command + callbacks to toggle per-action always-approve mode.
"""
from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from gaming.src.backend.services.tx_approval import (
    get_approval_mode,
    resolve_approval,
    set_approval_mode,
)
from gaming.src.bot.keyboards import approval_settings_menu, main_menu
from gaming.src.bot.utils.db import get_or_create_profile

logger = logging.getLogger(__name__)
router = Router()

_ACTION_LABEL = {
    "spectator_bet": "arena bets",
    "lp_deposit": "LP deposits",
}


def _callback_data_parts(callback: types.CallbackQuery) -> list[str]:
    return (callback.data or "").split(":")


@router.callback_query(F.data.startswith("approve:yes:"))
@router.callback_query(F.data.startswith("approve:no:"))
@router.callback_query(F.data.startswith("approve:always:"))
async def cb_approval(callback: types.CallbackQuery) -> None:
    parts = _callback_data_parts(callback)
    if len(parts) < 3:
        await callback.answer("Invalid approval", show_alert=True)
        return
    decision = parts[1]  # yes | no | always
    approval_id = parts[2]
    always = decision == "always"
    action = "yes" if decision != "no" else "no"

    res = resolve_approval(approval_id, action, always=always)
    if not res.get("ok"):
        reason = res.get("reason") or "unknown"
        await callback.answer(
            "This request is no longer pending." if reason == "already_decided"
            else "Request not found.",
            show_alert=True,
        )
        try:
            await callback.message.edit_text(
                "🕐 This request was already answered.",
                reply_markup=None,
            )
        except Exception:
            pass
        return

    status = res["status"]
    label = _ACTION_LABEL.get(res.get("action") or "", "transaction")
    if status == "approved":
        if always:
            text = (
                "✅ <b>Approved — and bets/LP are now auto-approved.</b>\n\n"
                f"Future {label} will spend from your wallet without asking. "
                f"Change this anytime with /approvals."
            )
        else:
            text = "✅ <b>Approved.</b>\n\nThis spend is confirmed. Change the default anytime with /approvals."
    else:
        text = "❌ <b>Declined.</b>\n\nNothing was spent. Change the default anytime with /approvals."

    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    try:
        await callback.answer("Done")
    except Exception:
        pass


@router.message(Command("approvals"))
async def cmd_approvals(message: types.Message) -> None:
    user = message.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    pid = profile["id"]
    bet_mode = get_approval_mode(pid, "spectator_bet")
    lp_mode = get_approval_mode(pid, "lp_deposit")
    await message.answer(
        "🔐 <b>Approvals</b>\n\n"
        "When you bet or provide liquidity on the website, the bot asks you to "
        "approve the spend in Telegram. Toggle each action below:\n\n"
        f"• <b>Bets:</b> {'Always approve' if bet_mode == 'always' else 'Ask each time'}\n"
        f"• <b>LP deposits:</b> {'Always approve' if lp_mode == 'always' else 'Ask each time'}",
        parse_mode=ParseMode.HTML,
        reply_markup=approval_settings_menu(bet_mode, lp_mode),
    )


@router.callback_query(F.data.startswith("approve:mode:"))
async def cb_approval_mode(callback: types.CallbackQuery) -> None:
    parts = _callback_data_parts(callback)
    # approve:mode:<action>:<ask|always>
    if len(parts) < 4:
        await callback.answer("Invalid", show_alert=True)
        return
    action, mode = parts[2], parts[3]
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    set_approval_mode(profile["id"], action, mode)
    bet_mode = get_approval_mode(profile["id"], "spectator_bet")
    lp_mode = get_approval_mode(profile["id"], "lp_deposit")
    try:
        await callback.message.edit_text(
            "🔐 <b>Approvals</b>\n\n"
            "When you bet or provide liquidity on the website, the bot asks you to "
            "approve the spend in Telegram. Toggle each action below:\n\n"
            f"• <b>Bets:</b> {'Always approve' if bet_mode == 'always' else 'Ask each time'}\n"
            f"• <b>LP deposits:</b> {'Always approve' if lp_mode == 'always' else 'Ask each time'}",
            parse_mode=ParseMode.HTML,
            reply_markup=approval_settings_menu(bet_mode, lp_mode),
        )
    except Exception:
        pass
    await callback.answer("Saved")
