"""Inline keyboard builders for the Rematch Telegram bot (simple UX)."""
from __future__ import annotations

import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

REMATCH_WEB = os.getenv("REMATCH_WEB_URL", "https://playingsidequest.fun/rematch")
REMATCH_BOARD = os.getenv(
    "REMATCH_LEADERBOARD_URL", "https://playingsidequest.fun/rematch/leaderboard"
)


def main_menu(miniapp_url: str | None = None) -> InlineKeyboardMarkup:
    """Big simple menu — no commands required."""
    builder = InlineKeyboardBuilder()
    web = miniapp_url or REMATCH_WEB
    builder.row(
        InlineKeyboardButton(text="🎮 My match", callback_data="ui:match"),
        InlineKeyboardButton(text="🔄 Rematch", callback_data="ui:rematch"),
    )
    builder.row(
        InlineKeyboardButton(text="⚔️ New challenge", callback_data="ui:challenge"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Wallet", callback_data="menu:wallet"),
        InlineKeyboardButton(text="👤 Profile", callback_data="menu:profile"),
    )
    builder.row(
        InlineKeyboardButton(text="🌐 Switch network", callback_data="ui:network"),
        InlineKeyboardButton(text="📋 Public board", callback_data="ui:board"),
    )
    # url= always works; WebApp needs BotFather domain — optional via env
    use_webapp = os.getenv("REMATCH_USE_WEBAPP", "").lower() in ("1", "true", "yes")
    if use_webapp:
        builder.row(
            InlineKeyboardButton(
                text="🏆 Leaderboard",
                web_app=WebAppInfo(url=REMATCH_BOARD),
            ),
            InlineKeyboardButton(
                text="🌐 Rematch site",
                web_app=WebAppInfo(url=web),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🏆 Leaderboard", url=REMATCH_BOARD),
            InlineKeyboardButton(text="🌐 Rematch site", url=web),
        )
    builder.row(
        InlineKeyboardButton(text="📖 How to play", callback_data="menu:learn"),
        InlineKeyboardButton(text="📜 Rules", callback_data="ui:rules"),
    )
    builder.row(
        InlineKeyboardButton(text="🎮 PLAY playbook", callback_data="ui:playbook"),
    )
    return builder.as_markup()


def network_menu(current: str = "arc") -> InlineKeyboardMarkup:
    """Pick preferred settlement / funding network."""
    builder = InlineKeyboardBuilder()
    opts = [
        ("arc", "🟣 Arc Testnet (USDC gas) ★"),
        ("base", "🔵 Base Sepolia (needs ETH gas)"),
        ("avalanche", "🔴 Avalanche Fuji"),
    ]
    for cid, label in opts:
        mark = " ✓" if cid == current else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{label}{mark}",
                callback_data=f"ui:network:set:{cid}",
            )
        )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def rematch_rivals_menu(rivals: list) -> InlineKeyboardMarkup:
    """One-tap rematch against past opponents."""
    builder = InlineKeyboardBuilder()
    if not rivals:
        builder.row(
            InlineKeyboardButton(text="⚔️ New challenge instead", callback_data="ui:challenge")
        )
    else:
        for r in rivals[:8]:
            pid = r.get("profile_id") or ""
            tag = r.get("tag") or "player"
            stake = r.get("stake") or 1
            chain = r.get("chain") or "arc"
            game = r.get("game") or "EAFC"
            label = f"🔄 @{tag} · ${stake:.0f} · {game} · {chain}"
            if len(label) > 64:
                label = f"🔄 @{tag} · ${stake:.0f} · {chain}"
            builder.row(
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"ui:rematch:go:{pid}",
                )
            )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def rematch_after_result_menu(opponent_id: str, label: str = "🔄 Rematch same setup") -> InlineKeyboardMarkup:
    """Shown after a match resolves — instant rematch with that opponent."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=label[:64],
            callback_data=f"ui:rematch:go:{opponent_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="🎮 My match", callback_data="ui:match"),
        InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"),
    )
    return builder.as_markup()


def challenge_confirm_menu(match_id: str) -> InlineKeyboardMarkup:
    """Accept / Decline for an invite.

    Callbacks keep the internal UUID (not shown to users in text).
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Accept", callback_data=f"challenge:accept:{match_id}"),
        InlineKeyboardButton(text="❌ Decline", callback_data=f"challenge:decline:{match_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Match status", callback_data=f"ui:info:{match_id}"),
    )
    return builder.as_markup()


