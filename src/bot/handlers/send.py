"""Send USDC to another ClawStation user or external address."""
from __future__ import annotations

import logging
import re
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.circle_wallet_service import CircleWalletService
from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_circle import get_usdc_balance
from gaming.src.bot.keyboards import back_menu, send_menu
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
) -> dict:
    circle = CircleWalletService()
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
    sb.schema("gaming").table("wallet_debit_audit").insert(audit).execute()
    return result


@router.message(Command("send"))
async def cmd_send(message: types.Message, state: FSMContext) -> None:
    """Entry point for sending USDC."""
    await state.clear()
    profile = await get_or_create_profile(message.from_user)

    if not has_tx_password(profile):
        await message.answer(
            "🔐 You need a transaction password to send tokens.\n"
            "Set one with /set_tx_password",
            reply_markup=back_menu(),
        )
        return

    await message.answer(
        "💸 *Send USDC*\n\n"
        "Choose how to send:",
        reply_markup=send_menu(),
    )


@router.callback_query(F.data == "m_send")
async def cb_send(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await cmd_send(callback.message, state)


@router.callback_query(F.data == "send_to_tag")
async def cb_send_to_tag(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SendState.waiting_for_tag_amount)
    await callback.message.edit_text(
        "💸 Send to a ClawStation tag.\n\n"
        "Reply with: `@tag <amount>`\n"
        "Example: `@alice 25`",
        reply_markup=back_menu(),
    )


@router.callback_query(F.data == "send_to_address")
async def cb_send_to_address(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SendState.waiting_for_address_amount)
    await callback.message.edit_text(
        "💸 Send to an external address.\n\n"
        "Reply with: `<0x_address> <amount>`\n"
        "Example: `0x1234...abcd 25`",
        reply_markup=back_menu(),
    )


@router.message(SendState.waiting_for_tag_amount, F.text)
async def send_tag_input(message: types.Message, state: FSMContext) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("❌ Usage: `@tag <amount>`")
        return
    tag = parts[0].lstrip("@")
    try:
        amount = Decimal(parts[1])
    except Exception:
        await message.answer("❌ Invalid amount.")
        return

    recipient = await get_profile_by_tag(tag)
    if not recipient:
        await message.answer(f"❌ Player `@{tag}` not found.")
        await state.clear()
        return

    address = recipient.get("gaming_deposit_address") or recipient.get("wallet_address")
    if not address or not _is_address(address):
        await message.answer(f"❌ `@{tag}` does not have a valid wallet address.")
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
        await message.answer("❌ Usage: `<0x_address> <amount>`")
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
    await state.set_state(SendState.confirm_password)
    await message.answer(
        f"🔐 Confirm sending *${amount:,.2f} USDC*.\n\n"
        "Enter your transaction password to proceed."
    )


@router.message(SendState.confirm_password, F.text)
async def send_confirm_password(message: types.Message, state: FSMContext) -> None:
    password = message.text or ""
    profile = await get_or_create_profile(message.from_user)

    if not verify_tx_password(password, profile.get("gaming_tx_password_hash", "")):
        await message.answer("❌ Incorrect transaction password.")
        return

    data = await state.get_data()
    amount = Decimal(data["amount"])

    if amount < _MIN_SEND or amount > _MAX_SEND:
        await message.answer(f"❌ Amount must be between ${_MIN_SEND} and ${_MAX_SEND}.")
        await state.clear()
        return

    try:
        balance = await get_usdc_balance(profile["id"])
    except Exception as exc:
        await message.answer(f"❌ Could not check balance: {exc}")
        await state.clear()
        return

    if balance < amount:
        await message.answer(
            f"❌ Insufficient balance. You have *${balance:,.2f}* but want to send *${amount:,.2f}*."
        )
        await state.clear()
        return

    sender_wallet_id = profile.get("circle_wallet_id") or profile.get("gaming_circle_wallet_id")
    if not sender_wallet_id:
        await message.answer("❌ Your wallet is not set up. Use /start first.")
        await state.clear()
        return

    if data.get("recipient_id") == profile["id"]:
        await message.answer("❌ You cannot send to yourself.")
        await state.clear()
        return

    result = await _execute_transfer(
        sender_id=profile["id"],
        sender_wallet_id=sender_wallet_id,
        recipient_address=data["recipient_address"],
        amount=amount,
        recipient_id=data.get("recipient_id"),
    )

    await state.clear()

    if result.get("success"):
        tx_hash = result.get("tx_hash")
        tx_hash_line = f"\nTx: `{tx_hash}`" if tx_hash else ""
        recipient_line = f"to `@{data.get('tag')}`" if data.get("tag") else f"to `{data['recipient_address']}`"
        await message.answer(
            f"✅ *Transfer submitted* {recipient_line}\n"
            f"Amount: *${amount:,.2f} USDC*\n"
            f"Transaction ID: `{result.get('transaction_id')}`{tx_hash_line}\n\n"
            f"Status: `{result.get('status', 'PENDING')}`"
        )
    else:
        await message.answer(f"❌ Transfer failed: {result.get('error')}")