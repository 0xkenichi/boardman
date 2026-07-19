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
    game_menu,
    main_menu,
    match_actions_menu,
    side_menu,
    stake_amount_menu,
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
    return (cid or "")[:8]


# ── Main menu hooks ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "menu:main")
@router.callback_query(F.data == "m_main")
async def ui_main(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "🏠 <b>ClawStation</b>\n\nTap a button — you don't need to type commands.",
        reply_markup=main_menu(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "ui:network")
async def ui_network_menu(callback: types.CallbackQuery) -> None:
    """Show network switcher + balances."""
    await callback.answer()
    user = callback.from_user
    if not user:
        return
    profile = await get_or_create_profile(user)
    from gaming.src.backend.services.clawstation_circle import (
        get_all_chain_balances,
        get_preferred_chain,
    )
    from gaming.src.bot.keyboards import network_menu

    pref = await get_preferred_chain(profile["id"])
    lines = []
    try:
        for r in await get_all_chain_balances(profile["id"]):
            mark = " ✓" if r["id"] == pref else ""
            gas = "USDC gas" if r.get("gas_mode") == "usdc_native" else f"{r.get('gas_token')} gas"
            lines.append(
                f"• <b>{h(r['label'])}</b>: ${r['balance_usdc']:,.2f} ({gas}){mark}"
            )
    except Exception:
        lines = ["(could not load balances)"]

    await callback.message.answer(
        "🌐 <b>Switch network</b>\n\n"
        "Same wallet address on all chains — balances are separate.\n"
        "<b>Arc Testnet</b> is best if you don't have test ETH "
        "(gas is paid in USDC).\n\n"
        + "\n".join(lines)
        + "\n\nYour active network is used for new challenges and wallet view.\n"
        "Pick a network:",
        parse_mode=ParseMode.HTML,
        reply_markup=network_menu(pref),
    )


@router.callback_query(F.data.startswith("ui:network:set:"))
async def ui_network_set(callback: types.CallbackQuery) -> None:
    await callback.answer()
    chain = callback.data.split(":")[-1]
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
        cid = await set_preferred_chain(profile["id"], chain)
        # Ensure wallet exists for this chain (Circle may create ARC wallet id)
        await ensure_user_wallet(profile["id"], chain_id=cid)
        bal = await get_usdc_balance(profile["id"], chain_id=cid)
        label = get_chain(cid).get("label", cid)
        gas = get_chain(cid).get("gas_token", "?")
        note = (
            "Gas is paid in USDC — no test ETH needed."
            if get_chain(cid).get("gas_mode") == "usdc_native"
            else f"You may need a little {gas} for gas (platform can top up when possible)."
        )
        await callback.message.answer(
            f"✅ Active network: <b>{h(label)}</b>\n"
            f"USDC on this network: <b>${bal:,.2f}</b>\n\n"
            f"{note}\n\n"
            f"New challenges will use this network by default.\n"
            f"Send USDC to your deposit address on <b>{h(label)}</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
    except Exception as exc:
        logger.exception("[UI] network set failed")
        await callback.message.answer(
            f"❌ Could not switch: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=network_menu(chain),
        )


@router.callback_query(F.data == "ui:playbook")
async def ui_playbook(callback: types.CallbackQuery) -> None:
    await callback.answer()
    from gaming.src.bot.handlers.profile import cmd_playbook

    # Reuse text via fake message is messy — inline short version
    text = (
        "🎮 <b>$PLAY playbook</b>\n\n"
        "• Win <b>+100</b> × streak · Loss <b>+40</b> · Draw <b>+50</b>\n"
        "• No-show (ghost) <b>−50</b>\n"
        "• Tier = Bronze→Diamond from total $PLAY\n"
        "• One match at a time\n\n"
        "Full: /playbook"
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=back_menu())


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
        await state.set_state(ChallengeWizard.waiting_tag)
        await callback.message.answer(
            "⚔️ <b>New challenge</b>\n\n"
            "Send their gaming tag or Telegram @username.\n"
            "Example: <code>@stillkenichi</code>\n\n"
            f"Stake limits: $1 – ${MAX_STAKE_USDC:,.0f} USDC\n"
            "They must have opened this bot once (/start).",
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu(),
        )
    except Exception as exc:
        logger.exception("[UI] New challenge failed")
        await callback.message.answer(
            f"❌ Could not start challenge: {h(exc)}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
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
    await state.set_state(ChallengeWizard.waiting_game)
    await callback.message.answer(
        f"Stake: <b>${amt}</b>\n\nWhich game?",
        parse_mode=ParseMode.HTML,
        reply_markup=game_menu(),
    )


@router.callback_query(ChallengeWizard.waiting_game, F.data.startswith("ui:chal:game:"))
async def ui_chal_game(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    game = callback.data.split(":")[-1]
    await state.update_data(game=game)
    # Prefer user's active network; still allow pick
    from gaming.src.backend.services.clawstation_circle import get_preferred_chain

    user = callback.from_user
    pref = "arc"
    if user:
        try:
            pref = await get_preferred_chain((await get_or_create_profile(user))["id"])
        except Exception:
            pref = "arc"
    await state.set_state(ChallengeWizard.waiting_chain)
    await callback.message.answer(
        f"Game: <b>{h(game)}</b>\n\n"
        f"Which network?\n"
        f"<b>Arc</b> = USDC gas (recommended if no test ETH).\n"
        f"Your active network is <b>{h(pref)}</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=chain_menu(),
    )


@router.callback_query(ChallengeWizard.waiting_chain, F.data.startswith("ui:chal:chain:"))
async def ui_chal_chain(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    chain = callback.data.split(":")[-1]
    if not chain_has_escrow(chain):
        await callback.message.answer(
            f"❌ {chain} not ready yet. Pick Base.",
            reply_markup=chain_menu(),
            parse_mode=None,
        )
        return
    await state.update_data(chain=chain)
    data = await state.get_data()
    await state.set_state(ChallengeWizard.confirm)
    label = get_chain(chain).get("label", chain)
    await callback.message.answer(
        f"📝 <b>Confirm challenge</b>\n\n"
        f"To: @{h(data.get('opponent_tag'))}\n"
        f"Stake: <b>${data.get('amount')}</b> USDC\n"
        f"Game: <b>{h(data.get('game'))}</b>\n"
        f"Network: <b>{h(label)}</b>\n\n"
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
    chain = data.get("chain") or "base"
    game = data.get("game") or "EAFC"
    opponent_id = data.get("opponent_id")
    opponent_tag = data.get("opponent_tag") or "player"

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
        await callback.message.answer(
            f"❌ Not enough USDC on <b>{h(chain)}</b>. You have ${bal:,.2f} there.\n"
            f"Fund your deposit address on that network (Switch network → see address).\n"
            f"Arc uses USDC for gas — no ETH needed.",
            reply_markup=main_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    challenge_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    record = denormalize_challenge(
        {
            "id": challenge_id,
            "creator_id": profile["id"],
            "opponent_id": opponent_id,
            "amount_usdc": float(amount),
            "game": game,
            "visibility": "private",
            "status": "open",
            "expires_at": expires.isoformat(),
            "message": "ClawStation challenge",
            "settlement_chain": chain,
        }
    )
    try:
        get_supabase().schema("gaming").table("challenges").insert(record).execute()
    except Exception as exc:
        logger.exception("[UI] challenge insert failed")
        # retry without settlement_chain
        record.pop("settlement_chain", None)
        try:
            get_supabase().schema("gaming").table("challenges").insert(record).execute()
        except Exception as exc2:
            await callback.message.answer(f"❌ Could not create: {h(exc2)}", parse_mode=ParseMode.HTML)
            return

    await state.clear()
    from gaming.src.bot.keyboards import challenge_confirm_menu

    try:
        await notify_user(
            opponent_id,
            f"⚔️ <b>Challenge from @{h(profile.get('gaming_tag') or 'player')}</b>\n\n"
            f"Stake: <b>${amount:,.2f} USDC</b>\n"
            f"Game: <b>{h(game)}</b>\n"
            f"Network: <b>{h(chain)}</b>\n\n"
            f"Tap Accept or Decline:",
            buttons=challenge_confirm_menu(challenge_id),
        )
    except Exception:
        logger.exception("[UI] notify opponent failed")

    await callback.message.answer(
        f"✅ Challenge sent to <b>@{h(opponent_tag)}</b>\n\n"
        f"When they Accept, both of you tap <b>Lock my stake</b>.\n"
        f"Use <b>My match</b> anytime.",
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

    await callback.message.answer(
        f"⏳ Locking <b>${amount:,.2f}</b> on {h(chain)}… (30–90s)",
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
    await callback.message.answer(
        f"{msg}\n\n{report_status(ch2)}",
        parse_mode=ParseMode.HTML,
        reply_markup=match_actions_menu(ch2, profile["id"]),
    )

    if is_opp:
        # Notify creator with buttons
        try:
            await notify_user(
                ch["creator_id"],
                f"🎮 Both stakes locked!\n\n"
                f"1. Tap <b>I am HOME</b> or <b>I am AWAY</b>\n"
                f"2. Play\n"
                f"3. Tap <b>Submit result</b> and send FT photo captioned <code>5-3</code>",
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
