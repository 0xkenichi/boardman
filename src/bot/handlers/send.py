"""Withdraw / send USDC to another ClawStation user or external address."""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from html import escape

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.supabase_client import get_supabase
from gaming.src.backend.services.chains import get_chain
from gaming.src.backend.services.clawstation_circle import (
    _circle_for_chain,
    ensure_user_wallet,
    get_preferred_chain,
    get_usdc_balance,
)
from gaming.src.backend.services.safety import (
    MAX_WITHDRAW_USDC,
    assert_money_ops_allowed,
    commit_daily_withdraw,
    is_paused,
    pause_message,
)
from gaming.src.bot.keyboards import back_menu, send_menu, wallet_menu
from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag
from gaming.src.bot.utils.security import has_tx_password, verify_tx_password

logger = logging.getLogger(__name__)

router = Router()

_MIN_SEND = Decimal("1")
_MAX_SEND = Decimal("10000")
_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class SendState(StatesGroup):
    waiting_for_tag_amount = State()
    waiting_for_address_amount = State()
    confirm_password = State()


def _is_address(value: str) -> bool:
    return bool(_ADDRESS_RE.match(value))


async def _execute_transfer(
    sender_id: str,
    sender_wallet_id: str,
    recipient_address: str,
    amount: Decimal,
    recipient_id: str | None,
    chain_id: str,
) -> dict:
    circle = _circle_for_chain(chain_id)
    result = circle.transfer_usdc(sender_wallet_id, recipient_address, float(amount))

    sb = get_supabase()
    audit = {
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "recipient_address": recipient_address.lower(),
        "amount_usdc": float(amount),
        "circle_transaction_id": result.get("transaction_id") if result.get("success") else None,
        "tx_hash": result.get("tx_hash"),
        "status": "pending" if result.get("success") else "failed",
    }
    try:
        audit["settlement_chain"] = chain_id
    except Exception:
        pass
    try:
        sb.schema("gaming").table("wallet_debit_audit").insert(audit).execute()
    except Exception as exc:
        # Retry without optional chain column if schema is older
        logger.warning("[Withdraw] audit insert failed, retry bare: %s", exc)
        bare = {k: v for k, v in audit.items() if k != "settlement_chain"}
        try:
            sb.schema("gaming").table("wallet_debit_audit").insert(bare).execute()
        except Exception:
            logger.exception("[Withdraw] audit insert failed")
    return result


async def start_withdraw(message: types.Message, state: FSMContext) -> None:
    """Shared entry: /send, Wallet → Withdraw, or menu:withdraw."""
    await state.clear()
    user = message.from_user
    if user is None:
        return
    if is_paused():
        await message.answer(
            pause_message(), parse_mode=ParseMode.HTML, reply_markup=wallet_menu()
        )
        return
    profile = await get_or_create_profile(user)

    if not has_tx_password(profile):
        await message.answer(
            "🔐 You need a <b>transaction password</b> before withdrawing.\n\n"
            "Set one with /set_tx_password (min 8 characters).\n"
            "You'll use it every time you send funds out.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu(),
        )
        return

    pref = "arc"
    bal = Decimal("0")
    try:
        pref = await get_preferred_chain(profile["id"])
        bal = await get_usdc_balance(profile["id"], chain_id=pref)
    except Exception:
        logger.exception("[Withdraw] balance check failed")

    label = get_chain(pref).get("label", pref)
    try:
        from gaming.src.backend.services.kobox_partner import (
            kobox_name,
            withdraw_intro_extra_html,
        )

        partner_blurb = withdraw_intro_extra_html()
        name = kobox_name()
    except Exception:
        partner_blurb = ""
        name = "your bank app"

    await message.answer(
        "💸 <b>Withdraw USDC</b>\n\n"
        f"Active network: <b>{escape(label)}</b>\n"
        f"Available: <b>${bal:,.2f}</b> USDC\n"
        f"Max per transfer: <b>${MAX_WITHDRAW_USDC:,.0f}</b>\n"
        f"{partner_blurb}\n"
        f"<b>How</b>\n"
        f"1. Open {escape(name)} (or any wallet) and copy its <b>USDC deposit address</b>\n"
        f"2. Tap <b>To 0x</b> here and send from Rematch\n"
        f"3. In {escape(name)}: swap USDC → Naira → withdraw to your bank\n\n"
        "Or send to another Rematch player with @tag.\n\n"
        "Where should we send?",
        parse_mode=ParseMode.HTML,
        reply_markup=send_menu(),
        disable_web_page_preview=True,
    )


