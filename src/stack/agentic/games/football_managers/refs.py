"""Match officials & the unexpected — the referee layer (arc L3).

Football is refereed by people, not by a rulebook. Every fixture gets an
official with a personality (a strictness curve over the 90 minutes) and every
player carries a hidden temperament — together they decide who collects cards
and when. This module also owns the *surprise events* that make a season feel
alive: a personal matter, a 24-hour bug, a knock in the warm-up — small, rare,
deterministic per (fixture, player), and absorbed by the living layer as
morale dents.

Everything here is a pure function of identity (match_id / player_id) and the
constant tables below, so replays stay byte-identical, the referee can be
announced pre-match like real football, and no extra state needs storing.
"""
from __future__ import annotations

from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.attributes import _hash01

# --------------------------------------------------------------- personas
# A persona is a strictness curve over (minute 0..90, tension): how ready the
# official is to reach for a card at that point of the game. 0.05..0.95.


def _p_steady(minute: int, tension: bool) -> float:
    return 0.50 + (0.10 if tension else 0.0)


def _p_lenient(minute: int, tension: bool) -> float:
    return 0.22 + (0.10 if tension else 0.0)


def _p_strict(minute: int, tension: bool) -> float:
    return 0.80 + (0.08 if tension else 0.0)


def _p_lets_it_flow(minute: int, tension: bool) -> float:
    """Lets it flow early; tightens as the game boils late."""
    return 0.25 + 0.38 * (minute / 90.0) ** 1.6 + (0.10 if tension else 0.0)


def _p_no_nonsense(minute: int, tension: bool) -> float:
    """No rubbish from minute one — strict early to set the tone, then eases
    off once the game has settled."""
    return 0.85 - 0.32 * (minute / 90.0) + (0.08 if tension else 0.0)


def _p_eases_off(minute: int, tension: bool) -> float:
    """A card-happy start that fades as the game gets intense — he wants to
    keep 22 men on the pitch in a derby."""
    return 0.68 - 0.28 * (minute / 90.0) ** 0.8 + (0.12 if tension else 0.0)


PERSONAS: dict[str, str] = {
    "steady": "by the book, all game",
    "lenient": "lets a lot go, all game",
    "strict": "cards readily, all game",
    "lets_it_flow": "lets it flow early, tightens late",
    "no_nonsense": "no rubbish from minute one, eases off as it settles",
    "eases_off": "strict early, eases off as the game gets intense",
}
_PERSONA_FN = {
    "steady": _p_steady,
    "lenient": _p_lenient,
    "strict": _p_strict,
    "lets_it_flow": _p_lets_it_flow,
    "no_nonsense": _p_no_nonsense,
    "eases_off": _p_eases_off,
}

# --------------------------------------------------------------- the roster
# Twelve named officials: two per persona, each with a small deterministic
# base-strictness tilt so two "strict" refs are not identical.


_ROSTER_SEED: list[tuple[str, str]] = [
    ("Pierluigi Tanzi", "steady"),
    ("Marcus Bell", "steady"),
    ("Rui Cavaco", "lenient"),
    ("Astrid Vollen", "lenient"),
    ("Sandra Okoye", "strict"),
    ("Piotr Wilda", "strict"),
    ("Felix Brandtner", "lets_it_flow"),
    ("Grace Mwangi", "lets_it_flow"),
    ("Hideo Marumo", "no_nonsense"),
    ("Diego Sarasti", "no_nonsense"),
    ("Youssef El-Amrani", "eases_off"),
    ("Lena Falkmer", "eases_off"),
]

_REFEREE_LIST: list[dict[str, Any]] = [
    {
        "ref_id": f"ref_{i:02d}",
        "name": name,
        "persona": persona,
        "base": round(
            0.5 + (_hash01(f"ref:{name}", "base_tilt") - 0.5) * 0.12, 3
        ),
    }
    for i, (name, persona) in enumerate(_ROSTER_SEED)
]


def _clamp_strict(v: float) -> float:
    return max(0.05, min(0.95, v))


def referee_for(match_id: str) -> dict[str, Any]:
    """The official for this fixture — deterministic from the match id."""
    idx = int(_hash01(str(match_id), "referee") * len(_REFEREE_LIST)) % len(_REFEREE_LIST)
    ref = _REFEREE_LIST[idx]
    return dict(ref)


def all_referees() -> list[dict[str, Any]]:
    """The officiating roster (for the news desk / dashboard)."""
    return [dict(r) for r in _REFEREE_LIST]


def strictness_at(ref: dict[str, Any], minute: int, tension: bool = False) -> float:
    """How card-ready this official is at `minute`, given a tight finish."""
    fn = _PERSONA_FN.get(str(ref.get("persona") or "steady"), _p_steady)
    base = float(ref.get("base") or 0.5)
    return _clamp_strict(fn(max(0, min(90, int(minute))), bool(tension)) + (base - 0.5))


def persona_label(persona: str) -> str:
    return PERSONAS.get(str(persona), PERSONAS["steady"])


def news_line(ref: dict[str, Any]) -> str:
    """Team-news line announcing the official (Sphera-style pre-match info)."""
    return f"Referee: {ref.get('name')} — {persona_label(str(ref.get('persona')))}"


def card_scales(
    ref: dict[str, Any],
    minute: int,
    tension: bool = False,
    temper: float = 0.5,
) -> tuple[float, float, float]:
    """Card-band multipliers for one foul: (yellow, straight-red, free-kick).

    Mean-preserving by construction — at average strictness and average
    temperament every scale is 1.0 — so the league-wide card rate keeps its
    calibration while the *variance* becomes personality: a lenient ref lets
    a cold defender's tackles go, a strict ref books a volatile winger twice.
    """
    s = strictness_at(ref, minute, tension)
    temper = max(0.0, min(1.0, float(temper)))
    y = (0.55 + 0.9 * s) * (0.70 + 0.60 * temper)
    r = (0.60 + 0.8 * s) * (0.80 + 0.40 * temper)
    fk = 0.60 + 0.8 * s
    return y, r, fk


# --------------------------------------------------------------- surprises
# Rare pre-match events the manager cannot control. Deterministic per
# (match_id, player_id); absorbed by the living layer as a morale dent for
# that fixture and carried slightly afterwards.

SURPRISE_TABLE: list[dict[str, Any]] = [
    {
        "kind": "personal",
        "dent": -0.07,
        "label": "a personal matter kept him away from full training this week",
    },
    {
        "kind": "illness",
        "dent": -0.06,
        "label": "a 24-hour bug on the eve of the game",
    },
    {
        "kind": "knock",
        "dent": -0.05,
        "label": "carried a knock into the warm-up",
    },
    {
        "kind": "family",
        "dent": 0.04,
        "label": "became a father on Thursday — sleepless, and playing on adrenaline",
    },
]

SURPRISE_P = 0.02  # per player per fixture — a league feels it roughly weekly


def surprise_for(match_id: str, player_id: str) -> Optional[dict[str, Any]]:
    """A surprise event for this player in this fixture, or None.

    ~2% per player per fixture: with ~11 starters per side that is roughly
    one surprise every other match across a fixture, felt across the league
    about once a matchday — the FM drip of "X had an off-field week".
    """
    if _hash01(f"{match_id}:{player_id}", "surprise") >= SURPRISE_P:
        return None
    pick = _hash01(f"{match_id}:{player_id}", "surprise_pick") * len(SURPRISE_TABLE)
    ev = SURPRISE_TABLE[int(pick) % len(SURPRISE_TABLE)]
    return {"kind": ev["kind"], "dent": ev["dent"], "label": ev["label"]}
