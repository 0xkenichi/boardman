"""Guided report interview — ask only what's needed for a fair ruling.

Collects, in order:
  1. Final-screen photo
  2. Reporter side (HOME/AWAY) when missing / scoreline games
  3. Outcome (W/L or home-away scoreline)
  4. Optional: which on-screen name is you (binary VS screens)

Does not invent winners. Settlement still needs both sides or no-show rules.
"""
from __future__ import annotations

from typing import Any, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gaming.src.backend.services.game_catalog import (
    binary_claim_to_home_away,
    display_name,
    is_binary_outcome,
    parse_result_caption,
    report_caption_help_html,
)


def game_id_of(ch: dict) -> str:
    return str(ch.get("game") or ch.get("game_type") or "")


def my_side(ch: dict, profile_id: str) -> Optional[str]:
    if profile_id == ch.get("creator_id"):
        return ch.get("creator_side")
    if profile_id == ch.get("opponent_id"):
        return ch.get("opponent_side")
    return None


def is_creator(ch: dict, profile_id: str) -> bool:
    return profile_id == ch.get("creator_id")


def my_ingame_name(ch: dict, profile_id: str) -> str:
    """In-game display name stored on the match (console_id fields reused)."""
    if profile_id == ch.get("creator_id"):
        return str(ch.get("creator_console_id") or "").strip()
    if profile_id == ch.get("opponent_id"):
        return str(ch.get("opponent_console_id") or "").strip()
    return ""


def missing_for_ruling(
    ch: dict,
    profile_id: str,
    *,
    has_photo: bool,
    home: Optional[int] = None,
    away: Optional[int] = None,
    binary_won: Optional[bool] = None,
    screen_name: str = "",
) -> list[str]:
    """Ordered list of missing pieces: photo | name | side | outcome.

    Binary VS games (8 Ball Pool etc.) **require** an on-screen name so we can
    tell Finch from Emmanuella without operator help.
    """
    gid = game_id_of(ch)
    binary = is_binary_outcome(gid)
    miss: list[str] = []
    if not has_photo:
        miss.append("photo")
    # Identity first — who is this Telegram user in the game?
    name = (screen_name or my_ingame_name(ch, profile_id) or "").strip()
    if binary and not name:
        miss.append("name")
    side = my_side(ch, profile_id)
    # Scoreline: side required. Binary: side optional if we have name + W/L
    if not binary and not side:
        miss.append("side")
    has_outcome = (home is not None and away is not None) or binary_won is not None
    if not has_outcome:
        miss.append("outcome")
    return miss


def intro_html(ch: dict) -> str:
    gid = game_id_of(ch)
    name = display_name(gid) if gid else "this match"
    return (
        f"⚖️ <b>Fair report for {name}</b>\n\n"
        f"I'll ask only what I need so we know <b>who is who</b> and <b>who won</b>.\n"
        f"No guesswork — you confirm.\n\n"
        f"{report_caption_help_html(gid)}"
    )


def ask_side_html(ch: dict) -> str:
    gid = game_id_of(ch)
    binary = is_binary_outcome(gid)
    if binary:
        return (
            "⚖️ <b>Who are you in this match?</b>\n\n"
            "Pick the side you played as (helps us map the result correctly):\n"
            "• <b>HOME</b> — left / home on the scoreboard if shown\n"
            "• <b>AWAY</b> — right / away\n\n"
            "If the game has no home/away (e.g. 8 Ball), pick either — "
            "we'll still ask if <b>you</b> won or lost."
        )
    return (
        "⚖️ <b>Which side were you?</b>\n\n"
        "For a fair scoreline we need this:\n"
        "• <b>HOME</b> — you were the home team\n"
        "• <b>AWAY</b> — you were the away team\n\n"
        "This must match what you agreed before the match."
    )


def side_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🏠 I was HOME", callback_data=f"ui:reportask:side:{challenge_id}:home"
        ),
        InlineKeyboardButton(
            text="✈️ I was AWAY", callback_data=f"ui:reportask:side:{challenge_id}:away"
        ),
    )
    b.row(
        InlineKeyboardButton(text="❌ Cancel report", callback_data="menu:main"),
    )
    return b.as_markup()


def ask_name_html(ch: dict) -> str:
    gid = game_id_of(ch)
    gname = display_name(gid) if gid else "this game"
    return (
        f"⚖️ <b>Who are you in {gname}?</b>\n\n"
        f"Type your <b>exact in-game name</b> as it appears on the result screen.\n\n"
        f"Example from 8 Ball Pool: if the screen shows <b>Finch</b> vs "
        f"<b>Emmanuella</b>, type <code>Finch</code> or "
        f"<code>Emmanuella</code> — whichever is <b>you</b>.\n\n"
        f"This stops mix-ups for random players. Spelling must match the photo."
    )


def ask_outcome_html(ch: dict, profile_id: str) -> str:
    gid = game_id_of(ch)
    name = display_name(gid) if gid else "this game"
    side = my_side(ch, profile_id) or "?"
    ign = my_ingame_name(ch, profile_id) or "?"
    if is_binary_outcome(gid):
        return (
            f"⚖️ <b>Who won — {name}?</b>\n\n"
            f"You are: <b>{ign}</b>"
            + (f" · side <b>{side.upper()}</b>" if side != "?" else "")
            + "\n\n"
            f"Look at the final screen (e.g. gold <b>Winner</b> over one avatar).\n"
            f"Did <b>you</b> win this match?\n\n"
            f"Your opponent will answer too. Both must agree for auto-payout."
        )
    return (
        f"⚖️ <b>Final score — {name}?</b>\n\n"
        f"Your side: <b>{side.upper()}</b>\n\n"
        f"Type the full-time score as <b>home-away</b>, e.g.\n"
        f"<code>5-3</code> or <code>2-1</code>\n\n"
        f"(Home first, then away — same as the sides you picked.)"
    )