def match_actions_menu(challenge: dict, profile_id: str) -> InlineKeyboardMarkup:
    """Context buttons for the user's active match — no typing IDs."""
    cid = challenge["id"]
    status = (challenge.get("status") or "").lower()
    is_creator = profile_id == challenge.get("creator_id")
    is_opp = profile_id == challenge.get("opponent_id")
    builder = InlineKeyboardBuilder()

    if status in ("accepted", "open", "creator_locked"):
        # Lock stake if appropriate
        if is_creator and status in ("accepted", "open") and not challenge.get("creator_lock_tx_id"):
            builder.row(
                InlineKeyboardButton(text="🔐 Lock my stake", callback_data=f"ui:lock:{cid}"),
            )
        if is_opp and status == "creator_locked" and not challenge.get("opponent_lock_tx_id"):
            builder.row(
                InlineKeyboardButton(text="🔐 Lock my stake", callback_data=f"ui:lock:{cid}"),
            )
        if is_creator and status == "creator_locked":
            builder.row(
                InlineKeyboardButton(
                    text="⏳ Waiting for opponent to lock…",
                    callback_data=f"ui:info:{cid}",
                ),
            )

    if status in ("locked", "playing", "submitted"):
        my_side = (
            challenge.get("creator_side")
            if is_creator
            else challenge.get("opponent_side")
        )
        if not my_side:
            builder.row(
                InlineKeyboardButton(text="🏠 I am HOME", callback_data=f"ui:side:{cid}:home"),
                InlineKeyboardButton(text="✈️ I am AWAY", callback_data=f"ui:side:{cid}:away"),
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text=f"Side: {my_side.upper()} ✓",
                    callback_data=f"ui:side:{cid}:menu",
                ),
            )
        builder.row(
            InlineKeyboardButton(
                text="📸 Submit result (photo)",
                callback_data=f"ui:report:{cid}",
            ),
        )

    if status == "submitted":
        builder.row(
            InlineKeyboardButton(text="⏳ Check settlement", callback_data=f"ui:settle:{cid}"),
        )

    if status == "disputed":
        builder.row(
            InlineKeyboardButton(text="⚠️ Disputed — status", callback_data=f"ui:info:{cid}"),
        )

    # Cancel: free / refund / mutual propose-confirm
    has_lock = bool(
        challenge.get("creator_lock_tx_id") or challenge.get("opponent_lock_tx_id")
    )
    if status in ("open", "accepted") and not has_lock:
        builder.row(
            InlineKeyboardButton(text="❌ Cancel match", callback_data=f"ui:cancel:{cid}"),
        )
    elif status == "creator_locked" or (
        challenge.get("creator_lock_tx_id") and not challenge.get("opponent_lock_tx_id")
    ):
        builder.row(
            InlineKeyboardButton(
                text="❌ Cancel & refund", callback_data=f"ui:cancel:{cid}"
            ),
        )
    elif status in ("locked", "playing", "submitted"):
        note = str(challenge.get("admin_resolution_note") or "")
        if note.startswith("cancel_proposed:"):
            proposer = note.split(":")[1] if ":" in note else ""
            if proposer and proposer != profile_id:
                builder.row(
                    InlineKeyboardButton(
                        text="✅ Confirm cancel (refund both)",
                        callback_data=f"ui:cancel:{cid}",
                    ),
                )
            else:
                builder.row(
                    InlineKeyboardButton(
                        text="⏳ Cancel proposed — waiting…",
                        callback_data=f"ui:info:{cid}",
                    ),
                )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="🤝 Propose cancel", callback_data=f"ui:cancel:{cid}"
                ),
            )

    builder.row(
        InlineKeyboardButton(text="📋 Match status", callback_data=f"ui:info:{cid}"),
        InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"),
    )
    return builder.as_markup()


def side_menu(match_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏠 HOME", callback_data=f"ui:side:{match_id}:home"),
        InlineKeyboardButton(text="✈️ AWAY", callback_data=f"ui:side:{match_id}:away"),
    )
    builder.row(InlineKeyboardButton(text="« Back", callback_data=f"ui:info:{match_id}"))
    return builder.as_markup()


def stake_amount_menu() -> InlineKeyboardMarkup:
    """Stake presets — only amounts at or under CLAW_MAX_STAKE_USDC."""
    import os
    from decimal import Decimal

    try:
        max_s = float(os.getenv("CLAW_MAX_STAKE_USDC", "25"))
    except ValueError:
        max_s = 25.0
    builder = InlineKeyboardBuilder()
    presets = [a for a in (1, 5, 10, 25) if a <= max_s + 1e-9]
    if not presets:
        presets = [1]
    for amt in presets:
        builder.add(
            InlineKeyboardButton(text=f"${amt}", callback_data=f"ui:chal:amt:{amt}"),
        )
    builder.adjust(min(4, len(presets)))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"))
    return builder.as_markup()


def game_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, key in (
        ("⚽ EA FC", "EAFC"),
        ("🏀 NBA 2K", "NBA2K"),
        ("🎮 Other", "Other"),
    ):
        builder.add(InlineKeyboardButton(text=label, callback_data=f"ui:chal:game:{key}"))
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"))
    return builder.as_markup()


def chain_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🟣 Arc Testnet (USDC gas) ★",
            callback_data="ui:chal:chain:arc",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🔵 Base Sepolia", callback_data="ui:chal:chain:base"),
        InlineKeyboardButton(text="🔴 Avalanche Fuji", callback_data="ui:chal:chain:avalanche"),
    )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"))
    return builder.as_markup()


def confirm_challenge_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Send challenge", callback_data="ui:chal:confirm"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"),
    )
    return builder.as_markup()


def after_report_menu(match_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Match status", callback_data=f"ui:info:{match_id}"),
        InlineKeyboardButton(text="🏠 Menu", callback_data="menu:main"),
    )
    return builder.as_markup()


def back_to_main() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def back_menu() -> InlineKeyboardMarkup:
    return back_to_main()


def wallet_menu() -> InlineKeyboardMarkup:
    """Actions on the wallet / balance screen."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💸 Withdraw", callback_data="ui:withdraw"),
    )
    builder.row(
        InlineKeyboardButton(text="🌐 Switch network", callback_data="ui:network"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def send_menu() -> InlineKeyboardMarkup:
    """Withdraw / send destination picker."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👤 To @tag (ClawStation)", callback_data="send_to_tag"),
    )
    builder.row(
        InlineKeyboardButton(text="📤 To 0x address (external)", callback_data="send_to_address"),
    )
    builder.row(
        InlineKeyboardButton(text="« Wallet", callback_data="menu:wallet"),
        InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"),
    )
    return builder.as_markup()
