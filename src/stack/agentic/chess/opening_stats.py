"""
Opening-line learning — per-agent W/L/D memory for book lines.

After each settled match, the game's first plies are matched against each
agent's authored book lines; the result is recorded. Book picks then weight
lines by how well they have scored and dampen the line the agent used in
its previous game — the same opener stops repeating every table.

Store: data/agentic/opening_stats.json (same file-store convention as the
rest of the agentic stack).
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json, save_json

STATS_FILE = "opening_stats.json"
# How many opening plies identify "the line a game followed"
LINE_DEPTH = 8
MAX_LINES_PER_AGENT = 200


def _now() -> float:
    return time.time()


def _load() -> dict[str, Any]:
    return load_json(STATS_FILE, {}) or {}


def _save(data: dict[str, Any]) -> None:
    save_json(STATS_FILE, data)


def _key(agent_id: str, side: str, line_key: str) -> str:
    return f"{agent_id}|{side}|{line_key}"


def line_key_for(sans: list[str]) -> str:
    """Position-sequence key for the first LINE_DEPTH plies."""
    return " ".join(sans[:LINE_DEPTH])


def record_result(
    *,
    agent_a_id: str,
    agent_b_id: str,
    sans: list[str],
    winner_side: Optional[str],  # "a" | "b" | None (draw)
    match_id: str = "",
) -> None:
    """Record W/L/D for the opening line each side actually played."""
    if not sans:
        return
    key = line_key_for(sans)
    data = _load()
    now = _now()
    for agent_id, side in ((agent_a_id, "a"), (agent_b_id, "b")):
        bucket = data.setdefault(agent_id, {})
        rec = bucket.setdefault(
            key,
            {"wins": 0, "losses": 0, "draws": 0, "games": 0, "last_used_at": 0, "last_match_id": ""},
        )
        rec["games"] = int(rec.get("games", 0)) + 1
        if winner_side is None:
            rec["draws"] = int(rec.get("draws", 0)) + 1
        elif side == winner_side:
            rec["wins"] = int(rec.get("wins", 0)) + 1
        else:
            rec["losses"] = int(rec.get("losses", 0)) + 1
        rec["last_used_at"] = now
        rec["last_match_id"] = match_id
        bucket[key] = rec
    # cap memory: drop coldest lines beyond the cap
    for agent_id, bucket in list(data.items()):
        if len(bucket) > MAX_LINES_PER_AGENT:
            coldest = sorted(bucket.items(), key=lambda kv: kv[1].get("last_used_at", 0))
            for k, _ in coldest[: len(bucket) - MAX_LINES_PER_AGENT]:
                bucket.pop(k, None)
    _save(data)


def line_weight(agent_id: str, sans_prefix: list[str], san: str) -> float:
    """
    Learning weight for choosing `san` at a book position whose game-so-far
    is `sans_prefix`. Result-scored lines rank higher; the line used in the
    agent's previous game is damped so openers rotate.
    """
    data = _load()
    bucket = data.get(agent_id) or {}
    prefix = " ".join((sans_prefix + [san])[:LINE_DEPTH])
    rec = bucket.get(prefix)
    if not rec:
        return 1.0
    w = 1.0 + 0.6 * int(rec.get("wins", 0)) + 0.2 * int(rec.get("draws", 0))
    w -= 0.3 * int(rec.get("losses", 0))
    # recent-use damping (previous game for this agent)
    last_used = float(rec.get("last_used_at", 0) or 0)
    if last_used and _now() - last_used < 6 * 3600:
        w *= 0.35
    return max(0.2, w)


def summary(agent_id: str) -> dict[str, Any]:
    bucket = _load().get(agent_id) or {}
    best = sorted(
        bucket.items(),
        key=lambda kv: (kv[1].get("wins", 0), -kv[1].get("losses", 0)),
        reverse=True,
    )[:5]
    return {
        "lines": len(bucket),
        "top": [{"line": k, **v} for k, v in best],
    }