def outcome_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✅ I won (W)", callback_data=f"ui:reportask:out:{challenge_id}:W"
        ),
        InlineKeyboardButton(
            text="❌ I lost (L)", callback_data=f"ui:reportask:out:{challenge_id}:L"
        ),
    )
    b.row(
        InlineKeyboardButton(text="❌ Cancel report", callback_data="menu:main"),
    )
    return b.as_markup()


def ask_who_html(names: list[str]) -> str:
    a, b = (names + ["Player A", "Player B"])[:2]
    return (
        "⚖️ <b>Which name on the screenshot is you?</b>\n\n"
        f"We see: <b>{a}</b> vs <b>{b}</b>\n\n"
        "Tap your name so we don't mix players up."
    )


def who_keyboard(challenge_id: str, names: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, n in enumerate(names[:2]):
        label = (n or f"Player {i+1}")[:28]
        b.row(
            InlineKeyboardButton(
                text=f"👤 {label}",
                callback_data=f"ui:reportask:who:{challenge_id}:{i}",
            )
        )
    b.row(
        InlineKeyboardButton(
            text="⏭ Skip — I already said W/L",
            callback_data=f"ui:reportask:who:{challenge_id}:skip",
        )
    )
    return b.as_markup()


def confirm_html(
    ch: dict,
    profile_id: str,
    *,
    home: int,
    away: int,
    binary_won: Optional[bool],
    screen_name: str = "",
) -> str:
    gid = game_id_of(ch)
    name = display_name(gid) if gid else "match"
    side = my_side(ch, profile_id) or "?"
    ign = (screen_name or my_ingame_name(ch, profile_id) or "—").strip()
    if binary_won is not None:
        claim = "WON" if binary_won else "LOST"
        return (
            f"📋 <b>Confirm your report — {name}</b>\n\n"
            f"• In-game name: <b>{ign}</b>\n"
            f"• Side: <b>{side.upper()}</b>\n"
            f"• You claim: <b>{claim}</b>\n"
            f"• Settlement map: <code>{home}-{away}</code>\n\n"
            f"Photo attached. We only auto-pay if your opponent’s report "
            f"<b>agrees</b> (they lost if you won, and different in-game names).\n\n"
            f"Tap <b>Submit report</b> only if this is correct."
        )
    return (
        f"📋 <b>Confirm your report — {name}</b>\n\n"
        f"• Side: <b>{side.upper()}</b>\n"
        f"• Scoreline: <code>{home}-{away}</code> (home-away)\n\n"
        f"Photo attached. Opponent should report the <b>same</b> scoreline."
    )


def names_conflict(ch: dict) -> bool:
    """Both players claimed the same in-game name."""
    c = (ch.get("creator_console_id") or "").strip().lower()
    o = (ch.get("opponent_console_id") or "").strip().lower()
    return bool(c and o and c == o)


def binary_win_claims(ch: dict) -> tuple[Optional[bool], Optional[bool]]:
    """Infer W/L claims from stored home-away (1-0 / 0-1) + sides.

    Returns (creator_won, opponent_won) or None if unknown.
    """
    def _won(home: Any, away: Any, side: Optional[str], as_creator: bool) -> Optional[bool]:
        if home is None or away is None:
            return None
        try:
            h, a = int(home), int(away)
        except (TypeError, ValueError):
            return None
        if h == a:
            return None
        home_wins = h > a
        if side == "home":
            return home_wins
        if side == "away":
            return not home_wins
        # default: creator = home perspective
        return home_wins if as_creator else not home_wins

    c = _won(
        ch.get("creator_reported_home"),
        ch.get("creator_reported_away"),
        ch.get("creator_side"),
        True,
    )
    o = _won(
        ch.get("opponent_reported_home"),
        ch.get("opponent_reported_away"),
        ch.get("opponent_side"),
        False,
    )
    return c, o


def confirm_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✅ Submit report",
            callback_data=f"ui:reportask:go:{challenge_id}",
        ),
        InlineKeyboardButton(
            text="✏️ Fix",
            callback_data=f"ui:report:{challenge_id}",
        ),
    )
    return b.as_markup()


def parse_score_message(text: str) -> tuple[Optional[int], Optional[int]]:
    home, away, err = parse_result_caption("EAFC", text or "")  # scoreline parser
    if home is not None and away is not None:
        return home, away
    return None, None


def resolve_home_away(
    ch: dict,
    profile_id: str,
    *,
    binary_won: Optional[bool],
    home: Optional[int],
    away: Optional[int],
) -> tuple[int, int]:
    if home is not None and away is not None:
        return int(home), int(away)
    if binary_won is None:
        raise ValueError("Need W/L or a scoreline")
    return binary_claim_to_home_away(
        binary_won,
        side=my_side(ch, profile_id),
        is_creator=is_creator(ch, profile_id),
    )
