"""
bot/keyboards.py: For all HUD/Inline UI elements.
"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types

# Allowed team selections — must match validation in match_manager.set_match_team
ALLOWED_TEAMS = ["Real Madrid", "Barcelona", "Man City", "Liverpool", "PSG", "Bayern", "Lakers", "Warriors"]

def main_menu() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="💰 Wallet",      callback_data="m_wallet"),
          types.InlineKeyboardButton(text="⚔️ Challenge",    callback_data="ritual_start"))
    b.row(types.InlineKeyboardButton(text="🏆 Leaderboard",  callback_data="m_leader"),
          types.InlineKeyboardButton(text="⚙️ Profile",      callback_data="m_profile"))
    b.row(types.InlineKeyboardButton(text="🌐 Open App",     callback_data="m_web"))
    return b.as_markup()

def back_menu() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

def challenge_menu() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="⚽ EA FC",  callback_data="g_eafc"))
    b.row(types.InlineKeyboardButton(text="🏀 NBA 2K", callback_data="g_nba"))
    b.row(types.InlineKeyboardButton(text="🎮 FIFA",   callback_data="g_fifa"))
    b.row(types.InlineKeyboardButton(text="◀️ Back",   callback_data="m_main"))
    return b.as_markup()

def stake_menu() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="₦500",       callback_data="s_500"))
    b.row(types.InlineKeyboardButton(text="₦1000",      callback_data="s_1000"))
    b.row(types.InlineKeyboardButton(text="₦5000",      callback_data="s_5000"))
    b.row(types.InlineKeyboardButton(text="✏️ Custom",  callback_data="s_custom"))
    b.row(types.InlineKeyboardButton(text="◀️ Back",    callback_data="m_main"))
    return b.as_markup()

# BUG-FIX: team_menu callback_data is t:{prefix}:{team} — exactly 3 colon-parts
def team_menu(prefix: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in ALLOWED_TEAMS:
        b.button(text=t, callback_data=f"t:{prefix}:{t}")
    b.adjust(2)
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

# BUG-FIX: single definition, no match_id param
def opponent_menu() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="📤 Invite Friend",     callback_data="opp_invite"))
    b.row(types.InlineKeyboardButton(text="🔍 Search @username",  callback_data="opp_search"))
    b.row(types.InlineKeyboardButton(text="🌎 PUBLIC ARENA",      callback_data="opp_public"))
    b.row(types.InlineKeyboardButton(text="◀️ Back",               callback_data="m_main"))
    return b.as_markup()

def confirm_menu(match_id: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="✅ LOCK STAKES",
                                      callback_data=f"conf_confirm:{match_id}"))
    b.row(types.InlineKeyboardButton(text="❌ Cancel",
                                      callback_data="conf_cancel"))
    return b.as_markup()

def profile_menu(is_public: bool) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🏦 Wallet", callback_data="m_wallet"))
    b.row(types.InlineKeyboardButton(
        text="🔔 PUBLIC: ON" if is_public else "🔕 PUBLIC: OFF",
        callback_data="toggle_pub"))
    b.row(types.InlineKeyboardButton(text="📋 Menu", callback_data="m_main"))
    return b.as_markup()

def accept_challenge_menu(match_id: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="⚡ ACCEPT & LOCK",
                                      callback_data=f"accept:{match_id}"))
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()