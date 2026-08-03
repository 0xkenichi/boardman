"""
Button-first UX for non-web3 users.

No need to copy challenge IDs. Flows:
  New challenge → tag → amount buttons → game → chain → confirm
  My match → Lock / Side / Submit result (photo + 5-3 caption)
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.supabase_client import get_supabase
from gaming.src.backend.services.chains import chain_has_escrow, get_chain
from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge
from gaming.src.backend.services.clawstation_circle import CircleWalletError, ensure_user_wallet, get_usdc_balance
from gaming.src.backend.services.clawstation_escrow import (
    EscrowError,
    approve_and_create_match,
    approve_and_join_match,
)
from gaming.src.backend.services.play_points import assert_can_start_or_accept, get_active_challenge
from gaming.src.backend.services.safety import (
    MAX_STAKE_USDC,
    assert_money_ops_allowed,
    check_idempotent,
    clear_idempotent,
    is_paused,
    pause_message,
    validate_stake,
)
from gaming.src.bot.keyboards import (
    after_report_menu,
    back_menu,
    chain_menu,
    confirm_challenge_menu,
    game_category_menu,
    game_menu,
    main_menu,
    match_actions_menu,
    side_menu,
    stake_amount_menu,
)
from gaming.src.backend.services.game_catalog import (
    display_name as game_display_name,
    is_imessage,
    is_mobile,
    proof_instructions,
)
from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag
from gaming.src.bot.utils.flow import how_to_play, report_status
from gaming.src.bot.utils.notify import get_balance_snapshot, notify_user
from gaming.src.bot.utils.text import bold, code, h

logger = logging.getLogger(__name__)
router = Router()


class ChallengeWizard(StatesGroup):
    waiting_tag = State()
    waiting_amount = State()
    waiting_game_category = State()
    waiting_game = State()
    waiting_chain = State()
    confirm = State()


class ReportWizard(StatesGroup):
    waiting_photo = State()  # data: challenge_id


def _safe_row(result) -> Optional[dict]:
    if result is None:
        return None
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


async def _load_challenge(cid: str) -> Optional[dict]:
    """Load by UUID (callbacks) or public short code (user input)."""
    from gaming.src.backend.services.match_codes import load_challenge_by_ref, is_uuid

    if not cid:
        return None
    # Prefer resolver (handles short codes + UUID + ensures public_code)
    ch = load_challenge_by_ref(cid)
    if ch:
        return ch
    if not is_uuid(cid):
        return None
    r = (
        get_supabase()
        .schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", cid)
        .limit(1)
        .execute()
    )
    return normalize_challenge(_safe_row(r))


def _short(cid: str) -> str:
    from gaming.src.backend.services.match_codes import display_code

    return display_code(None, challenge_id=cid)


# ── Main menu hooks ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:main")
@router.callback_query(F.data == "m_main")
async def ui_main(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "🏠 <b>Rematch</b>\n\nTap a button — no commands needed.",
        reply_markup=main_menu(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "ui:more")
async def ui_more(callback: types.CallbackQuery) -> None:
    await callback.answer()
    from gaming.src.bot.keyboards import more_menu

    await callback.message.answer(
        "⋯ <b>More</b>",
        reply_markup=more_menu(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "ui:get_usdc")
async def ui_get_usdc(callback: types.CallbackQuery) -> None:
    """Load Arc address → try Circle API drip → else fund helper + web faucet."""
    await callback.answer("Loading…")
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    from gaming.src.backend.services.circle_faucet import (
        CIRCLE_FAUCET_URL,
        fund_helper_url,
        request_arc_usdc,
    )
    from gaming.src.bot.keyboards import get_usdc_menu

    addr = ""
    try:
        from gaming.src.backend.services.clawstation_circle import set_preferred_chain

        await set_preferred_chain(profile["id"], "arc")
        wallet = await ensure_user_wallet(profile["id"], chain_id="arc")
        addr = wallet.get("address") or ""
    except Exception as exc:
        logger.exception("[UI] get_usdc wallet failed")
        await callback.message.answer(
            f"❌ Could not load wallet: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    if not addr:
        await callback.message.answer(
            "❌ No deposit address yet. Tap /start and try again.",
            reply_markup=main_menu(),
        )
        return

    # Best path: Circle API auto-drip (needs account permission; often fails on free keys)
    drip = await request_arc_usdc(addr)
    helper = fund_helper_url(addr)

    if drip.get("ok"):
        await callback.message.answer(
            "💧 <b>USDC requested</b>\n\n"
            f"Address:\n<code>{h(addr)}</code>\n\n"
            f"{h(drip.get('message') or 'Wait ~30s, then open Wallet.')}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_usdc_menu(
                faucet_url=CIRCLE_FAUCET_URL,
                helper_url=helper,
            ),
            disable_web_page_preview=True,
        )
        return

    # Fallback: address shown (tap-to-copy on Telegram) + fund page with address prefilled
    await callback.message.answer(
        "💧 <b>Get money</b>\n\n"
        f"Your address (tap to copy):\n<code>{h(addr)}</code>\n\n"
        "1. Tap <b>Fund page</b> — address ready to copy\n"
        "2. Open faucet → pick <b>Arc Testnet</b> → <b>USDC</b> → paste\n"
        "3. Back here → Wallet → Refresh\n\n"
        "Gas is paid in USDC — you only need USDC.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_usdc_menu(
            faucet_url=CIRCLE_FAUCET_URL,
            helper_url=helper,
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "ui:network")
async def ui_network_menu(callback: types.CallbackQuery) -> None:
    """Arc-only network screen (product is Arc-first for now)."""
    await callback.answer()
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    from gaming.src.backend.services.clawstation_circle import (
        get_usdc_balance,
        set_preferred_chain,
    )
    from gaming.src.bot.keyboards import network_menu

    try:
        await set_preferred_chain(profile["id"], "arc")
        wallet = await ensure_user_wallet(profile["id"], chain_id="arc")
        bal = await get_usdc_balance(profile["id"], chain_id="arc")
        addr = wallet.get("address") or ""
    except Exception as exc:
        await callback.message.answer(
            f"❌ {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    await callback.message.answer(
        "🌐 <b>Network</b>\n\n"
        "Rematch runs on <b>Arc</b>.\n"
        f"Balance: <b>${bal:,.2f} USDC</b>\n\n"
        f"Deposit:\n<code>{h(addr)}</code>\n\n"
        "Need funds? Tap <b>Get money</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=network_menu("arc"),
    )


@router.callback_query(F.data.startswith("ui:network:set:"))
async def ui_network_set(callback: types.CallbackQuery) -> None:
    """Force Arc for now — ignore other chain ids from old menus."""
    await callback.answer()
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    from gaming.src.backend.services.clawstation_circle import (
        get_usdc_balance,
        set_preferred_chain,
    )
    from gaming.src.bot.keyboards import get_usdc_menu

    try:
        await set_preferred_chain(profile["id"], "arc")
        wallet = await ensure_user_wallet(profile["id"], chain_id="arc")
        bal = await get_usdc_balance(profile["id"], chain_id="arc")
        addr = wallet.get("address") or ""
        await callback.message.answer(
            f"✅ You're on <b>Arc</b>\n"
            f"USDC: <b>${bal:,.2f}</b>\n\n"
            f"Deposit:\n<code>{h(addr)}</code>\n\n"
            f"Fund via <b>Get money</b> before locking a stake.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_usdc_menu(),
        )
    except Exception as exc:
        logger.exception("[UI] network set failed")
        await callback.message.answer(
            f"❌ Could not switch: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


@router.callback_query(F.data == "ui:playbook")
async def ui_playbook(callback: types.CallbackQuery) -> None:
    await callback.answer()
    from gaming.src.bot.utils.flow import play_points_short

    await callback.message.answer(
        play_points_short(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.callback_query(F.data == "ui:rules")
async def ui_rules(callback: types.CallbackQuery) -> None:
    await callback.answer()
    from gaming.src.bot.utils.flow import rules_short

    await callback.message.answer(
        rules_short(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "ui:board")
async def ui_public_board(callback: types.CallbackQuery) -> None:
    await callback.answer()
    from gaming.src.backend.services.rematch_public import (
        format_leaderboard_text,
        format_metrics_text,
        get_chain_metrics,
        get_leaderboard,
        get_open_public_challenges,
    )
    from gaming.src.bot.keyboards import REMATCH_BOARD, REMATCH_WEB
    from aiogram.types import InlineKeyboardButton, WebAppInfo
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    try:
        board = get_open_public_challenges(12)
        lb = get_leaderboard(8)
        metrics = get_chain_metrics()
    except Exception as exc:
        logger.exception("[UI] board load failed")
        await callback.message.answer(
            f"❌ Board unavailable: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    lines = ["📋 <b>Public board</b> (open challenges)\n"]
    if not board:
        lines.append("No open public challenges right now.\nCreate one with visibility <b>public</b>.\n")
    else:
        for b in board:
            lines.append(
                f"• <code>{b['code']}</code> · ${b['stake']:.0f} · {b['game']} · "
                f"{b['chain']} · @{b['creator_tag']}"
            )
    lines.append("")
    lines.append(format_leaderboard_text(lb, 8))
    lines.append("")
    lines.append(format_metrics_text(metrics))

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🏆 Open leaderboard", url=REMATCH_BOARD))
    kb.row(InlineKeyboardButton(text="🌐 Rematch site", url=REMATCH_WEB))
    kb.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    await callback.message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("ui:cancel:"))
async def ui_cancel_match(callback: types.CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    cid = callback.data.split(":", 2)[2]
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    from gaming.src.backend.services.rematch_cancel import execute_cancel
    from gaming.src.bot.utils.notify import notify_user

    try:
        result = await execute_cancel(profile["id"], cid)
    except Exception as exc:
        logger.exception("[UI] cancel failed")
        await callback.message.answer(
            f"❌ Cancel failed: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    msg = result.get("message") or "Done."
    await callback.message.answer(
        f"{'✅' if result.get('success') else 'ℹ️'} {h(msg)}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )

    # Notify other party
    ch = await _load_challenge(cid)
    if ch:
        other = (
            ch.get("opponent_id")
            if profile["id"] == ch.get("creator_id")
            else ch.get("creator_id")
        )
        if other and result.get("success"):
            mode = result.get("mode")
            if mode == "propose":
                await notify_user(
                    other,
                    f"🤝 Opponent proposed cancel on match <code>{h(result.get('code'))}</code>.\n"
                    f"Open <b>My match</b> → Confirm cancel (both refunded) or keep playing.",
                )
            elif mode in ("free", "refund", "confirm"):
                await notify_user(
                    other,
                    f"❌ Match <code>{h(result.get('code'))}</code> was cancelled.",
                )


@router.callback_query(F.data == "ui:rematch")
async def ui_rematch_list(callback: types.CallbackQuery, state: FSMContext) -> None:
    """List past rivals for one-tap rematch."""
    await callback.answer()
    await state.clear()
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    from gaming.src.backend.services.play_points import assert_can_start_or_accept
    from gaming.src.backend.services.rematch_public import get_recent_rivals
    from gaming.src.bot.keyboards import rematch_rivals_menu

    blocked = assert_can_start_or_accept(profile["id"])
    if blocked:
        await callback.message.answer(f"❌ {blocked}", parse_mode=None, reply_markup=main_menu())
        return

    rivals = get_recent_rivals(profile["id"], 8)
    if not rivals:
        await callback.message.answer(
            "🔄 <b>Rematch</b>\n\n"
            "No past rivals yet.\n"
            "Play someone once (New challenge), then Rematch skips the setup.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    await callback.message.answer(
        "🔄 <b>Rematch</b>\n"
        "Same stake & game as last time.\n"
        "Tap a rival → they Accept → both Lock.",
        parse_mode=ParseMode.HTML,
        reply_markup=rematch_rivals_menu(rivals),
    )


@router.callback_query(F.data.startswith("ui:rematch:go:"))
async def ui_rematch_go(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Create challenge with last setup vs chosen rival."""
    try:
        await callback.answer("Starting rematch…")
    except Exception:
        pass
    await state.clear()
    user = callback.from_user
    if not user:
        return
    opponent_id = callback.data.split(":")[-1]
    profile = await get_or_create_profile(user)

    from gaming.src.backend.services.rematch_quick import create_quick_rematch
    from gaming.src.bot.keyboards import challenge_confirm_menu

    try:
        result = await create_quick_rematch(profile["id"], opponent_id)
    except Exception as exc:
        logger.exception("[UI] quick rematch failed")
        await callback.message.answer(
            f"❌ {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    code = result["public_code"]
    tag = result.get("opponent_tag") or "player"
    try:
        await notify_user(
            opponent_id,
            f"🔄 <b>Rematch?</b> from @{h(profile.get('gaming_tag') or 'player')}\n\n"
            f"Match: <code>{h(code)}</code>\n"
            f"Stake: <b>${result['stake']:,.2f} USDC</b>\n"
            f"Game: <b>{h(result['game'])}</b>\n"
            f"Network: <b>{h(result['chain'])}</b>\n\n"
            f"Same setup as last time. Accept to run it back:",
            buttons=challenge_confirm_menu(result["challenge_id"]),
        )
    except Exception:
        logger.exception("[UI] rematch notify failed")

    await callback.message.answer(
        f"🔄 <b>Rematch sent</b> to @{h(tag)}\n"
        f"Code: <code>{h(code)}</code>\n"
        f"${result['stake']:,.2f} · {h(result['game'])} · {h(result['chain'])}\n\n"
        f"When they Accept → both <b>Lock</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "ui:match")
async def ui_my_match(callback: types.CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        await state.clear()
        user = callback.from_user
        if not user:
            return
        profile = await get_or_create_profile(user)
        active = get_active_challenge(profile["id"])
        if not active:
            await callback.message.answer(
                "No active match.\n\nTap <b>New challenge</b> to start one.",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu(),
            )
            return
        ch = await _load_challenge(active["id"])
        if not ch:
            await callback.message.answer("Match not found.", reply_markup=main_menu())
            return
        await callback.message.answer(
            f"{report_status(ch)}\n\nUse the buttons below:",
            parse_mode=ParseMode.HTML,
            reply_markup=match_actions_menu(ch, profile["id"]),
        )
    except Exception as exc:
        logger.exception("[UI] My match failed")
        await callback.message.answer(
            f"❌ Could not load match: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


@router.callback_query(F.data.startswith("ui:info:"))
async def ui_info(callback: types.CallbackQuery) -> None:
    await callback.answer()
    cid = callback.data.split(":", 2)[2]
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    ch = await _load_challenge(cid)
    if not ch:
        await callback.message.answer("Match not found.", reply_markup=main_menu())
        return
    await callback.message.answer(
        report_status(ch),
        parse_mode=ParseMode.HTML,
        reply_markup=match_actions_menu(ch, profile["id"]),
    )


# ── Challenge wizard ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "ui:challenge")
@router.callback_query(F.data == "menu:challenge")
async def ui_challenge_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        user = callback.from_user
        if not user:
            return
        if is_paused():
            await callback.message.answer(
                pause_message(), parse_mode=ParseMode.HTML, reply_markup=main_menu()
            )
            return
        profile = await get_or_create_profile(user)
        blocked = assert_can_start_or_accept(profile["id"])
        if blocked:
            await callback.message.answer(
                f"❌ {blocked}", reply_markup=main_menu(), parse_mode=None
            )
            return
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(
                text="👤 Challenge a friend", callback_data="ui:chal:mode:private"
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="📋 Post to public board", callback_data="ui:chal:mode:public"
            )
        )
        kb.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
        await callback.message.answer(
            "⚔️ <b>New challenge</b>\n\n"
            "• <b>Friend</b> — invite one @tag\n"
            "• <b>Public board</b> — first to accept in the bot / website\n\n"
            f"Stake limits: $1 – ${MAX_STAKE_USDC:,.0f} USDC",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.as_markup(),
        )
    except Exception as exc:
        logger.exception("[UI] New challenge failed")
        await callback.message.answer(
            f"❌ Could not start challenge: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


@router.callback_query(F.data == "ui:chal:mode:private")
async def ui_chal_mode_private(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(visibility="private")
    await state.set_state(ChallengeWizard.waiting_tag)
    await callback.message.answer(
        "Send their gaming tag or Telegram @username.\n"
        "Example: <code>@stillkenichi</code>\n\n"
        "They must have opened this bot once (/start).",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.callback_query(F.data == "ui:chal:mode:public")
async def ui_chal_mode_public(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(visibility="public", opponent_id=None, opponent_tag="public")
    await state.set_state(ChallengeWizard.waiting_amount)
    await callback.message.answer(
        "📋 <b>Public challenge</b>\n\nHow much USDC to stake?",
        parse_mode=ParseMode.HTML,
        reply_markup=stake_amount_menu(),
    )


@router.message(ChallengeWizard.waiting_tag)
async def ui_chal_tag(message: types.Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().lstrip("@")
    if not raw or raw.startswith("/"):
        await message.answer("Send a tag like @friend", parse_mode=None)
        return
    opponent = await get_profile_by_tag(raw)
    if not opponent:
        await message.answer(
            f"❌ @{raw} not found. They must open ClawStation bot and tap Start first.",
            parse_mode=None,
        )
        return
    profile = await get_or_create_profile(message.from_user)
    if opponent["id"] == profile["id"]:
        await message.answer("❌ You can't challenge yourself.", parse_mode=None)
        return
    blocked = assert_can_start_or_accept(opponent["id"])
    if blocked:
        await message.answer(f"❌ @{raw} already has an open match.", parse_mode=None)
        return
    await state.update_data(
        opponent_id=opponent["id"],
        opponent_tag=opponent.get("gaming_tag") or raw,
    )
    await state.set_state(ChallengeWizard.waiting_amount)
    await message.answer(
        f"Opponent: <b>@{h(opponent.get('gaming_tag') or raw)}</b>\n\n"
        f"How much USDC to stake?",
        parse_mode=ParseMode.HTML,
        reply_markup=stake_amount_menu(),
    )


@router.callback_query(ChallengeWizard.waiting_amount, F.data.startswith("ui:chal:amt:"))
async def ui_chal_amt(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    amt = int(callback.data.split(":")[-1])
    err = validate_stake(Decimal(amt))
    if err:
        await callback.message.answer(err, reply_markup=stake_amount_menu())
        return
    await state.update_data(amount=amt)
    await state.set_state(ChallengeWizard.waiting_game_category)
    await callback.message.answer(
        f"Stake: <b>${amt}</b>\n\n"
        f"Where do you play?",
        parse_mode=ParseMode.HTML,
        reply_markup=game_category_menu(),
    )


@router.callback_query(ChallengeWizard.waiting_game_category, F.data == "ui:chal:cats")
@router.callback_query(ChallengeWizard.waiting_game, F.data == "ui:chal:cats")
async def ui_chal_cats(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(ChallengeWizard.waiting_game_category)
    data = await state.get_data()
    await callback.message.answer(
        f"Stake: <b>${data.get('amount')}</b>\n\nWhere do you play?",
        parse_mode=ParseMode.HTML,
        reply_markup=game_category_menu(),
    )


@router.callback_query(ChallengeWizard.waiting_game_category, F.data.startswith("ui:chal:cat:"))
async def ui_chal_category(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    cat = callback.data.split(":")[-1]
    await state.update_data(game_category=cat)
    await state.set_state(ChallengeWizard.waiting_game)
    label = {
        "imessage": "iMessage games",
        "console": "Console",
        "mobile": "Mobile (FC Mobile & more)",
    }.get(cat, cat)
    hint = ""
    if cat == "mobile":
        hint = (
            "\n⚽ <b>FC Mobile</b> · 🔥 Free Fire · 🔫 COD · 🗡️ Valorant · 🎯 PUBG\n"
            "<i>1v1 / TDM / private only — not open BR.</i>"
        )
    elif cat == "imessage":
        hint = "\n📱 Play in Messages, send the final screen here."
    await callback.message.answer(
        f"<b>{h(label)}</b>{hint}\n\nPick one:",
        parse_mode=ParseMode.HTML,
        reply_markup=game_menu(category=cat),
    )


@router.callback_query(ChallengeWizard.waiting_game, F.data.startswith("ui:chal:game:"))
async def ui_chal_game(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Pick game → Arc is fixed (no chain picker)."""
    await callback.answer()
    # game_id may contain dots: ui:chal:game:imessage.8_ball
    parts = callback.data.split(":")
    game = ":".join(parts[3:]) if len(parts) > 3 else parts[-1]
    await state.update_data(game=game, chain="arc")
    data = await state.get_data()
    gname = game_display_name(game)
    extra = ""
    if is_imessage(game):
        extra = (
            "\n\n📱 <b>iMessage mode</b>\n"
            "After both lock: play in iMessage, then send the "
            "<b>final screen</b> screenshot to this bot."
        )
    elif is_mobile(game):
        extra = (
            "\n\n📲 <b>Mobile mode</b>\n"
            "After both lock: play on your phone, then send the "
            "<b>final result screen</b> to this bot."
        )
    await state.set_state(ChallengeWizard.confirm)
    await callback.message.answer(
        f"📝 <b>Confirm challenge</b>\n\n"
        f"To: @{h(data.get('opponent_tag'))}\n"
        f"Stake: <b>${data.get('amount')}</b>\n"
        f"Game: <b>{h(gname)}</b>\n"
        f"{extra}\n\n"
        f"Send it?",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_challenge_menu(),
    )


@router.callback_query(ChallengeWizard.waiting_chain, F.data.startswith("ui:chal:chain:"))
async def ui_chal_chain(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Legacy path if a user still has an old wizard state — force Arc."""
    await callback.answer()
    await state.update_data(chain="arc")
    data = await state.get_data()
    await state.set_state(ChallengeWizard.confirm)
    await callback.message.answer(
        f"📝 <b>Confirm challenge</b>\n\n"
        f"To: @{h(data.get('opponent_tag'))}\n"
        f"Stake: <b>${data.get('amount')}</b> USDC\n"
        f"Game: <b>{h(data.get('game'))}</b>\n"
        f"Network: <b>Arc</b>\n\n"
        f"Send it?",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_challenge_menu(),
    )


@router.callback_query(ChallengeWizard.confirm, F.data == "ui:chal:confirm")
async def ui_chal_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    # Instant ack so Telegram stops the loading spinner
    try:
        await callback.answer("Sending…")
    except Exception:
        pass
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    data = await state.get_data()
    amount = Decimal(str(data.get("amount", 1)))
    chain = "arc"  # product surface is Arc-only for now
    game = data.get("game") or "EAFC"
    game_label = game_display_name(game)
    opponent_id = data.get("opponent_id")
    opponent_tag = data.get("opponent_tag") or "player"
    visibility = data.get("visibility") or ("public" if not opponent_id else "private")

    gate = assert_money_ops_allowed(
        profile["id"], action="challenge", amount=amount, kind="stake"
    )
    if gate:
        await state.clear()
        await callback.message.answer(gate, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        return

    blocked = assert_can_start_or_accept(profile["id"])
    if blocked:
        await state.clear()
        await callback.message.answer(f"❌ {blocked}", reply_markup=main_menu())
        return

    await callback.message.answer("⏳ Creating challenge…")

    try:
        bal = await get_usdc_balance(profile["id"], chain_id=chain)
    except Exception as exc:
        await callback.message.answer(f"❌ Balance error: {h(exc)}", parse_mode=ParseMode.HTML)
        return
    if bal < amount:
        from gaming.src.bot.keyboards import get_usdc_menu

        await callback.message.answer(
            f"❌ Not enough USDC. You have <b>${bal:,.2f}</b>.\n"
            f"Tap <b>Get money</b> to fund your wallet, then try again.",
            reply_markup=get_usdc_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    from gaming.src.backend.services.match_codes import display_code

    challenge_id = str(uuid.uuid4())
    public_code = display_code(None, challenge_id=challenge_id)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    # Never insert public_code — column not on live schema (PGRST204)
    record = denormalize_challenge(
        {
            "id": challenge_id,
            "creator_id": profile["id"],
            "opponent_id": opponent_id,
            "amount_usdc": float(amount),
            "game": game,
            "visibility": visibility,
            "status": "open",
            "expires_at": expires.isoformat(),
            "message": "Rematch challenge",
            "settlement_chain": chain,
        }
    )
    try:
        get_supabase().schema("gaming").table("challenges").insert(record).execute()
    except Exception as exc:
        logger.exception("[UI] challenge insert failed")
        record.pop("settlement_chain", None)
        try:
            get_supabase().schema("gaming").table("challenges").insert(record).execute()
        except Exception as exc2:
            await callback.message.answer(f"❌ Could not create: {h(exc2)}", parse_mode=ParseMode.HTML)
            return

    await state.clear()
    from gaming.src.bot.keyboards import challenge_confirm_menu, REMATCH_BOARD

    if opponent_id:
        try:
            imsg = ""
            if is_imessage(game):
                imsg = "\n📱 Play in <b>iMessage</b>, then send final screenshot here."
            elif is_mobile(game):
                imsg = "\n📲 Play on <b>mobile</b>, then send final screenshot here."
            await notify_user(
                opponent_id,
                f"⚔️ <b>Challenge from @{h(profile.get('gaming_tag') or 'player')}</b>\n\n"
                f"Match: <code>{h(public_code)}</code>\n"
                f"Stake: <b>${amount:,.2f}</b>\n"
                f"Game: <b>{h(game_label)}</b>"
                f"{imsg}\n\n"
                f"Tap Accept or Decline:",
                buttons=challenge_confirm_menu(challenge_id),
            )
        except Exception:
            logger.exception("[UI] notify opponent failed")
        imsg_me = (
            f"\n\n{proof_instructions(game)}"
            if is_imessage(game)
            else ""
        )
        await callback.message.answer(
            f"✅ Challenge sent to <b>@{h(opponent_tag)}</b>\n"
            f"Match: <code>{h(public_code)}</code>\n"
            f"Game: <b>{h(game_label)}</b>\n\n"
            f"When they Accept, both of you tap <b>Lock my stake</b>."
            f"{imsg_me}\n\n"
            f"Use <b>My match</b> anytime.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
    else:
        await callback.message.answer(
            f"✅ <b>Public challenge posted</b>\n"
            f"Match: <code>{h(public_code)}</code>\n"
            f"Stake: <b>${amount:,.2f}</b> · {h(game_label)}\n\n"
            f"Anyone can accept from <b>Public board</b> or\n"
            f"{h(REMATCH_BOARD)}\n\n"
            f"You will lock after someone accepts.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )


# ── Lock stake (button) ──────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("ui:lock:"))
async def ui_lock(callback: types.CallbackQuery) -> None:
    try:
        await callback.answer("Locking…")
    except Exception:
        pass
    cid = callback.data.split(":", 2)[2]
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    ch = await _load_challenge(cid)
    if not ch:
        await callback.message.answer("Match not found.", reply_markup=main_menu())
        return

    is_creator = profile["id"] == ch["creator_id"]
    is_opp = profile["id"] == ch.get("opponent_id")
    if not is_creator and not is_opp:
        await callback.message.answer("Not your match.", reply_markup=main_menu())
        return

    amount = Decimal(str(ch["amount_usdc"]))
    chain = ch.get("settlement_chain") or "base"

    gate = assert_money_ops_allowed(
        profile["id"], action="lock", amount=amount, kind="lock"
    )
    if gate:
        await callback.message.answer(gate, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        return

    idem_key = f"lock:{cid}:{profile['id']}"
    dup = check_idempotent(idem_key)
    if dup:
        await callback.message.answer(dup, reply_markup=match_actions_menu(ch, profile["id"]))
        return

    # Preflight: chain-specific Circle wallet + balance (Arc ≠ Base wallet)
    try:
        wallet = await ensure_user_wallet(profile["id"], chain_id=chain)
        bal = await get_usdc_balance(profile["id"], chain_id=chain)
        if bal < amount:
            label = get_chain(chain).get("label", chain)
            from gaming.src.bot.keyboards import get_usdc_menu

            await callback.message.answer(
                f"❌ Not enough USDC for this match.\n"
                f"Need <b>${amount:,.2f}</b>, have <b>${bal:,.2f}</b>.\n\n"
                f"Your address:\n<code>{h(wallet.get('address') or '')}</code>\n\n"
                f"Tap <b>Get money</b>, then lock again.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_usdc_menu(),
            )
            clear_idempotent(idem_key)
            return
    except Exception as exc:
        logger.exception("[UI] lock preflight failed")
        await callback.message.answer(
            f"❌ Wallet not ready: {h(exc)}\n"
            f"Open <b>Get money</b> / Wallet and try again.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        clear_idempotent(idem_key)
        return

    await callback.message.answer(
        f"⏳ Locking <b>${amount:,.2f}</b> USDC…",
        parse_mode=ParseMode.HTML,
    )

    try:
        await ensure_user_wallet(profile["id"], chain_id=chain)
        if is_creator:
            if ch.get("status") == "open" and ch.get("opponent_id"):
                get_supabase().schema("gaming").table("challenges").update(
                    {"status": "accepted"}
                ).eq("id", cid).execute()
            await approve_and_create_match(profile["id"], cid, amount)
            msg = f"✅ Stake locked (you).\nWaiting for opponent."
        else:
            if ch.get("status") != "creator_locked":
                clear_idempotent(idem_key)
                await callback.message.answer(
                    "⏳ Wait for the other player to lock first.",
                    reply_markup=match_actions_menu(ch, profile["id"]),
                )
                return
            await approve_and_join_match(profile["id"], cid, amount)
            msg = f"✅ Both stakes locked!"
    except (EscrowError, CircleWalletError) as exc:
        clear_idempotent(idem_key)
        await callback.message.answer(
            f"❌ Lock failed: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=match_actions_menu(ch, profile["id"]),
        )
        return
    except Exception as exc:
        clear_idempotent(idem_key)
        logger.exception("[UI] lock failed")
        await callback.message.answer(f"❌ {h(exc)}", parse_mode=ParseMode.HTML)
        return

    ch2 = await _load_challenge(cid) or ch
    game_key = ch2.get("game") or ch.get("game") or ""
    play_help = proof_instructions(str(game_key))
    if is_imessage(str(game_key)):
        next_steps = (
            f"{play_help}\n\n"
            f"Then: <b>Submit result</b> → photo of the final screen.\n"
            f"Caption <code>W</code> / <code>L</code> or the score."
        )
    elif is_mobile(str(game_key)):
        next_steps = (
            f"{play_help}\n\n"
            f"Then: <b>Submit result</b> → photo of the final screen.\n"
            f"Caption score like <code>2-1</code> (or <code>W</code>/<code>L</code>)."
        )
    else:
        next_steps = (
            f"1. Tap <b>I am HOME</b> or <b>I am AWAY</b>\n"
            f"2. Play\n"
            f"3. <b>Submit result</b> → FT photo captioned <code>5-3</code>"
        )
    await callback.message.answer(
        f"{msg}\n\n{report_status(ch2)}\n\n{next_steps}",
        parse_mode=ParseMode.HTML,
        reply_markup=match_actions_menu(ch2, profile["id"]),
    )

    if is_opp:
        try:
            await notify_user(
                ch["creator_id"],
                f"🎮 Both stakes locked!\n\n{next_steps}",
                buttons=match_actions_menu(ch2, ch["creator_id"]),
            )
        except Exception:
            pass


# ── Side selection ───────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("ui:side:"))
async def ui_side(callback: types.CallbackQuery) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    # ui:side:{id}:home|away|menu
    if len(parts) < 4:
        return
    cid, side = parts[2], parts[3]
    user = callback.from_user
    if not user:
        return
    if side == "menu":
        await callback.message.answer(
            "Pick your side for this match:",
            reply_markup=side_menu(cid),
        )
        return
    if side not in ("home", "away"):
        return

    profile = await get_or_create_profile(user)
    ch = await _load_challenge(cid)
    if not ch:
        await callback.message.answer("Match not found.", reply_markup=main_menu())
        return
    is_creator = profile["id"] == ch["creator_id"]
    is_opp = profile["id"] == ch.get("opponent_id")
    if not is_creator and not is_opp:
        await callback.message.answer("Not your match.")
        return

    other = "away" if side == "home" else "home"
    update: dict = {}
    if is_creator:
        if ch.get("opponent_side") == side:
            await callback.message.answer(
                f"❌ Opponent already took {side}. Pick {other}.",
                reply_markup=side_menu(cid),
            )
            return
        update["creator_side"] = side
        if not ch.get("opponent_side"):
            update["opponent_side"] = other
    else:
        if ch.get("creator_side") == side:
            await callback.message.answer(
                f"❌ Creator already took {side}. Pick {other}.",
                reply_markup=side_menu(cid),
            )
            return
        update["opponent_side"] = side
        if not ch.get("creator_side"):
            update["creator_side"] = other

    get_supabase().schema("gaming").table("challenges").update(
        denormalize_challenge(update)
    ).eq("id", cid).execute()
    ch2 = await _load_challenge(cid) or ch
    await callback.message.answer(
        f"✅ You are <b>{side.upper()}</b>.\n\n"
        f"Play your match, then tap <b>Submit result</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=match_actions_menu(ch2, profile["id"]),
    )


# ── Submit result (photo only, no ID typing) ─────────────────────────────────


@router.callback_query(F.data.startswith("ui:report:"))
async def ui_report_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    cid = callback.data.split(":", 2)[2]
    await state.set_state(ReportWizard.waiting_photo)
    await state.update_data(challenge_id=cid)
    await callback.message.answer(
        "📸 <b>Submit result</b>\n\n"
        "1. Send the <b>full-time screenshot</b> as a photo or file\n"
        "2. Caption it with the score <b>home-away</b>, for example:\n"
        "   <code>5-3</code>\n"
        "   or <code>H-A 5-3</code>\n\n"
        "That's it — no match ID needed.\n"
        "Send the image now.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.message(ReportWizard.waiting_photo, F.photo | F.document)
async def ui_report_photo(message: types.Message, state: FSMContext, bot) -> None:
    """Receive photo while in report wizard — caption is just 5-3."""
    data = await state.get_data()
    cid = data.get("challenge_id")
    if not cid:
        await state.clear()
        await message.answer("Session expired. Tap My match again.", reply_markup=main_menu())
        return

    caption = (message.caption or "").strip()
    # Parse 5-3 or H-A 5-3 or home-away 5-3
    score_token = None
    m = re.search(r"(\d+)\s*[-:]\s*(\d+)", caption)
    if m:
        score_token = f"{m.group(1)}-{m.group(2)}"
    if not score_token:
        await message.answer(
            "Add a caption like <code>5-3</code> (home goals - away goals) on the photo.\n"
            "Or resend the photo with that caption.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Reuse submit_score pipeline with synthetic caption
    from gaming.src.bot.handlers.submit_score import (
        _extract_image_file_id,
        _process_screenshot_message,
    )

    file_id = _extract_image_file_id(message)
    if not file_id:
        await message.answer("Send a photo or image file, please.")
        return

    synthetic = f"/submit_score {cid} {score_token}"
    await state.clear()
    await _process_screenshot_message(
        message, bot, synthetic, file_id_override=file_id
    )
    # After processing, show match buttons
    user = message.from_user
    if user:
        profile = await get_or_create_profile(user)
        ch = await _load_challenge(cid)
        if ch:
            bal = await get_balance_snapshot(profile["id"])
            await message.answer(
                f"<b>Your balances</b>\n{bal}",
                parse_mode=ParseMode.HTML,
                reply_markup=match_actions_menu(ch, profile["id"]),
            )


@router.callback_query(F.data.startswith("ui:settle:"))
async def ui_settle(callback: types.CallbackQuery) -> None:
    await callback.answer("Checking…")
    cid = callback.data.split(":", 2)[2]
    try:
        from gaming.src.backend.services.clawstation_settlement import settle_challenge

        result = await settle_challenge(cid)
    except Exception as exc:
        await callback.message.answer(f"Settle check: {h(exc)}", parse_mode=ParseMode.HTML)
        return
    ch = await _load_challenge(cid)
    user = callback.from_user
    profile = await get_or_create_profile(user) if user else None
    text = f"Result: <b>{h(result.get('action'))}</b>"
    if result.get("reason"):
        text += f"\n{h(result.get('reason'))}"
    if ch and profile:
        text += f"\n\n{report_status(ch)}"
        await callback.message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=match_actions_menu(ch, profile["id"]),
        )
    else:
        await callback.message.answer(text, parse_mode=ParseMode.HTML)


# ── Enhance accept to show match buttons ─────────────────────────────────────
# (challenge.py already accepts; we patch notify to include ui after accept via
#  wrapping is heavy — instead after accept in challenge.py we could import menu.
#  For simplicity, message on My match is enough.)
