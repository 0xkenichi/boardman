"""Phase stream builder — turns the spatial event log into renderable phases.

Ratified contract (Evans / DEvansData board target, roadmap P1):

    Phase = {
        t: float,          # match clock, minutes (minute + sub-minute fraction)
        ball: {x, y, z},   # metres — x = length, y = width, z = height
        players: [...],    # 22 tokens (the starting XIs): {id, side, x, y, facing}
        action?: "pass" | "carry" | "shot" | "cross",
        note?: string,     # human readable, e.g. "Calafiori carries"
    }

Like the spatial overlay it is a *pure* deterministic fold: every placement
derives from a separate hash stream keyed on (match_id, phase index, field)
and never consumes the match RNG, so the same match always yields the same
phases and outcomes are untouched. Additive extras per phase (`minute`,
`type`, `event`) help a renderer replay a specific event.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from gaming.src.stack.agentic.games.football_managers.club_store import _formation_slots
from gaming.src.stack.agentic.games.football_managers.match_engine import (
    PITCH_LENGTH,
    PITCH_WIDTH,
)


def _unit(match_id: str, i: int, key: str) -> float:
    h = hashlib.sha256(f"afm-phase:{match_id}:{i}:{key}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / (2**32)


# Base position per slot group, in metres (home attacks +x, so x is measured
# from the home goal line). Lateral positions are a fraction of pitch width
# (0 = one touchline, 1 = the other). Duplicate slots spread around the base.
_SLOT_X: dict[str, float] = {
    "GK": 5.0, "RB": 16.0, "LB": 16.0, "CB": 12.0,
    "CDM": 24.0, "CM": 30.0, "CAM": 36.0,
    "RW": 32.0, "LW": 32.0, "ST": 44.0,
}
_SLOT_Y: dict[str, float] = {
    "GK": 0.5, "RB": 0.86, "LB": 0.14, "CB": 0.5,
    "CDM": 0.5, "CM": 0.5, "CAM": 0.5,
    "RW": 0.88, "LW": 0.12, "ST": 0.5,
}
_SLOT_SPREAD: dict[str, float] = {
    # duplicate slots spread around the base lateral position; e.g. two CBs
    # at ±0.15 → 0.35 / 0.65 across the width, two STs at ±0.20 → 0.30 / 0.70
    "GK": 0.0, "CB": 0.30, "CDM": 0.28, "CM": 0.24, "ST": 0.40,
}
_DEF_X = 26.0
_DEF_Y = 0.5
_DEF_SPREAD = 0.24

# Event type → board action (anything unmapped gets no `action` key).
_ACTION: dict[str, str] = {
    "possession": "carry",
    "pass": "pass",
    "shot": "shot",
    "goal": "shot",
    "penalty": "shot",
    "corner": "cross",
    "cross": "cross",
}


def _xi_base_positions(xi: list[str], formation: str, side: str) -> list[dict[str, Any]]:
    """Deterministic in-formation anchor per starter, in XI order.

    XI order follows slot order (`decide._pick_xi` fills slots in order); a
    malformed XI is padded defensively so positioning never crashes.
    """
    slots = _formation_slots(formation or "4-3-3")
    if len(slots) != len(xi):
        slots = ["MID"] * len(xi)
    counts = Counter(slots)
    seen: Counter[str] = Counter()
    out: list[dict[str, Any]] = []
    for idx, pid in enumerate(xi):
        slot = slots[idx]
        k = seen[slot]
        seen[slot] += 1
        n = counts.get(slot, 1)
        spread = _SLOT_SPREAD.get(slot, _DEF_SPREAD)
        base_x = _SLOT_X.get(slot, _DEF_X)
        y_frac = _SLOT_Y.get(slot, _DEF_Y) + (k - (n - 1) / 2.0) * spread
        if side == "away":
            base_x = PITCH_LENGTH - base_x
            y_frac = 1.0 - y_frac
        out.append({
            "id": pid,
            "side": side,
            "slot": slot,
            "keeper": slot == "GK",
            "base_x": base_x,
            "base_y": y_frac * PITCH_WIDTH,
        })
    return out


def build_phase_stream(
    match_id: str,
    feed: list[dict[str, Any]],
    home_xi: list[str],
    away_xi: list[str],
    home_formation: str,
    away_formation: str,
) -> list[dict[str, Any]]:
    """One phase per spatial event, in feed order.

    `t` is strictly increasing (minute + index-based fraction), `players`
    lists both starting XIs with deterministic in-formation positions, the
    event's actor snaps to the ball, and the whole shape leans toward play so
    the board reads like football, not static dots.
    """
    home_base = _xi_base_positions(home_xi, home_formation, "home")
    away_base = _xi_base_positions(away_xi, away_formation, "away")
    squad = home_base + away_base
    n = max(len(feed), 1)
    phases: list[dict[str, Any]] = []
    for i, ev in enumerate(feed):
        ex = float(ev.get("x", PITCH_LENGTH / 2.0))
        ey = float(ev.get("y", PITCH_WIDTH / 2.0))
        actor = ev.get("actor_id")
        ev_facing = float(ev.get("facing", 0.0))
        t = round(float(ev.get("minute", 0)) + (i / n) * 0.9, 4)

        players: list[dict[str, Any]] = []
        for p in squad:
            pid = p["id"]
            if p["keeper"]:
                rx, ry = 0.6, 0.6
            else:
                rx, ry = 8.0, 6.0
            x = p["base_x"] + (_unit(match_id, i, f"{pid}:x") - 0.5) * rx
            y = p["base_y"] + (_unit(match_id, i, f"{pid}:y") - 0.5) * ry
            if not p["keeper"]:
                # lean toward the ball so the shape follows play
                x += (ex - x) * 0.10
                y += (ey - y) * 0.08
            if pid == actor:
                # the actor sits exactly on the ball — a goal on the line (x=100)
                # must not be pushed a metre off by the formation margin
                x = round(min(max(ex, 0.0), PITCH_LENGTH), 1)
                y = round(min(max(ey, 0.0), PITCH_WIDTH), 1)
            else:
                x = round(min(max(x, 1.0), PITCH_LENGTH - 1.0), 1)
                y = round(min(max(y, 1.0), PITCH_WIDTH - 1.0), 1)
            if pid == actor:
                facing = round(ev_facing, 1)
            else:
                base_f = 90.0 if p["side"] == "home" else 270.0
                facing = round(
                    (base_f + (_unit(match_id, i, f"{pid}:f") - 0.5) * 30.0) % 360.0, 1
                )
            players.append({"id": pid, "side": p["side"], "x": x, "y": y, "facing": facing})

        phase: dict[str, Any] = {
            "t": t,
            "minute": int(ev.get("minute") or 0),
            "type": ev.get("type"),
            "event": i,
            "ball": {
                "x": round(min(max(ex, 0.0), PITCH_LENGTH), 1),
                "y": round(min(max(ey, 0.0), PITCH_WIDTH), 1),
                "z": round(float(ev.get("z", 0.0)), 2),
            },
            "players": players,
        }
        action = _ACTION.get(ev.get("type"))
        if action:
            phase["action"] = action
        note = ev.get("text")
        if note:
            phase["note"] = str(note)
        phases.append(phase)
    return phases