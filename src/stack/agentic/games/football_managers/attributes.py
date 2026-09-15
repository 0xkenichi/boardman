"""
AFM player attribute model (Phase 0).

The engine differentiates outcomes through a small set of football attributes
(pace, technical ability, physicality, decision-making, positional sense,
shooting, passing, tackling, goalkeeping, fitness, morale) rather than a
single "base_rating" number.

Attributes are *derived deterministically* from each player's stable identity
(player_id) + base_rating + position + form, so:

  - the catalog file never needs an attributes column (no data migration),
  - the same player always has the same attributes (deterministic across
    runs, machines and replay reconstructions),
  - materially better squads get materially better attribute profiles, which
    is the Phase 0 acceptance criterion "attributes measurably change match
    outcomes",
  - the model is an implementation detail: precise weights live here and can
    be tuned without touching the event loop.

Ratings are on the same 0-99 scale as base_rating. A rating of ~90 is
world-class, ~70 is a journeyman.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

# The attribute vocabulary the engine consumes. Implementations may vary,
# but these are the ones that *meaningfully affect simulated outcomes*.
ATTRIBUTES = (
    "pace",           # speed in open play — wins races, stretches lines
    "technical",      # first touch, dribbling, ball control
    "physicality",    # strength / aggression in duels
    "decision_making",  # choice quality under pressure
    "positioning",    # off-ball reading: finding space / denying space
    "shooting",       # finishing + shot power
    "passing",        # range + accuracy
    "tackling",       # defensive duels
    "gk",             # goalkeeping (only meaningful for GK)
    "fitness",        # 0..1 stamina reservoir, drained during a match
    "morale",         # 0..1 form multiplier, lifted by good form
)

# Position group -> attribute biases applied on top of base_rating.
_SLOT_BIAS: dict[str, dict[str, float]] = {
    "GK": {"gk": 9.0, "positioning": 5.0, "physicality": 1.0, "decision_making": 2.0},
    "RB": {"tackling": 4.0, "pace": 4.0, "physicality": 2.0, "positioning": 3.0, "passing": 2.0},
    "CB": {"tackling": 7.0, "physicality": 6.0, "positioning": 6.0, "pace": 1.0, "decision_making": 1.0},
    "LB": {"tackling": 4.0, "pace": 4.0, "physicality": 2.0, "positioning": 3.0, "passing": 2.0},
    "CDM": {"tackling": 5.0, "physicality": 3.0, "passing": 3.0, "decision_making": 3.0, "positioning": 2.0},
    "CM": {"passing": 6.0, "technical": 4.0, "decision_making": 3.0, "tackling": 1.0, "positioning": 1.0},
    "CAM": {"technical": 6.0, "passing": 4.0, "shooting": 3.0, "decision_making": 3.0},
    "RW": {"pace": 6.0, "shooting": 3.0, "technical": 5.0, "passing": 1.0},
    "LW": {"pace": 6.0, "shooting": 3.0, "technical": 5.0, "passing": 1.0},
    "ST": {"shooting": 7.0, "pace": 4.0, "technical": 2.0, "physicality": 1.0, "positioning": 3.0},
}

_GROUP_FALLBACK = {
    "GK": "GK",
    "DEF": "CB",
    "MID": "CM",
    "FWD": "ST",
}

# Wider noise spread on attributes that carry less of a player's core value.
_NOISE_SPAN = 5.0  # ±2.5 from the seeded hash


def _slot_for(p: dict[str, Any]) -> str:
    slot = str(p.get("slot") or p.get("primary_pos") or "CM").upper()
    if slot in _SLOT_BIAS:
        return slot
    return _GROUP_FALLBACK.get(slot, "CM")


def _hash01(player_id: str, attr: str) -> float:
    """Deterministic [0,1) per (player, attribute) — stable across runs."""
    h = hashlib.sha256(f"afm:{player_id}:{attr}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / (2**32)


def player_attributes(
    player_id: str,
    base_rating: float = 70.0,
    slot: Optional[str] = None,
    form: float = 6.5,
    fitness: float = 1.0,
) -> dict[str, float]:
    """Deterministic attribute profile for a player.

    Attributes are anchored on base_rating (so squad quality is the dominant
    signal), biased by position, and given a small deterministic ±2.5 noise
    term per (player, attribute) so two same-rated players still differ.
    fitness/morale are 0..1 running-state values, not 0-99 skills.
    """
    slot = (slot or "MID").upper()
    bias = _SLOT_BIAS.get(slot, _SLOT_BIAS[_slot_for({"slot": slot, "primary_pos": slot})])
    out: dict[str, float] = {}
    base = float(base_rating)
    for attr in ATTRIBUTES:
        if attr in ("fitness", "morale"):
            continue
        seeded = (_hash01(player_id, attr) - 0.5) * _NOISE_SPAN
        if attr == "gk" and slot != "GK":
            out[attr] = 20.0  # outfielders cannot keep goal
            continue
        v = base + bias.get(attr, 0.0) + seeded
        # decision/positioning benefit from experience curve flattening a touch
        out[attr] = min(99.0, max(25.0, v))

    # fitness drains during a match from this starting level (1.0 at kickoff);
    # morale follows the player's form marker (6.5 avg -> ~0.72).
    form_f = float(form)
    out["fitness"] = max(0.1, min(1.0, float(fitness)))
    out["morale"] = max(0.45, min(1.0, 0.55 + (form_f - 6.0) * 0.18))
    return out


def derive_profile(player: Optional[dict[str, Any]]) -> dict[str, float]:
    """Attribute profile straight from a catalog player record (or defaults)."""
    if not player:
        return player_attributes("unknown", base_rating=70.0, slot="CM", form=6.5)
    return player_attributes(
        str(player.get("player_id") or "unknown"),
        base_rating=float(player.get("base_rating") or 70.0),
        slot=str(player.get("slot") or player.get("primary_pos") or "CM"),
        form=float(player.get("form") or 6.5),
        fitness=1.0,
    )


def group_skill(attrs: dict[str, float], *names: str) -> float:
    """Mean of the named skills (fitness/morale excluded automatically)."""
    vals = [attrs[n] for n in names if n in attrs and n not in ("fitness", "morale")]
    if not vals:
        return 70.0
    return sum(vals) / len(vals)
