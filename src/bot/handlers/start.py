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
from gaming.src.bot.keyboards import main_menu, back_menu, welcome_menu
from gaming.src.bot.utils.db import get_or_create_profile, update_telegram_chat_id

logger = logging.getLogger(__name__)

router = Router()


class _FakeRequest:
    """Minimal request double for the geo-fence check in a bot context."""

    def __init__(self, headers: dict):
        self.headers = headers
        self.client = None


def _start_payload(message: types.Message) -> str:
    """Extract deep-link payload from /start <payload>."""
    text = (message.text or message.caption or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Onboard a Telegram user: geo-check, profile, wallet, welcome message."""
    user = message.from_user
    if user is None:
        return

    # Instant ack so /start never feels dead while we hit Supabase/Circle
    try:
        await message.answer(
            "⏳ Opening Boardman…",
            reply_markup=main_menu(),
            parse_mode=None,
        )
    except Exception:
        pass

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
            await message.answer("Boardman isn't available in your region yet.")
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

    # Deep links: ctr_IKEJA01 (onile) · cup_ABC123 · m_XXXX (public match)
    payload = _start_payload(message)
    if payload:
        try:
            from gaming.src.backend.services.partners import (
                attribute_profile,
                get_partner,
                parse_start_payload,
                welcome_html,
            )
            from gaming.src.bot.keyboards import main_menu as mm

            kind, value = parse_start_payload(payload)

            if kind == "partner" and value:
                result = attribute_profile(
                    profile["id"], value, first_touch_only=True, source="start_deeplink"
                )
                partner = result.get("partner") or get_partner(value)
                if partner and result.get("ok"):
                    await message.answer(
                        welcome_html(partner),
                        parse_mode=ParseMode.HTML,
                        reply_markup=mm(),
                    )
                    # Fall through to normal welcome after partner card
                elif not partner:
                    await message.answer(
                        f"Partner code <code>{escape(value)}</code> not found. "
                        f"Ask the desk for a fresh QR.",
                        parse_mode=ParseMode.HTML,
                        reply_markup=mm(),
                    )

            elif kind == "cup" and value:
                from gaming.src.backend.services.tournament import (
                    format_tournament_card,
                    get_tournament,
                    join_tournament,
                    money_live,
                    tournaments_enabled,
                    TournamentError,
                )
                from aiogram.types import InlineKeyboardButton
                from aiogram.utils.keyboard import InlineKeyboardBuilder

                if not tournaments_enabled():
                    await message.answer(
                        "Cups are paused right now. Try a normal challenge.",
                        reply_markup=mm(),
                    )
                    return
                t = get_tournament(value)
                if not t:
                    await message.answer(
                        f"Cup <code>{escape(value)}</code> not found.",
                        parse_mode=ParseMode.HTML,
                        reply_markup=mm(),
                    )
                    return
                # Auto-join if open; else show status
                if (t.get("status") or "") == "open":
                    try:
                        t = await join_tournament(value, profile["id"])
                        note = ""
                        if not money_live():
                            note = "\n\n🧪 <i>Dry-run seat — no USDC locked yet.</i>"
                        elif float(t.get("entry_usdc") or 0) > 0:
                            note = "\n\n💵 <i>Entry locked into pot.</i>"
                        kb = InlineKeyboardBuilder()
                        kb.row(
                            InlineKeyboardButton(
                                text="📋 Cup status",
                                callback_data=f"t:status:{t.get('code')}",
                            )
                        )
                        kb.row(
                            InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main")
                        )
                        await message.answer(
                            f"✅ Joined cup <code>{escape(t.get('code') or value)}</code>."
                            f"{note}\n\n{format_tournament_card(t)}",
                            parse_mode=ParseMode.HTML,
                            reply_markup=kb.as_markup(),
                        )
                        return
                    except TournamentError as exc:
                        # already in / full → still show card
                        logger.info("[Start] cup join: %s", exc)
                kb = InlineKeyboardBuilder()
                if (t.get("status") or "") == "open":
                    kb.row(
                        InlineKeyboardButton(
                            text="✅ Join cup",
                            callback_data=f"t:join:{t.get('code')}",
                        )
                    )
                kb.row(
                    InlineKeyboardButton(
                        text="📋 Status", callback_data=f"t:status:{t.get('code')}"
                    )
                )
                kb.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
                await message.answer(
                    format_tournament_card(t),
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb.as_markup(),
                )
                return

            elif kind == "match" and value:
                from gaming.src.backend.services.game_catalog import display_name as game_display_name
                from gaming.src.backend.services.match_codes import display_code, load_challenge_by_ref
                from gaming.src.bot.keyboards import challenge_confirm_menu

                ch = load_challenge_by_ref(value)
                if ch and (ch.get("status") or "").lower() == "open":
                    mcode = display_code(ch)
                    gname = game_display_name(ch.get("game") or "EAFC")
                    stake = float(ch.get("amount_usdc") or 0)
                    await message.answer(
                        f"⚔️ <b>Open challenge</b>\n\n"
                        f"Match: <code>{escape(mcode)}</code>\n"
                        f"Stake: <b>${stake:,.2f}</b> · {escape(str(gname))}\n\n"
                        f"Tap Accept to take it:",
                        parse_mode=ParseMode.HTML,
                        reply_markup=challenge_confirm_menu(str(ch["id"])),
                    )
                    return
                await message.answer(
                    "That match is no longer open. Tap Public board or create a new challenge.",
                    reply_markup=mm(),
                )
                return
        except Exception:
            logger.exception("[Start] deep-link failed payload=%s", payload)

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
        import asyncio

        from gaming.src.backend.services.clawstation_circle import get_balance_summary

        # Cap wait — never let balance RPC delay the welcome menu for all users
        s = await asyncio.wait_for(
            get_balance_summary(profile["id"], chain_id="arc"), timeout=2.5
        )
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
        logger.warning("[Start] balance preview skipped/failed for %s", profile["id"])

    from gaming.src.bot.brand_assets import boardman_arena_url, boardman_site_url

    site = boardman_site_url()
    arena = boardman_arena_url()
    text = (
        f"🤝 <b>Welcome to Boardman, {name}.</b>\n"
        f"<i>Nice to have you here.</i>\n\n"
        f"Hope you make a lot of money. Hope you enjoy your games. "
        f"This desk is yours now — lock, play, settle.\n\n"
        f"Your tag: <code>@{tag}</code>\n"
        f"{bal_line}"
        f"Play address:\n<code>{addr}</code>\n\n"
        f"<b>Quick start</b>\n"
        f"1. <b>Get money</b> — fund that address\n"
        f"2. <b>Challenge</b> a friend, or watch Raja vs Nero live\n"
        f"3. Lock → play → send the result photo\n\n"
        f"🌐 {escape(site)}\n"
        f"♟️ {escape(arena)}"
    )
    try:
        from aiogram.types import FSInputFile

        from gaming.src.bot.brand_assets import boardman_welcome_image_path

        art = boardman_welcome_image_path()
        kb = welcome_menu()
        if art is not None:
            await message.answer_photo(
                photo=FSInputFile(str(art)),
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception("[Start] Failed to send welcome HTML message: %s", exc)
        plain = (
            f"Welcome to Boardman, {profile.get('display_name') or user.first_name}.\n"
            f"Nice to have you here. Hope you make money and enjoy your games.\n\n"
            f"Tag: {profile.get('gaming_tag') or '—'}\n"
            f"Play address:\n{address}\n\n"
            f"1. Get money\n2. Challenge a friend\n3. Lock → play → result photo\n\n"
            f"{site}"
        )
        await message.answer(plain, reply_markup=welcome_menu(), parse_mode=None)


@router.callback_query(F.data == "m_main")
async def cb_main(callback: types.CallbackQuery) -> None:
    """Back to main menu."""
    await callback.answer()
    try:
        await callback.message.edit_text(
            "Choose an option:",
            reply_markup=main_menu(),
        )
    except Exception:
        await callback.message.answer("Choose an option:", reply_markup=main_menu())


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
    """Send the Boardman site link."""
    await callback.answer()
    from gaming.src.bot.brand_assets import boardman_arena_url, boardman_site_url

    site = boardman_site_url()
    arena = boardman_arena_url()
    await callback.message.edit_text(
        f"🌐 <b>Boardman</b>\n\n"
        f"Site: {site}\n"
        f"Live chess: {arena}",
        reply_markup=back_menu(),
        parse_mode=ParseMode.HTML,
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
