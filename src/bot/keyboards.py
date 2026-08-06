"""Inline keyboard builders for the Boardman Telegram bot (simple UX)."""
from __future__ import annotations

import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

REMATCH_WEB = os.getenv("REMATCH_WEB_URL", "https://boardman.playingsidequest.fun")
REMATCH_BOARD = os.getenv(
    "REMATCH_LEADERBOARD_URL", "https://playingsidequest.fun/rematch/leaderboard"
)
REMATCH_BOT_URL = os.getenv(
    "NEXT_PUBLIC_TELEGRAM_BOT_URL",
    os.getenv("TELEGRAM_BOT_URL", "https://t.me/ClawStationOfficialBot"),
)


def rematch_group_url() -> str | None:
    """Public Telegram group invite for live rooms / community.

    Set any of: REMATCH_TELEGRAM_GROUP_URL, TELEGRAM_GROUP_URL,
    NEXT_PUBLIC_TELEGRAM_GROUP_URL (same as web).
    Returns None when unset or when it only points at the bot itself.
    """
    raw = (
        os.getenv("REMATCH_TELEGRAM_GROUP_URL")
        or os.getenv("TELEGRAM_GROUP_URL")
        or os.getenv("NEXT_PUBLIC_TELEGRAM_GROUP_URL")
        or os.getenv("NEXT_PUBLIC_REMATCH_TG_GROUP")
        or ""
    ).strip()
    if not raw:
        return None
    if not raw.startswith("http"):
        raw = f"https://{raw.lstrip('/')}"
    # Don't show a "join group" link that just re-opens the bot DM
    bot = (REMATCH_BOT_URL or "").rstrip("/").lower()
    if raw.rstrip("/").lower() in (bot, f"{bot}/"):
        return None
    if "clawstationofficialbot" in raw.lower() and "/+" not in raw:
        return None
    return raw


