"""
bot/keyboards.py: For all HUD/Inline UI elements.
"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types

COUNTRIES = [
    "🇺🇸 USA", "🇬🇧 UK", "🇪🇸 Spain", "🇫🇷 France",
    "🇩🇪 Germany", "🇮🇹 Italy", "🇳🇱 Netherlands",
    "🇧🇷 Brazil", "🇦🇷 Argentina", "🇵🇹 Portugal",
    "🇯🇵 Japan", "🇰🇷 South Korea", "🇨🇳 China",
    "🇦🇪 UAE", "🇸🇦 Saudi Arabia", "🇶🇦 Qatar",
    "🇳🇬 Nigeria", "🇬🇭 Ghana", "🇰🇪 Kenya",
    "🇿🇦 South Africa", "🇪🇬 Egypt", "🇲🇦 Morocco",
]

# USDC stake amounts in $
STAKE_AMOUNTS = [5, 10, 25, 50, 100, 250, 500]

def main_menu() -> types.InlineKeyboardMarkup:
    """Main menu — wallet, challenge, leaderboard, profile."""
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="💰 Wallet", callback_data="m_wallet"),
        types.InlineKeyboardButton(text="⚔️ Challenge", callback_data="ritual_start")
    )
    b.row(
        types.InlineKeyboardButton(text="🏆 Leaderboard", callback_data="m_leader"),
        types.InlineKeyboardButton(text="⚙️ Profile", callback_data="m_profile")
    )
    b.row(types.InlineKeyboardButton(text="🌐 Open App", callback_data="m_web"))
    return b.as_markup()

def back_menu() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

def challenge_menu() -> types.InlineKeyboardMarkup:
    """Game selection — EA FC only."""
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="⚽ EA FC", callback_data="g_eafc"))
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

def stake_menu() -> types.InlineKeyboardMarkup:
    """Stake amounts in USDC ($)."""
    b = InlineKeyboardBuilder()
    for s in STAKE_AMOUNTS:
        b.button(text=f"${s}", callback_data=f"s_{s}")
    b.adjust(3)
    b.row(types.InlineKeyboardButton(text="✏️ Custom", callback_data="s_custom"))
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

def side_menu(prefix: str) -> types.InlineKeyboardMarkup:
    """Home / Away side selection."""
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="🏠 HOME", callback_data=f"side:{prefix}:home"),
        types.InlineKeyboardButton(text="✈️ AWAY", callback_data=f"side:{prefix}:away")
    )
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()


def club_search_results_menu(prefix: str, clubs: list[str]) -> types.InlineKeyboardMarkup:
    """Show matching clubs as selectable buttons."""
    b = InlineKeyboardBuilder()
    for club in clubs:
        # Callback data length limit is ~64 bytes; keep display text short-ish
        display = club[:30] + "…" if len(club) > 30 else club
        b.row(types.InlineKeyboardButton(text=display, callback_data=f"club:{prefix}:{club}"))
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

def country_menu() -> types.InlineKeyboardMarkup:
    """Country selection for profile."""
    b = InlineKeyboardBuilder()
    for c in COUNTRIES:
        b.button(text=c, callback_data=f"c:{c}")
    b.adjust(3)
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main"))
    return b.as_markup()

def opponent_menu() -> types.InlineKeyboardMarkup:
    """Opponent selection — invite, search, or public."""
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="📤 Invite Friend", callback_data="opp_invite"),
        types.InlineKeyboardButton(text="🔍 Search @username", callback_data="opp_search")
    )
    b.row(
        types.InlineKeyboardButton(text="🌎 PUBLIC: Everyone", callback_data="opp_public"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main")
    )
    return b.as_markup()

def confirm_menu(match_id: str) -> types.InlineKeyboardMarkup:
    """Confirm and lock stakes."""
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="✅ Lock Stakes", callback_data=f"conf_confirm:{match_id}"),
        types.InlineKeyboardButton(text="❌ Cancel", callback_data="conf_cancel")
    )
    return b.as_markup()

def profile_menu(is_public: bool) -> types.InlineKeyboardMarkup:
    """Profile actions — wallet, toggle, menu."""
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🏦 Wallet", callback_data="m_wallet"))
    b.row(
        types.InlineKeyboardButton(
            text="🔔 PUBLIC: ON" if is_public else "🔕 PUBLIC: OFF",
            callback_data="toggle_pub"
        )
    )
    b.row(types.InlineKeyboardButton(text="📋 Menu", callback_data="m_main"))
    return b.as_markup()

def accept_challenge_menu(match_id: str) -> types.InlineKeyboardMarkup:
    """Accept a pending challenge."""
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="⚡ ACCEPT & LOCK", callback_data=f"accept:{match_id}"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main")
    )
    return b.as_markup()

def link_menu(platform: str) -> types.InlineKeyboardMarkup:
    """Link PSN or Xbox account."""
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text=f"Link {platform}", callback_data=f"link_{platform.lower()}"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="m_main")
    )
    return b.as_markup()