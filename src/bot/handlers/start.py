"""Handler for the /start command and main menu callbacks."""
from __future__ import annotations

import logging
import os
from html import escape

from aiogram import types, F
from aiogram.enums import ParseMode
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

    # Geo-fence for Telegram is opt-in via TELEGRAM_USER_COUNTRY (ISO-2).
    # Do NOT map language_code → country (e.g. "en" is not a region).
    # API geo-fence still applies to HTTP; bot demos stay unblocked unless set.
    headers: dict = {}
    country = os.getenv("TELEGRAM_USER_COUNTRY")
    if country:
        headers["cf-ipcountry"] = country.upper()

    if headers:
        try:
            check_region(_FakeRequest(headers))
        except BlockedRegionError:
            await message.answer("Rematch isn't available in your region yet.")
            return
        except Exception as exc:
            logger.warning("[Start] Geo-fence check skipped due to error: %s", exc)

    try:
        profile = await get_or_create_profile(user)
    except Exception as exc:
        logger.exception("[Start] Profile create failed for telegram_id=%s", user.id)
        await message.answer(f"❌ Could not create your profile: {exc}")
        return

    try:
        await update_telegram_chat_id(profile["id"], message.chat.id)
    except Exception as exc:
        logger.warning("[Start] chat id update failed: %s", exc)

    # Arc-only product surface for now
    try:
        from gaming.src.backend.services.clawstation_circle import set_preferred_chain

        await set_preferred_chain(profile["id"], "arc")
    except Exception:
        logger.warning("[Start] set preferred arc failed for %s", profile["id"], exc_info=True)

    try:
        wallet = await ensure_user_wallet(profile["id"], chain_id="arc")
        address = wallet.get("address", "Not linked")
    except Exception as exc:
        logger.exception("[Start] Failed to ensure wallet for %s", profile["id"])
        await message.answer(f"❌ Wallet setup failed: {exc}")
        return

    # HTML parse mode — gaming tags contain underscores that break Markdown.
    name = escape(str(profile.get("display_name") or user.first_name or "Gamer"))
    raw_tag = str(profile.get("gaming_tag") or "—")
    tag = escape(raw_tag)
    addr = escape(str(address))
    bal_line = ""
    try:
        from gaming.src.backend.services.clawstation_circle import get_balance_summary

        s = await get_balance_summary(profile["id"], chain_id="arc")
        spend = float(s.get("spendable_usdc") or 0)
        other = float(s.get("other_usdc") or 0)
        total = spend + other
        bal_line = f"Balance: <b>${total:,.2f}</b>\n"
        if other > 0.009:
            bal_line += (
                f"⚠️ ${other:,.2f} is on a linked/old address — "
                f"send it to your play address to stake.\n"
            )
    except Exception:
        logger.warning("[Start] balance preview failed for %s", profile["id"], exc_info=True)

    text = (
        f"🎮 <b>Welcome to Rematch, {name}!</b>\n"
        f"<i>by sideQuest</i>\n\n"
        f"Your tag: <code>@{tag}</code>\n"
        f"Friends challenge you with this.\n\n"
        f"{bal_line}"
        f"Your <b>play</b> fund address:\n"
        f"<code>{addr}</code>\n\n"
        f"<b>Get started</b>\n"
        f"1. <b>Get money</b> → fund that play address only\n"
        f"2. <b>Challenge</b> a friend\n"
        f"3. Accept → Lock → Side → FT photo\n\n"
        f"Tap <b>How to play</b> under More anytime."
    )
    try:
        await message.answer(text, reply_markup=main_menu(), parse_mode=ParseMode.HTML)
    except Exception as exc:
        # Never fail silent — fall back to plain text so the user always gets a reply.
        logger.exception("[Start] Failed to send welcome HTML message: %s", exc)
        plain = (
            f"🎮 Welcome to Rematch, {profile.get('display_name') or user.first_name}!\n\n"
            f"Tag: {profile.get('gaming_tag') or '—'}\n\n"
            f"Your Arc deposit address:\n"
            f"{address}\n\n"
            f"1. Get USDC → fund address\n"
            f"2. New challenge → Lock → Side → FT photo"
        )
        await message.answer(plain, reply_markup=main_menu(), parse_mode=None)


@router.callback_query(F.data == "m_main")
async def cb_main(callback: types.CallbackQuery) -> None:
    """Back to main menu."""
    await callback.answer()
    await callback.message.edit_text(
        "Choose an option:",
        reply_markup=main_menu(),
    )


def _callback_as_user_message(callback: types.CallbackQuery, text: str) -> types.Message:
    """Build a Message whose ``from_user`` is the person who tapped the button.

    Inline callbacks arrive on a bot-authored message, so reusing
    ``callback.message`` alone makes handlers think the *bot* is the user
    (wrong profile / empty wallet). Always stamp ``from_user`` from the callback.
    """
    assert callback.message is not None
    assert callback.from_user is not None
    return callback.message.model_copy(
        update={
            "text": text,
            "from_user": callback.from_user,
        }
    )


@router.callback_query(F.data == "menu:wallet")
async def cb_menu_wallet(callback: types.CallbackQuery) -> None:
    """Wallet button → show balance for the user who tapped."""
    await callback.answer()
    from gaming.src.bot.handlers.balance import cmd_balance

    await cmd_balance(_callback_as_user_message(callback, "/balance"))


# menu:challenge is handled by simple_ui (button wizard) — do not override here.


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
    """Profile button → show profile for the user who tapped."""
    await callback.answer()
    from gaming.src.bot.handlers.profile import cmd_profile

    await cmd_profile(_callback_as_user_message(callback, "/profile"))


REMATCH_INFO_URL = "https://playingsidequest.fun/rematch"


@router.callback_query(F.data == "menu:learn")
async def cb_menu_learn(callback: types.CallbackQuery) -> None:
    """In-bot how-to (simple steps)."""
    await callback.answer()
    from gaming.src.bot.utils.flow import how_to_play

    await callback.message.edit_text(
        how_to_play(),
        reply_markup=back_menu(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "menu:app")
async def cb_menu_app(callback: types.CallbackQuery) -> None:
    """Send the Rematch site link."""
    await callback.answer()
    await callback.message.edit_text(
        f"🌐 Rematch\n\n{REMATCH_INFO_URL}",
        reply_markup=back_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Show all available commands."""
    from gaming.src.bot.utils.flow import short_help

    await message.answer(short_help(), reply_markup=back_menu(), parse_mode=ParseMode.HTML)


@router.message(Command("howto"))
async def cmd_howto(message: types.Message) -> None:
    """Full simple how-to."""
    from gaming.src.bot.utils.flow import how_to_play

    await message.answer(how_to_play(), reply_markup=back_menu(), parse_mode=ParseMode.HTML)
