"""Runtime house match schedule.

The admin desk writes this (via the House API); the house session reads it on
every iteration. Stored next to matches.json so the API process and the
session process share it without any IPC.

Semantics:
  enabled      — session keeps playing (false pauses the schedule; Play now
                 from the arena still works on demand).
  cadence_sec  — seconds the session waits AFTER a settled game before opening
                 the next one. 1800 = 48 games/day, 900 = 96/day, 600 = 144/day.
  burst_games  — play N games back-to-back (ignoring cadence), decrementing
                 this counter each game, then resume cadence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from gaming.src.stack.agentic.store import load_json, save_json

SCHEDULE_FILE = "house_schedule.json"

# Cadence presets the admin desk offers. Key = label, value = seconds.
PRESETS: dict[str, int] = {
    "48/day (every 30m)": 1800,
    "96/day (every 15m)": 900,
    "144/day (every 10m)": 600,
    "continuous": 0,
}

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "cadence_sec": 0,  # continuous — games flow back-to-back
    "burst_games": 0,  # 0 = no burst
    "set_by": "system",
    "updated_at": None,
    "last_settled_at": None,  # session writes after each game (status endpoint uses it)
    "last_match_id": None,
}


def read_schedule() -> dict[str, Any]:
    raw = load_json(SCHEDULE_FILE, {}) or {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in raw.items() if k in DEFAULTS})
    return out


def write_schedule(*, set_by: str = "admin", **changes: Any) -> dict[str, Any]:
    cur = read_schedule()
    for k, v in changes.items():
        if k in DEFAULTS:
            cur[k] = v
    cur["set_by"] = set_by
    cur["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_json(SCHEDULE_FILE, cur)
    return cur


def clamp_cadence(sec: Any) -> int:
    try:
        n = int(float(sec))
    except (TypeError, ValueError):
        n = DEFAULTS["cadence_sec"]
    return max(0, min(n, 86400))


def clamp_burst(n: Any) -> int:
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        v = 0
    return max(0, min(v, 1000))
