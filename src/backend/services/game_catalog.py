"""
Game catalog loader — console + iMessage (+ future mobile).

Reads config/games/*.yaml. Safe if PyYAML missing (built-in seed).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_GAMES_DIR = Path(__file__).resolve().parents[3] / "config" / "games"

# Fallback if YAML files missing
_SEED: list[dict[str, Any]] = [
    {
        "game_id": "EAFC",
        "display_name": "EA FC",
        "category": "console",
        "enabled": True,
        "outcome_type": "scoreline",
        "result_screen": "Full-time scoreline",
        "ai_hints": ["EA FC FT screen", "home away goals"],
        "duration_hint_min": 90,
        "emoji": "⚽",
    },
    {
        "game_id": "NBA2K",
        "display_name": "NBA 2K",
        "category": "console",
        "enabled": True,
        "outcome_type": "scoreline",
        "result_screen": "Final box score",
        "ai_hints": ["NBA 2K final score"],
        "duration_hint_min": 60,
        "emoji": "🏀",
    },
    {
        "game_id": "imessage.8_ball",
        "display_name": "8 Ball",
        "category": "imessage",
        "enabled": True,
        "outcome_type": "binary_winner",
        "result_screen": "You Win / You Lose",
        "ai_hints": ["GamePigeon 8 Ball", "You Win", "You Lose"],
        "duration_hint_min": 15,
        "emoji": "🎱",
    },
    {
        "game_id": "mobile.8_ball_pool",
        "display_name": "8 Ball Pool",
        "category": "mobile",
        "enabled": True,
        "outcome_type": "binary_winner",
        "result_screen": "You Win / You Lose after 8-ball (1v1)",
        "ai_hints": [
            "Miniclip 8 Ball Pool final result",
            "You Win / You Lose / Winner banner",
            "Not GamePigeon iMessage",
        ],
        "duration_hint_min": 10,
        "emoji": "🎱",
    },
]


def _load_yaml_file(path: Path) -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError:
        logger.warning("[GameCatalog] PyYAML not installed")
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[GameCatalog] failed to read %s: %s", path, exc)
        return []
    category = raw.get("category") or path.stem
    games = raw.get("games") or []
    out: list[dict[str, Any]] = []
    for g in games:
        if not isinstance(g, dict) or not g.get("game_id"):
            continue
        row = dict(g)
        row.setdefault("category", category)
        row.setdefault("enabled", True)
        row.setdefault("outcome_type", "binary_winner")
        row.setdefault("ai_hints", [])
        out.append(row)
    return out


@lru_cache(maxsize=1)
def load_all_games() -> tuple[dict[str, Any], ...]:
    """All games from config/games + console defaults."""
    by_id: dict[str, dict[str, Any]] = {}
    # Built-in console always present
    for g in _SEED:
        by_id[g["game_id"]] = dict(g)

    if _GAMES_DIR.is_dir():
        for path in sorted(_GAMES_DIR.glob("*.yaml")):
            for g in _load_yaml_file(path):
                by_id[g["game_id"]] = g
    else:
        logger.warning("[GameCatalog] missing dir %s", _GAMES_DIR)

    # Console aliases used by existing bot
    if "EAFC" not in by_id:
        by_id["EAFC"] = dict(_SEED[0])
    if "NBA2K" not in by_id:
        by_id["NBA2K"] = dict(_SEED[1])
    if "Other" not in by_id:
        by_id["Other"] = {
            "game_id": "Other",
            "display_name": "Other",
            "category": "console",
            "enabled": True,
            "outcome_type": "scoreline",
            "ai_hints": ["final score screen"],
            "emoji": "🎮",
        }

    return tuple(by_id[k] for k in sorted(by_id.keys()))


def reload_catalog() -> None:
    load_all_games.cache_clear()


def get_game(game_id: str) -> Optional[dict[str, Any]]:
    if not game_id:
        return None
    gid = str(game_id).strip()
    for g in load_all_games():
        if g["game_id"] == gid or g["game_id"].lower() == gid.lower():
            return dict(g)
    return None


def list_games(
    *,
    category: Optional[str] = None,
    enabled_only: bool = True,
) -> list[dict[str, Any]]:
    out = []
    for g in load_all_games():
        if enabled_only and not g.get("enabled", True):
            continue
        if category and g.get("category") != category:
            continue
        out.append(dict(g))
    return out


def list_categories(*, enabled_only: bool = True) -> list[dict[str, str]]:
    """Unique categories with display labels."""
    labels = {
        "imessage": "📱 iMessage",
        "console": "🎮 Console",
        "mobile": "📲 Mobile",
    }
    seen: list[str] = []
    for g in list_games(enabled_only=enabled_only):
        cat = g.get("category") or "other"
        if cat not in seen:
            seen.append(cat)
    # Product order: iMessage → Mobile (FC Mobile focus) → Console
    order = ["imessage", "mobile", "console"]
    seen.sort(key=lambda c: order.index(c) if c in order else 99)
    return [{"id": c, "label": labels.get(c, c.title())} for c in seen]


def display_name(game_id: str) -> str:
    g = get_game(game_id)
    if not g:
        return game_id or "Game"
    emoji = g.get("emoji") or ""
    name = g.get("display_name") or g["game_id"]
    cat = g.get("category")
    if cat == "imessage" and "iMessage" not in name:
        return f"{emoji} {name} (iMessage)".strip()
    if cat == "mobile" and "Mobile" not in name and not name.endswith("Mobile"):
        return f"{emoji} {name} (Mobile)".strip()
    return f"{emoji} {name}".strip()


def is_imessage(game_id: str) -> bool:
    g = get_game(game_id)
    return bool(g and g.get("category") == "imessage") or str(game_id).startswith("imessage.")


def is_mobile(game_id: str) -> bool:
    g = get_game(game_id)
    return bool(g and g.get("category") == "mobile") or str(game_id).startswith("mobile.")


def outcome_type(game_id: str) -> str:
    g = get_game(game_id) or {}
    return str(g.get("outcome_type") or "scoreline")


def is_binary_outcome(game_id: str) -> bool:
    """Win/lose games (8 Ball, Free Fire 1v1) — not football-style scorelines."""
    return outcome_type(game_id).lower() in (
        "binary_winner",
        "binary",
        "winner",
        "win_lose",
    )


def ai_context_for_game(game_id: str) -> dict[str, Any]:
    """Hints injected into vision prompts."""
    g = get_game(game_id) or {}
    return {
        "game_id": g.get("game_id") or game_id,
        "display_name": g.get("display_name") or game_id,
        "category": g.get("category"),
        "outcome_type": g.get("outcome_type") or "scoreline",
        "result_screen": g.get("result_screen") or "",
        "ai_hints": list(g.get("ai_hints") or []),
    }


def binary_claim_to_home_away(
    won: bool, *, side: Optional[str], is_creator: bool
) -> tuple[int, int]:
    """Map reporter W/L to home-away scoreline (1-0 / 0-1)."""
    if side == "home":
        return (1, 0) if won else (0, 1)
    if side == "away":
        return (0, 1) if won else (1, 0)
    # No side declared: creator = home by convention
    if is_creator:
        return (1, 0) if won else (0, 1)
    return (0, 1) if won else (1, 0)


def parse_result_caption(
    game_id: str,
    caption: str,
    *,
    side: Optional[str] = None,
    is_creator: bool = True,
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Parse user caption for a game.

    Returns (home, away, err). err is human message if unusable.
    For binary games: W/L/win/lose (also win/lose phrases).
    For scoreline: 5-3 or 5:3.
    """
    import re

    text = (caption or "").strip()
    binary = is_binary_outcome(game_id)

    # Always accept explicit scoreline if present
    m = re.search(r"(?i)(?:h\s*[-–]\s*a\s+)?(\d+)\s*[-:–]\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2)), None

    # Binary claims
    low = text.lower()
    won: Optional[bool] = None
    if re.fullmatch(r"[wW]|win|won|victory|i\s*won|you\s*win", text.strip()):
        won = True
    elif re.fullmatch(r"[lL]|lose|loss|lost|defeat|i\s*lost|you\s*lose", text.strip()):
        won = False
    elif re.search(r"\b(i\s+won|we\s+won|victory|winner)\b", low):
        won = True
    elif re.search(r"\b(i\s+lost|we\s+lost|defeat|loser)\b", low):
        won = False
    elif low in ("1", "1-0", "1:0") and binary:
        won = True
    elif low in ("0", "0-1", "0:1") and binary:
        won = False

    if won is not None:
        h, a = binary_claim_to_home_away(won, side=side, is_creator=is_creator)
        return h, a, None

    if binary:
        if not text:
            return None, None, None  # allow AI-only path
        return (
            None,
            None,
            "Caption this photo <code>W</code> (you won) or <code>L</code> (you lost). "
            "Or send the photo alone and we will try AI.",
        )
    if not text:
        return None, None, None
    return (
        None,
        None,
        "Caption the photo with the score like <code>5-3</code> (home-away).",
    )


def _short_result_screen(game_id: str, max_len: int = 120) -> str:
    g = get_game(game_id) or {}
    raw = " ".join(str(g.get("result_screen") or "final result screen").split())
    if len(raw) > max_len:
        return raw[: max_len - 1].rstrip() + "…"
    return raw


def how_to_report_short(game_id: str) -> str:
    """Friendly one-block instructions for match status / after lock / side pick."""
    g = get_game(game_id)
    name = (g or {}).get("display_name") or "your game"
    emoji = (g or {}).get("emoji") or "🎮"
    binary = is_binary_outcome(game_id)
    cat = (g or {}).get("category") or ""
    where = (
        "on your phone"
        if cat == "mobile"
        else ("in iMessage" if cat == "imessage" else "on your console")
    )
    need = _short_result_screen(game_id, 90)

    if binary:
        return (
            f"{emoji} <b>How to report — {name}</b>\n\n"
            f"This game is <b>win or lose</b> (no football-style score).\n\n"
            f"1. Finish the match <b>{where}</b>\n"
            f"2. Open the <b>end screen</b>: <i>{need}</i>\n"
            f"3. Tap <b>Report result</b> and send that photo\n"
            f"4. The bot will ask you to type your <b>exact in-game name</b> "
            f"(e.g. <code>Finch</code>) so we know who is who\n"
            f"5. Then tap <b>I won</b> or <b>I lost</b>\n\n"
            f"Opponent does the same with <b>their</b> name. "
            f"Auto-pay only if reports agree."
        )
    return (
        f"{emoji} <b>How to report — {name}</b>\n\n"
        f"This game uses a <b>scoreline</b> (home–away).\n\n"
        f"1. Finish the match <b>{where}</b>\n"
        f"2. Open the <b>full-time / final score</b> screen: <i>{need}</i>\n"
        f"3. Tap <b>Submit result</b> and send it as a photo\n"
        f"4. Caption the score like <code>5-3</code> or <code>2-1</code>\n"
        f"   (home first, then away — same as the sides you picked)\n\n"
        f"Both players report the same scoreline when they can."
    )


def report_caption_help_html(game_id: str) -> str:
    """Full HTML guide when user taps Submit result — kind and game-specific."""
    g = get_game(game_id)
    name = (g or {}).get("display_name") or game_id or "this game"
    emoji = (g or {}).get("emoji") or "📸"
    result = _short_result_screen(game_id, 140)
    binary = is_binary_outcome(game_id)
    cat = (g or {}).get("category") or ""

    where = (
        "your phone"
        if cat == "mobile"
        else ("iMessage" if cat == "imessage" else "your console / TV")
    )

    lines = [
        f"{emoji} <b>Submit result — {name}</b>",
        "",
        "We've got you — just send the right final screen for <b>this</b> game.",
        "",
        f"<b>What to photograph</b>",
        f"• {result}",
        f"• Take it on <b>{where}</b> right after the match ends",
        "• Avoid mid-game, lobby, or coin/XP popups only",
        "",
        "<b>How to send it</b>",
        "1. Tap 📎 → Photo (or File)",
        "2. Pick the screenshot",
    ]
    if binary:
        lines += [
            "3. Send the photo (caption optional for now)",
            "4. We'll ask for your <b>exact in-game name</b> on that screen "
            "(e.g. Finch) — this is how we know who is who",
            "5. Then confirm <b>I won</b> or <b>I lost</b>",
            "",
            f"<i>{name}</i> does not use football scores — only winner + your name.",
        ]
    else:
        lines += [
            "3. In the caption, type the <b>home–away</b> score:",
            "   • e.g. <code>5-3</code> or <code>2-1</code>",
            "",
            "Home / Away = the sides you chose on this match (HOME / AWAY buttons).",
            "",
            f"<i>{name}</i> settles from the full-time scoreline.",
        ]
    lines += [
        "",
        "4. Send — we'll save it and notify your opponent.",
        "",
        "Tip: if captioning is awkward, send the photo alone and we can try AI — "
        "but a short caption is the most reliable.",
        "",
        "Ready when you are — send the image now 👇",
    ]
    return "\n".join(lines)


def proof_instructions(game_id: str) -> str:
    """Short HTML-safe copy for after lock / submit (uses how_to_report_short)."""
    return how_to_report_short(game_id)
