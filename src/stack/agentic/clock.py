"""
Chess clocks + time-control classes for agent matches.

Games are not endless: each side has a budget of wall-clock thinking time.
Agents declare preferred controls at deploy; a match only forms when both
accept a control (or the host forces one both list).

Reasoning delay is *not* uniform: each mind has think_ms_min/max so two
agents feel like different people even when both use Stockfish underneath.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# id → {base_ms, increment_ms, label, class}
TIME_CONTROLS: dict[str, dict[str, Any]] = {
    "bullet_1|0": {
        "id": "bullet_1|0",
        "label": "1+0 Bullet",
        "class": "bullet",
        "base_ms": 60_000,
        "increment_ms": 0,
        "max_game_ms": 120_000,
    },
    "blitz_3|0": {
        "id": "blitz_3|0",
        "label": "3+0 Blitz",
        "class": "blitz",
        "base_ms": 180_000,
        "increment_ms": 0,
        "max_game_ms": 360_000,
    },
    "blitz_3|2": {
        "id": "blitz_3|2",
        "label": "3+2 Blitz",
        "class": "blitz",
        "base_ms": 180_000,
        "increment_ms": 2_000,
        "max_game_ms": 480_000,
    },
    "blitz_5|0": {
        "id": "blitz_5|0",
        "label": "5+0 Blitz",
        "class": "blitz",
        "base_ms": 300_000,
        "increment_ms": 0,
        "max_game_ms": 600_000,
    },
    "rapid_10|0": {
        "id": "rapid_10|0",
        "label": "10+0 Rapid",
        "class": "rapid",
        "base_ms": 600_000,
        "increment_ms": 0,
        "max_game_ms": 1_200_000,
    },
}


def list_time_controls() -> list[dict[str, Any]]:
    return list(TIME_CONTROLS.values())


def negotiate_time_control(
    prefs_a: list[str],
    prefs_b: list[str],
    *,
    host_preference: Optional[str] = None,
) -> str:
    """
    Pick a control both agents accept.
    Prefer host_preference if in intersection; else first of A∩B; else blitz_3|2.
    """
    sa, sb = set(prefs_a or []), set(prefs_b or [])
    inter = [x for x in (prefs_a or []) if x in sb]  # preserve A order
    if host_preference and host_preference in sa and host_preference in sb:
        return host_preference
    if inter:
        return inter[0]
    # fallback: any shared class — else default blitz
    return "blitz_3|2"


@dataclass
class SideClock:
    remaining_ms: int
    last_started: Optional[float] = None  # monotonic

    def start(self) -> None:
        self.last_started = time.monotonic()

    def stop(self) -> int:
        """Stop clock; return ms spent this move."""
        if self.last_started is None:
            return 0
        spent = int((time.monotonic() - self.last_started) * 1000)
        self.remaining_ms = max(0, self.remaining_ms - spent)
        self.last_started = None
        return spent

    def flag(self) -> bool:
        return self.remaining_ms <= 0

    def to_dict(self) -> dict[str, Any]:
        return {"remaining_ms": self.remaining_ms, "flag": self.flag()}


@dataclass
class MatchClock:
    control_id: str
    white: SideClock
    black: SideClock
    increment_ms: int = 0
    move_times: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_control(cls, control_id: str) -> "MatchClock":
        tc = TIME_CONTROLS.get(control_id) or TIME_CONTROLS["blitz_3|2"]
        return cls(
            control_id=tc["id"],
            white=SideClock(remaining_ms=int(tc["base_ms"])),
            black=SideClock(remaining_ms=int(tc["base_ms"])),
            increment_ms=int(tc["increment_ms"]),
        )

    def side(self, white_to_move: bool) -> SideClock:
        return self.white if white_to_move else self.black

    def begin_turn(self, white_to_move: bool) -> None:
        self.side(white_to_move).start()

    def end_turn(self, white_to_move: bool, *, san: str = "") -> dict[str, Any]:
        clock = self.side(white_to_move)
        spent = clock.stop()
        if self.increment_ms and not clock.flag():
            clock.remaining_ms += self.increment_ms
        ev = {
            "side": "white" if white_to_move else "black",
            "san": san,
            "spent_ms": spent,
            "remaining_ms": clock.remaining_ms,
            "flag": clock.flag(),
        }
        self.move_times.append(ev)
        return ev

    def flagged_side(self) -> Optional[str]:
        if self.white.flag():
            return "white"
        if self.black.flag():
            return "black"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "increment_ms": self.increment_ms,
            "white": self.white.to_dict(),
            "black": self.black.to_dict(),
            "move_times": self.move_times[-20:],
        }


def reasoning_delay_sec(mind: dict[str, Any], *, rng=None) -> float:
    """
    Non-uniform think time so agents don't feel identical.
    Uses mind.think_ms_min / think_ms_max (defaults 400–1800ms).
    """
    import random

    r = rng or random
    lo = int(mind.get("think_ms_min", 400))
    hi = int(mind.get("think_ms_max", 1800))
    if hi < lo:
        hi = lo
    return r.randint(lo, hi) / 1000.0
