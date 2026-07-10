"""Inline keyboard builders for the ClawStation Telegram bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(miniapp_url: str | None = None) -> InlineKeyboardMarkup:
    """Return the main menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Wallet", callback_data="menu:wallet"),
        InlineKeyboardButton(text="Challenge", callback_data="menu:challenge"),
        InlineKeyboardButton(text="💸 Send", callback_data="m_send"),
    )
    builder.row(
        InlineKeyboardButton(text="Leaderboard", callback_data="menu:leaderboard"),
        InlineKeyboardButton(text="Profile", callback_data="menu:profile"),
    )
    builder.row(
        InlineKeyboardButton(text="📖 How to use ClawStation", callback_data="menu:learn"),
    )
    return builder.as_markup()


def challenge_confirm_menu(match_id: str) -> InlineKeyboardMarkup:
    """Return Accept / Decline inline buttons for a challenge."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Accept", callback_data=f"challenge:accept:{match_id}"),
        InlineKeyboardButton(text="Decline", callback_data=f"challenge:decline:{match_id}"),
    )
    return builder.as_markup()


def back_to_main() -> InlineKeyboardMarkup:
    """Return a single Back button."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Back", callback_data="menu:main"))
    return builder.as_markup()


def back_menu() -> InlineKeyboardMarkup:
    """Alias for back_to_main for compatibility."""
    return back_to_main()


def send_menu() -> InlineKeyboardMarkup:
    """Return the send menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👤 Send to @tag", callback_data="send_to_tag"),
        InlineKeyboardButton(text="📤 Send to address", callback_data="send_to_address"),
    )
    builder.row(InlineKeyboardButton(text="Back", callback_data="m_main"))
    return builder.as_markup()