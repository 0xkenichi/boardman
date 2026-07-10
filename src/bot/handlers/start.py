"""Handler for the /start command and main menu callbacks."""
from __future__ import annotations

import logging
import os

from aiogram import types, F
from aiogram.filters import Command
from aiogram import Router

from gaming.src.backend.middleware.geo_fence import BlockedRegionError, check_region
from gaming.src.backend.services.clawstation_circle import ensure_user_wallet
from gaming.src.bot.keyboards import main_menu, back_menu
from gaming.src.bot.utils.db import get_or_create_profile, update_telegram_chat_id

logger = logging.getLogger(__name__)

router = Router()


class _FakeRequest:
    """Minimal request double for the geo-fence check in a bot context."""

    def __init__(self, headers: dict):
        self.headers = headers
        self.client = None


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Onboard a Telegram user: geo-check, profile, wallet, welcome message."""
    user = message.from_user
    if user is None:
        return

    country = os.getenv("TELEGRAM_USER_COUNTRY")
    headers: dict = {}
    if country:
        headers["cf-ipcountry"] = country
    elif getattr(user, "language_code", None):
        # Best-effort signal only; never block solely on language code.
        headers["cf-ipcountry"] = user.language_code.upper()

    try:
        check_region(_FakeRequest(headers))
    except BlockedRegionError:
        await message.answer("ClawStation isn't available in your region yet.")
        return
    except Exception as exc:
        logger.warning("[Start] Geo-fence check skipped due to error: %s", exc)

    profile = await get_or_create_profile(user)
    await update_telegram_chat_id(profile["id"], message.chat.id)

    try:
        wallet = await ensure_user_wallet(profile["id"])
        address = wallet.get("address", "Not linked")
    except Exception as exc:
        logger.exception("[Start] Failed to ensure wallet for %s", profile["id"])
        await message.answer(f"❌ Wallet setup failed: {exc}")
        return

    name = profile.get("display_name") or user.first_name or "Gamer"
    short_addr = f"{address[:10]}...{address[-4:]}" if len(address) > 14 else address
    text = (
        f"🎮 *Welcome to ClawStation by sideQuest, {name}!*\n\n"
        f"Your USDC deposit address (Base Sepolia):\n"
        f"`{short_addr}`\n\n"
        f"Send USDC here to fund your wallet. All gameplay happens in this chat. Tap \"How to use ClawStation\" for a guide."
    )
    await message.answer(text, reply_markup=main_menu())


@router.callback_query(F.data == "m_main")
async def cb_main(callback: types.CallbackQuery) -> None:
    """Back to main menu."""
    await callback.answer()
    await callback.message.edit_text(
        "Choose an option:",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "menu:wallet")
async def cb_menu_wallet(callback: types.CallbackQuery) -> None:
    """Wallet button → show balance."""
    await callback.answer()
    # Reuse the balance handler by constructing a fake message.
    from gaming.src.bot.handlers.balance import cmd_balance
    await cmd_balance(callback.message)


@router.callback_query(F.data == "menu:challenge")
async def cb_menu_challenge(callback: types.CallbackQuery) -> None:
    """Challenge button → start challenge creation."""
    await callback.answer()
    from gaming.src.bot.handlers.challenge import cmd_challenge
    # Build a message with the usage text to start the flow.
    callback.message.text = '/challenge'
    await cmd_challenge(callback.message)


@router.callback_query(F.data == "menu:leaderboard")
async def cb_menu_leaderboard(callback: types.CallbackQuery) -> None:
    """Leaderboard button → placeholder."""
    await callback.answer()
    await callback.message.edit_text(
        "🏆 Leaderboard is coming soon!\n\nWin challenges to climb the ranks.",
        reply_markup=back_menu(),
    )


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: types.CallbackQuery) -> None:
    """Profile button → show own profile."""
    await callback.answer()
    from gaming.src.bot.handlers.profile import cmd_profile
    callback.message.text = '/profile'
    await cmd_profile(callback.message)


CLAWSTATION_INFO_URL = "https://playingsidequest.fun/clawstation"


@router.callback_query(F.data == "menu:learn")
async def cb_menu_learn(callback: types.CallbackQuery) -> None:
    """Send the informational ClawStation page link."""
    await callback.answer()
    text = (
        "📖 *How to use ClawStation*\n\n"
        "Gameplay happens right here in Telegram.\n"
        "Visit the guide for FAQs, commands, and step-by-step instructions:\n\n"
        f"{CLAWSTATION_INFO_URL}"
    )
    await callback.message.edit_text(text, reply_markup=back_menu())


@router.callback_query(F.data == "menu:app")
async def cb_menu_app(callback: types.CallbackQuery) -> None:
    """Send the informational ClawStation page link."""
    await callback.answer()
    await callback.message.edit_text(
        f"📖 Learn how to use ClawStation:\n\n{CLAWSTATION_INFO_URL}",
        reply_markup=back_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Show all available commands."""
    text = (
        "📋 *ClawStation Commands*\n\n"
        "🏠 *General*\n"
        "  /start — Start ClawStation\n"
        "  /help — Show this help message\n\n"
        "💰 *Wallet & Transactions*\n"
        "  /balance — Check USDC balance\n"
        "  /send — Send USDC to a user or address\n"
        "  /set_tx_password — Set transaction password\n"
        "  /reset_tx_password — Reset transaction password\n\n"
        "👤 *Profile & Social*\n"
        "  /profile — View your profile\n"
        "  /link_psn <psn_username> — Link PlayStation Network ID\n"
        "  /link_xbox <xbox_gamertag> — Link Xbox Gamertag\n"
        "  /link_email <email> — Link backup email\n"
        "  /set_bio <bio_text> — Set your gaming bio\n\n"
        "⚔️ *Gaming*\n"
        "  /challenge — Create a challenge\n"
        "  /dispute <challenge_id> — Raise a dispute on a challenge\n"
        "  /lock_stake <challenge_id> — Lock your challenge stake on-chain\n"
        "  /submit_score <challenge_id> <score> — Submit your match score\n"
    )
    await message.answer(text, reply_markup=back_menu())