@router.message(Command("send"))
@router.message(Command("withdraw"))
async def cmd_send(message: types.Message, state: FSMContext) -> None:
    """Entry point for withdrawing / sending USDC."""
    await start_withdraw(message, state)


@router.callback_query(F.data.in_({"ui:withdraw", "menu:withdraw", "m_send"}))
async def cb_withdraw(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    # Use callback.message with from_user of the person who tapped
    msg = callback.message
    if msg is None:
        return
    # Patch from_user so profile lookup uses the tapper, not the bot
    class _MsgProxy:
        def __init__(self, m, u):
            self._m = m
            self.from_user = u

        def __getattr__(self, name):
            return getattr(self._m, name)

        async def answer(self, *a, **k):
            return await self._m.answer(*a, **k)

    await start_withdraw(_MsgProxy(msg, callback.from_user), state)  # type: ignore[arg-type]


@router.callback_query(F.data == "ui:withdraw:kobox")
async def cb_withdraw_kobox(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Explain partner cash-out when no URL is set (or user tapped the info button)."""
    await callback.answer()
    from gaming.src.backend.services.kobox_partner import (
        kobox_name,
        kobox_referral_url,
        offramp_copy_html,
    )

    name = kobox_name()
    url = kobox_referral_url()
    link_line = f"\nOpen {escape(name)}: {escape(url)}\n" if url else ""
    await callback.message.answer(
        f"{offramp_copy_html()}\n"
        f"{link_line}\n"
        f"<b>In Rematch</b>\n"
        f"1. In {escape(name)}, copy your <b>USDC deposit / receive address</b>\n"
        f"2. Tap <b>To 0x (Kobox or any wallet)</b>\n"
        f"3. Paste address + amount → confirm\n"
        f"4. In {escape(name)}: swap → withdraw Naira to your bank\n\n"
        f"Same steps work with any wallet/exchange you already use.",
        parse_mode=ParseMode.HTML,
        reply_markup=send_menu(),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "send_to_tag")
async def cb_send_to_tag(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SendState.waiting_for_tag_amount)
    await callback.message.answer(
        "💸 <b>Withdraw to a ClawStation player</b>\n\n"
        "Reply with: <code>@tag amount</code>\n"
        "Example: <code>@alice 25</code>\n\n"
        "They must have opened this bot once.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.callback_query(F.data == "send_to_address")
async def cb_send_to_address(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SendState.waiting_for_address_amount)
    await callback.message.answer(
        "💸 <b>Withdraw to an external wallet</b>\n\n"
        "Reply with: <code>0xAddress amount</code>\n"
        "Example: <code>0x1234…abcd 25</code>\n\n"
        "⚠️ Withdraw on <b>Arc</b> only (same network as Rematch).",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.message(SendState.waiting_for_tag_amount, F.text)
async def send_tag_input(message: types.Message, state: FSMContext) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer(
            "❌ Usage: <code>@tag amount</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    tag = parts[0].lstrip("@")
    try:
        amount = Decimal(parts[1])
    except Exception:
        await message.answer("❌ Invalid amount.")
        return

    recipient = await get_profile_by_tag(tag)
    if not recipient:
        await message.answer(f"❌ Player @{escape(tag)} not found.")
        await state.clear()
        return

    address = recipient.get("gaming_deposit_address") or recipient.get("wallet_address")
    if not address or not _is_address(address):
        await message.answer(f"❌ @{escape(tag)} does not have a valid wallet address.")
        await state.clear()
        return

    await state.update_data(
        recipient_id=recipient["id"],
        recipient_address=address,
        amount=str(amount),
        tag=tag,
    )
    await _ask_password(message, state)


@router.message(SendState.waiting_for_address_amount, F.text)
async def send_address_input(message: types.Message, state: FSMContext) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer(
            "❌ Usage: <code>0xAddress amount</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    address, amount_str = parts
    if not _is_address(address):
        await message.answer("❌ Invalid Ethereum address.")
        return
    try:
        amount = Decimal(amount_str)
    except Exception:
        await message.answer("❌ Invalid amount.")
        return

    await state.update_data(
        recipient_id=None,
        recipient_address=address,
        amount=str(amount),
        tag=None,
    )
    await _ask_password(message, state)


async def _ask_password(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = Decimal(data["amount"])
    profile = await get_or_create_profile(message.from_user)
    pref = await get_preferred_chain(profile["id"])
    label = get_chain(pref).get("label", pref)
    dest = (
        f"@{escape(data['tag'])}"
        if data.get("tag")
        else f"<code>{escape(data['recipient_address'])}</code>"
    )
    await state.set_state(SendState.confirm_password)
    await message.answer(
        f"🔐 <b>Confirm withdrawal</b>\n\n"
        f"Amount: <b>${amount:,.2f} USDC</b>\n"
        f"Network: <b>{escape(label)}</b>\n"
        f"To: {dest}\n\n"
        "Enter your transaction password to proceed.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )


@router.message(SendState.confirm_password, F.text)
async def send_confirm_password(message: types.Message, state: FSMContext) -> None:
    password = message.text or ""
    profile = await get_or_create_profile(message.from_user)

    if not verify_tx_password(password, profile.get("gaming_tx_password_hash", "")):
        await message.answer("❌ Incorrect transaction password. Try again, or /start to cancel.")
        return

    data = await state.get_data()
    amount = Decimal(data["amount"])

    gate = assert_money_ops_allowed(
        profile["id"], action="withdraw", amount=amount, kind="withdraw"
    )
    if gate:
        await message.answer(gate, parse_mode=ParseMode.HTML, reply_markup=wallet_menu())
        await state.clear()
        return

    if amount < _MIN_SEND or amount > _MAX_SEND:
        await message.answer(f"❌ Amount must be between ${_MIN_SEND} and ${_MAX_SEND}.")
        await state.clear()
        return

    try:
        pref = await get_preferred_chain(profile["id"])
        balance = await get_usdc_balance(profile["id"], chain_id=pref)
        wallet = await ensure_user_wallet(profile["id"], chain_id=pref)
    except Exception as exc:
        await message.answer(f"❌ Could not check wallet: {escape(str(exc))}", parse_mode=ParseMode.HTML)
        await state.clear()
        return

    if balance < amount:
        label = get_chain(pref).get("label", pref)
        await message.answer(
            f"❌ Insufficient balance on <b>{escape(label)}</b>.\n"
            f"You have <b>${balance:,.2f}</b> but want to send <b>${amount:,.2f}</b>.\n\n"
            "Switch network if funds are on another chain.",
            parse_mode=ParseMode.HTML,
            reply_markup=wallet_menu(),
        )
        await state.clear()
        return

    sender_wallet_id = wallet.get("wallet_id")
    if not sender_wallet_id:
        await message.answer("❌ Your wallet is not set up. Use /start first.")
        await state.clear()
        return

    if data.get("recipient_id") == profile["id"]:
        await message.answer("❌ You cannot withdraw to yourself.")
        await state.clear()
        return

    await message.answer("⏳ Submitting withdrawal…")
    result = await _execute_transfer(
        sender_id=profile["id"],
        sender_wallet_id=sender_wallet_id,
        recipient_address=data["recipient_address"],
        amount=amount,
        recipient_id=data.get("recipient_id"),
        chain_id=pref,
    )

    await state.clear()
    label = get_chain(pref).get("label", pref)

    if result.get("success"):
        commit_daily_withdraw(profile["id"], amount)
        tx_hash = result.get("tx_hash")
        if data.get("tag"):
            dest = f"@{escape(data['tag'])}"
        else:
            dest = f"<code>{escape(data['recipient_address'])}</code>"

        # Refresh balance after send for confirmation message
        try:
            new_bal = await get_usdc_balance(profile["id"], chain_id=pref)
        except Exception:
            new_bal = balance - amount

        from gaming.src.backend.services.wallet_activity import (
            format_withdraw_message,
            set_snapshot,
        )

        # Align watcher snapshot so the next poll doesn't double-DM this outflow
        try:
            set_snapshot(profile["id"], pref, new_bal)
        except Exception:
            pass

        confirm = format_withdraw_message(
            amount,
            new_bal,
            pref,
            destination=dest,
            tx_hash=str(tx_hash) if tx_hash else None,
            status="submitted",
        )
        tx_id = result.get("transaction_id")
        if tx_id:
            confirm += f"\nTransaction ID: <code>{escape(str(tx_id))}</code>"

        await message.answer(
            confirm,
            parse_mode=ParseMode.HTML,
            reply_markup=wallet_menu(),
        )
        logger.info(
            "[Withdraw] user=%s amount=%s chain=%s status=%s",
            profile["id"][:8],
            amount,
            pref,
            result.get("status"),
        )
    else:
        await message.answer(
            f"❌ Withdrawal failed: {escape(str(result.get('error')))}",
            parse_mode=ParseMode.HTML,
            reply_markup=wallet_menu(),
        )
