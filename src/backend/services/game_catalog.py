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


def proof_instructions(game_id: str) -> str:
    """Short HTML-safe copy for after lock / submit."""
    g = get_game(game_id)
    if not g:
        return "Play the match, then send the final score screenshot."
    name = g.get("display_name") or game_id
    result = g.get("result_screen") or "winner / final score"
    cat = g.get("category")
    if cat == "imessage":
        return (
            f"Play <b>{name}</b> in <b>iMessage</b>, "
            f"then send the <b>final screen</b> here.\n"
            f"What we need: {result}."
        )
    if cat == "mobile":
        return (
            f"Play <b>{name}</b> on your <b>phone</b>, "
            f"then send the <b>final result screen</b> here.\n"
            f"What we need: {result}."
        )
    return (
        f"Play <b>{name}</b>, then submit the "
        f"<b>final score screen</b> photo."
    )