def main_menu(miniapp_url: str | None = None) -> InlineKeyboardMarkup:
    """Minimal button-first home — no crypto jargon, few choices."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎮 My match", callback_data="ui:match"),
        InlineKeyboardButton(text="⚔️ Challenge", callback_data="ui:challenge"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Wallet", callback_data="menu:wallet"),
        InlineKeyboardButton(text="💧 Get money", callback_data="ui:get_money"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Rematch", callback_data="ui:rematch"),
        InlineKeyboardButton(text="👤 Profile", callback_data="menu:profile"),
    )
    # Community + public board — always visible (not buried only under More)
    group = rematch_group_url()
    if group:
        builder.row(
            InlineKeyboardButton(text="💬 Join community", url=group),
            InlineKeyboardButton(text="📋 Public board", callback_data="ui:board"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="💬 Join community", callback_data="ui:community"),
            InlineKeyboardButton(text="📋 Public board", callback_data="ui:board"),
        )
    builder.row(
        InlineKeyboardButton(text="⋯ More", callback_data="ui:more"),
    )
    return builder.as_markup()


def more_menu(miniapp_url: str | None = None) -> InlineKeyboardMarkup:
    """Secondary links — board, community, site, rules."""
    builder = InlineKeyboardBuilder()
    web = miniapp_url or REMATCH_WEB
    group = rematch_group_url()
    builder.row(
        InlineKeyboardButton(text="📋 Public board", callback_data="ui:board"),
        InlineKeyboardButton(text="🏆 Leaderboard", url=REMATCH_BOARD),
    )
    if group:
        builder.row(InlineKeyboardButton(text="💬 Join community · live rooms", url=group))
    else:
        builder.row(
            InlineKeyboardButton(text="💬 Join community · live rooms", callback_data="ui:community")
        )
    builder.row(
        InlineKeyboardButton(text="🌐 Site", url=web),
        InlineKeyboardButton(text="📜 Rules", callback_data="ui:rules"),
    )
    builder.row(
        InlineKeyboardButton(text="📖 How to play", callback_data="menu:learn"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def community_menu() -> InlineKeyboardMarkup:
    """Live rooms / public matchmaking entry points."""
    builder = InlineKeyboardBuilder()
    group = rematch_group_url()
    if group:
        builder.row(InlineKeyboardButton(text="💬 Open community group", url=group))
    builder.row(
        InlineKeyboardButton(text="📋 Public board", callback_data="ui:board"),
        InlineKeyboardButton(text="⚔️ Post challenge", callback_data="ui:challenge"),
    )
    builder.row(InlineKeyboardButton(text="🌐 Boardman site", url=REMATCH_WEB))
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def network_menu(current: str = "arc") -> InlineKeyboardMarkup:
    """Arc-only for now (other chains kept in backend, not offered in UI)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🟣 Arc ✓",
            callback_data="ui:network:set:arc",
        )
    )
    builder.row(
        InlineKeyboardButton(text="💧 Get money", callback_data="ui:get_money"),
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
        game_id = str(challenge.get("game") or challenge.get("game_type") or "")
        binary = False
        report_btn = "📸 Submit result — how to"
        try:
            from gaming.src.backend.services.game_catalog import is_binary_outcome

            binary = is_binary_outcome(game_id)
            # Button label reflects how *this* game is reported
            report_btn = (
                "📸 Report result (W or L)"
                if binary
                else "📸 Report score (e.g. 5-3)"
            )
        except Exception:
            pass

        my_side = (
            challenge.get("creator_side")
            if is_creator
            else challenge.get("opponent_side")
        )
        # Scoreline games need HOME/AWAY; binary win/lose still can use side for mapping
        if not my_side:
            if binary:
                builder.row(
                    InlineKeyboardButton(
                        text="🏠 I am HOME (optional)",
                        callback_data=f"ui:side:{cid}:home",
                    ),
                    InlineKeyboardButton(
                        text="✈️ I am AWAY (optional)",
                        callback_data=f"ui:side:{cid}:away",
                    ),
                )
            else:
                builder.row(
                    InlineKeyboardButton(
                        text="🏠 I am HOME", callback_data=f"ui:side:{cid}:home"
                    ),
                    InlineKeyboardButton(
                        text="✈️ I am AWAY", callback_data=f"ui:side:{cid}:away"
                    ),
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
                text=report_btn,
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


def game_category_menu() -> InlineKeyboardMarkup:
    """First step: iMessage vs Console (catalog-driven)."""
    from gaming.src.backend.services.game_catalog import list_categories

    builder = InlineKeyboardBuilder()
    cats = list_categories(enabled_only=True)
    if not cats:
        cats = [
            {"id": "imessage", "label": "📱 iMessage"},
            {"id": "console", "label": "🎮 Console"},
        ]
    for c in cats:
        builder.row(
            InlineKeyboardButton(
                text=c["label"][:64],
                callback_data=f"ui:chal:cat:{c['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"))
    return builder.as_markup()


def game_menu(category: str | None = None) -> InlineKeyboardMarkup:
    """Games for a category, or legacy flat console list."""
    from gaming.src.backend.services.game_catalog import list_games

    builder = InlineKeyboardBuilder()
    if category:
        games = list_games(category=category, enabled_only=True)
    else:
        games = list_games(category="console", enabled_only=True)
        if not games:
            games = [
                {"game_id": "EAFC", "display_name": "EA FC", "emoji": "⚽"},
                {"game_id": "NBA2K", "display_name": "NBA 2K", "emoji": "🏀"},
                {"game_id": "Other", "display_name": "Other", "emoji": "🎮"},
            ]
    for g in games[:12]:
        emoji = g.get("emoji") or ""
        label = f"{emoji} {g.get('display_name') or g['game_id']}".strip()
        gid = g["game_id"]
        # Telegram callback_data max 64 bytes
        cb = f"ui:chal:game:{gid}"
        if len(cb.encode("utf-8")) > 64:
            cb = f"ui:chal:game:{gid[:40]}"
        builder.row(InlineKeyboardButton(text=label[:64], callback_data=cb))
    if category:
        builder.row(
            InlineKeyboardButton(text="« Categories", callback_data="ui:chal:cats")
        )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"))
    return builder.as_markup()


def chain_menu() -> InlineKeyboardMarkup:
    """Arc-only challenge network (legacy callback kept for in-flight wizards)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🟣 Arc",
            callback_data="ui:chal:chain:arc",
        ),
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
        InlineKeyboardButton(text="💧 Get money", callback_data="ui:get_money"),
        InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:wallet"),
    )
    builder.row(
        InlineKeyboardButton(text="💸 Withdraw", callback_data="ui:withdraw"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def get_money_menu() -> InlineKeyboardMarkup:
    """Choose how to fund: Kobox (partner) first, then bank fallback / crypto."""
    builder = InlineKeyboardBuilder()
    try:
        from gaming.src.backend.services.kobox_partner import (
            kobox_enabled,
            kobox_name,
            kobox_referral_url,
        )

        if kobox_enabled():
            url = kobox_referral_url()
            label = f"⭐ Open {kobox_name()} (recommended)"
            if url:
                builder.row(InlineKeyboardButton(text=label[:64], url=url))
            else:
                builder.row(
                    InlineKeyboardButton(text=label[:64], callback_data="ui:topup:kobox")
                )
    except Exception:
        pass
    builder.row(
        InlineKeyboardButton(
            text="🇳🇬 We'll do it — pay Naira to our bank",
            callback_data="ui:topup:ngn",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🇺🇸 We'll do it — pay USD to our bank",
            callback_data="ui:topup:usd",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🪙 Crypto / play address", callback_data="ui:topup:crypto"),
    )
    builder.row(
        InlineKeyboardButton(text="« Wallet", callback_data="menu:wallet"),
        InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"),
    )
    return builder.as_markup()


def fiat_amount_presets_menu(currency: str = "ngn") -> InlineKeyboardMarkup:
    """Quick amounts for Naira or USD bank top-ups."""
    builder = InlineKeyboardBuilder()
    cur = (currency or "ngn").lower()
    if cur == "usd":
        for amt in (5, 10, 20, 50):
            builder.add(
                InlineKeyboardButton(
                    text=f"${amt}",
                    callback_data=f"ui:topup:amt:usd:{amt}",
                )
            )
        builder.adjust(4)
    else:
        # ₦ presets (roughly → credit after ~$2 fee at ~1650)
        for amt in (10000, 20000, 50000, 100000):
            label = f"₦{amt // 1000}k" if amt >= 1000 else f"₦{amt}"
            builder.add(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"ui:topup:amt:ngn:{amt}",
                )
            )
        builder.adjust(4)
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data="ui:topup:cancel_wizard"),
    )
    return builder.as_markup()


def fiat_confirm_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Continue — show bank details", callback_data="ui:topup:confirm"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data="ui:topup:cancel_wizard"),
    )
    return builder.as_markup()


def fiat_proof_menu(ref: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Wallet", callback_data="menu:wallet"),
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel this top-up",
            callback_data=f"ui:topup:cancel:{ref}",
        ),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def get_usdc_menu(
    faucet_url: str = "https://faucet.circle.com/",
    helper_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Fund helper (address prefilled) + Circle faucet + refresh wallet."""
    builder = InlineKeyboardBuilder()
    if helper_url:
        builder.row(
            InlineKeyboardButton(text="📋 Fund page (copy address)", url=helper_url),
        )
    builder.row(
        InlineKeyboardButton(text="🔗 Open faucet", url=faucet_url),
    )
    builder.row(
        InlineKeyboardButton(text="🇳🇬 Naira / 🇺🇸 USD bank", callback_data="ui:get_money"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 I funded — refresh", callback_data="menu:wallet"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    return builder.as_markup()


def send_menu() -> InlineKeyboardMarkup:
    """Withdraw / send destination picker — Kobox cash-out first, then 0x / @tag."""
    builder = InlineKeyboardBuilder()
    try:
        from gaming.src.backend.services.kobox_partner import (
            kobox_enabled,
            kobox_name,
            kobox_referral_url,
        )

        if kobox_enabled():
            url = kobox_referral_url()
            label = f"⭐ Cash out via {kobox_name()}"
            if url:
                builder.row(InlineKeyboardButton(text=label[:64], url=url))
            else:
                builder.row(
                    InlineKeyboardButton(text=label[:64], callback_data="ui:withdraw:kobox")
                )
    except Exception:
        pass
    builder.row(
        InlineKeyboardButton(
            text="📤 To 0x (Kobox or any wallet)",
            callback_data="send_to_address",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="👤 To @tag (Boardman player)", callback_data="send_to_tag"),
    )
    builder.row(
        InlineKeyboardButton(text="« Wallet", callback_data="menu:wallet"),
        InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"),
    )
    return builder.as_markup()
