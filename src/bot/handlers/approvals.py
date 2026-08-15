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
    get_approval_row,
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


async def _lock_after_yes(approval_id: str) -> dict:
    try:
        from gaming.src.backend.services.tx_approval import apply_approved_spend

        return await apply_approved_spend(approval_id)
    except Exception:
        logger.exception("[approvals] apply after Yes failed id=%s", approval_id)
        return {"success": False, "pending": False, "error": "apply_failed"}


def _locked_text(applied: dict, *, always: bool) -> str:
    extra = ""
    if always:
        extra = (
            "\n\nFuture spends of this type will go through without asking. "
            "Change that anytime with /approvals."
        )
    if applied.get("success") and not applied.get("pending"):
        amt = applied.get("amount")
        kind = applied.get("kind") or applied.get("action") or ""
        if kind == "lp" or applied.get("agent_id"):
            who = applied.get("agent_name") or applied.get("agent_id") or "the agent"
            return (
                f"✅ <b>Locked ${float(amt or 0):,.2f} LP into {who}.</b>\n\n"
                f"The website ticket updates now.{extra}"
            )
        side = str(applied.get("side") or "")
        who = "Raja" if side == "a" else "Nero" if side == "b" else "the book"
        return (
            f"✅ <b>Locked ${float(amt or 0):,.2f} on {who}.</b>\n\n"
            f"The website ticket updates now.{extra}"
        )
    if applied.get("pending"):
        return "✅ <b>Approved.</b>\n\nLocking the funds now — the website will catch up."
    err = applied.get("message") or applied.get("error") or "could not lock"
    return (
        f"✅ <b>Approved in Telegram</b> but the lock did not finish: {err}\n\n"
        "Stay on the website — it will retry."
    )


def _callback_data_parts(callback: types.CallbackQuery) -> list[str]:
    return (callback.data or "").split(":")


def _telegram_owns_approval(tg_user_id: int, approval_id: str) -> bool:
    """Only the profile owner may tap Yes/No/Always on an approval prompt.

    Telegram inline buttons survive message forwarding, and callback data
    carries the approval id — without this check an attacker who obtains
    someone else's approval prompt could approve and spend their wallet.
    """
    try:
        from backend.supabase_client import get_supabase

        row = get_approval_row(approval_id) or {}
        pid = str(row.get("profile_id") or "")
        if not pid:
            return False
        r = (
            get_supabase()
            .table("profiles")
            .select("telegram_id, gaming_telegram_chat_id")
            .eq("id", pid)
            .limit(1)
            .execute()
        )
        rec = (r.data or [None])[0] or {}
        allowed: set[int] = set()
        for v in (rec.get("telegram_id"), rec.get("gaming_telegram_chat_id")):
            if v in (None, ""):
                continue
            try:
                allowed.add(int(v))
            except (TypeError, ValueError):
                continue
        return tg_user_id in allowed
    except Exception:
        logger.warning("[approvals] identity check failed id=%s", approval_id, exc_info=True)
        return False


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

    user = callback.from_user
    if not user or not _telegram_owns_approval(user.id, approval_id):
        await callback.answer(
            "This approval is for a different Telegram account.",
            show_alert=True,
        )
        return

    res = resolve_approval(approval_id, action, always=always)
    if not res.get("ok"):
        reason = res.get("reason") or "unknown"
        # Already Yes — still try to lock so the website sees applied.
        if reason == "already_decided" and res.get("status") in {"approved", "applied"}:
            applied = await _lock_after_yes(approval_id)
            if applied.get("success") and not applied.get("pending"):
                await callback.answer("Already locked")
                try:
                    await callback.message.edit_text(
                        _locked_text(applied, always=False),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                return
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
    if status == "approved":
        await callback.answer("Approved — locking now")
        applied = await _lock_after_yes(approval_id)
        text = _locked_text(applied, always=always)
    else:
        text = "❌ <b>Declined.</b>\n\nNothing was spent. Change the default anytime with /approvals."
        try:
            await callback.answer("Declined")
        except Exception:
            pass

    try:
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
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
