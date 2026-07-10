"""Transaction password setup and reset for ClawStation."""
from __future__ import annotations

import logging
import random

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.security import hash_tx_password

logger = logging.getLogger(__name__)

router = Router()


class TxPasswordState(StatesGroup):
    """States for setting a new transaction password."""
    enter_password = State()
    confirm_password = State()


class TxPasswordResetState(StatesGroup):
    """States for resetting a transaction password."""
    request_code = State()
    enter_code = State()
    set_new_password = State()
    confirm_new_password = State()


@router.message(Command("set_tx_password"))
async def cmd_set_tx_password(message: types.Message, state: FSMContext) -> None:
    """Start the transaction password setup flow."""
    await state.clear()
    await state.set_state(TxPasswordState.enter_password)
    await message.answer(
        "🔐 *Set Transaction Password*\n\n"
        "Please enter a transaction password (minimum 8 characters).\n"
        "You will need this password to confirm withdrawals and transfers."
    )


@router.message(TxPasswordState.enter_password, F.text)
async def tx_password_enter(message: types.Message, state: FSMContext) -> None:
    """Store the first password entry and ask for confirmation."""
    password = message.text or ""
    if len(password) < 8:
        await message.answer("❌ Password must be at least 8 characters. Please try again.")
        return

    await state.update_data(tx_password=password)
    await state.set_state(TxPasswordState.confirm_password)
    await message.answer("🔐 Please re-enter the same password to confirm.")


@router.message(TxPasswordState.confirm_password, F.text)
async def tx_password_confirm(message: types.Message, state: FSMContext) -> None:
    """Confirm the password and save the hash."""
    data = await state.get_data()
    first = data.get("tx_password", "")
    second = message.text or ""

    if first != second:
        await state.clear()
        await message.answer("❌ Passwords do not match. Start again with /set_tx_password")
        return

    profile = await get_or_create_profile(message.from_user)
    hashed = hash_tx_password(second)

    try:
        from backend.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("profiles").update({"gaming_tx_password_hash": hashed}).eq("id", profile["id"]).execute()
    except Exception:
        logger.exception("[TxPassword] Failed to save password hash for %s", profile["id"])
        await message.answer("❌ Could not save password. Please try again later.")
        await state.clear()
        return

    await state.clear()
    await message.answer("✅ Transaction password set successfully.")


@router.message(Command("reset_tx_password"))
async def cmd_reset_tx_password(message: types.Message, state: FSMContext) -> None:
    """Start the transaction password reset flow by generating a 6-digit code."""
    await state.clear()

    user = message.from_user
    if user is None:
        return

    profile = await get_or_create_profile(user)

    # Generate 6-digit numeric code
    code = f"{random.randint(100000, 999999)}"

    # Store code in FSM
    await state.update_data(reset_code=code, reset_profile_id=profile["id"])
    await state.set_state(TxPasswordResetState.enter_code)

    # Send code via Telegram DM
    await message.answer(
        f"🔐 *Transaction Password Reset*\n\n"
        f"Your verification code: `{code}`\n\n"
        f"Please enter the code above to continue.",
        reply_markup=back_menu(),
    )


@router.message(TxPasswordResetState.enter_code, F.text)
async def tx_reset_enter_code(message: types.Message, state: FSMContext) -> None:
    """Validate the entered code."""
    entered_code = (message.text or "").strip()
    data = await state.get_data()
    expected_code = data.get("reset_code", "")

    if entered_code != expected_code:
        await message.answer(
            "❌ Invalid code. Please try again or request a new one with /reset_tx_password",
            reply_markup=back_menu(),
        )
        return

    await state.set_state(TxPasswordResetState.set_new_password)
    await message.answer(
        "✅ Code verified.\n\n"
        "Please enter your new transaction password (minimum 8 characters).",
        reply_markup=back_menu(),
    )


@router.message(TxPasswordResetState.set_new_password, F.text)
async def tx_reset_set_new_password(message: types.Message, state: FSMContext) -> None:
    """Store the new password and ask for confirmation."""
    password = message.text or ""
    if len(password) < 8:
        await message.answer("❌ Password must be at least 8 characters. Please try again.")
        return

    await state.update_data(new_tx_password=password)
    await state.set_state(TxPasswordResetState.confirm_new_password)
    await message.answer(
        "🔐 Please re-enter the new password to confirm.",
        reply_markup=back_menu(),
    )


@router.message(TxPasswordResetState.confirm_new_password, F.text)
async def tx_reset_confirm_new_password(message: types.Message, state: FSMContext) -> None:
    """Confirm the new password and save the hash."""
    data = await state.get_data()
    first = data.get("new_tx_password", "")
    second = message.text or ""
    profile_id = data.get("reset_profile_id")

    if first != second:
        await state.clear()
        await message.answer(
            "❌ Passwords do not match. Start again with /reset_tx_password",
            reply_markup=back_menu(),
        )
        return

    if not profile_id:
        await state.clear()
        await message.answer(
            "❌ Session expired. Please start again with /reset_tx_password",
            reply_markup=back_menu(),
        )
        return

    hashed = hash_tx_password(second)

    try:
        from backend.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("profiles").update({"gaming_tx_password_hash": hashed}).eq("id", profile_id).execute()
    except Exception:
        logger.exception("[TxPasswordReset] Failed to save password hash for %s", profile_id)
        await message.answer("❌ Could not save password. Please try again later.", reply_markup=back_menu())
        await state.clear()
        return

    await state.clear()
    await message.answer(
        "✅ Transaction password has been reset successfully.",
        reply_markup=back_menu(),
    )
