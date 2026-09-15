"""AFM manager detail card — the marketplace's at-a-glance read model.

Everything a buyer wants to know about a manager before making an offer,
derived purely from state that already exists (no new writes):

- **playbook radar** — how the mind actually sets up, computed from the same
  `decide.STRATEGIES` the matchday decision loop runs: forward/defensive slot
  share of the archetype's first-choice formation, press intensity of its base
  tag, counter instinct, system-vs-stars selection style.
- **ability radar** — what the manager has to work with: squad-average
  attributes from `attributes.derive_profile` (deterministic per player), so a
  bought manager inherits the club it runs, not a generic profile.
- **record charts** — the season so far from stored results: per-matchday
  outcomes, goals and xG for/against, a last-5 form string, plus season
  totals. Mirrors the standings row the league table already shows.

The card never fabricates numbers: an axis is a computed share, a chart point
is a stored result. A manager with no season yet simply has an empty record.
"""
from __future__ import annotations

from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.attributes import derive_profile
from gaming.src.stack.agentic.games.football_managers.decide import STRATEGIES
from gaming.src.stack.agentic.games.football_managers.club_store import (
    _formation_slots,
    get_club,
)

# The archetype key lives on registry records under ``mind.archetype``; market
# rows carry it top-level already.
def _arch_of(agent: dict[str, Any]) -> str:
    arch = str(agent.get("archetype") or "").strip()
    if arch:
        return arch
    mind = agent.get("mind") or {}
    return str(mind.get("archetype") or "").strip() or "tactician"

# Radar axes in draw order (clockwise from the top).
PLAYBOOK_AXES = ("attack", "press", "defence", "counter", "system", "stars")
ABILITY_AXES = ("attack", "pace", "defence", "passing", "physical", "keeper")

# Slot groups for formation shares (a formation is 1 GK + 10 outfield slots).
_FWD_SLOTS = {"RW", "LW", "ST", "CAM"}
_DEF_SLOTS = {"CB", "RB", "LB", "CDM"}

# Per-slot attacking / defensive commitment (0-1 each), summed over the 10
# outfield slots and scaled to 0-100. Raw group shares cannot separate our
# shapes (the repo's 3-4-3 and 5-3-2 slot tables carry the same DEF/MID/FWD
# counts), so the weights encode where each slot actually plays: a striker
# weights more than a wide man, a centre-back more than a full-back.
_SLOT_ATTACK_W = {
    "ST": 1.0, "RW": 0.9, "LW": 0.9, "CAM": 0.8, "CM": 0.5,
    "CDM": 0.3, "RB": 0.4, "LB": 0.4, "CB": 0.1,
}
_SLOT_DEFENCE_W = {
    "CB": 0.9, "CDM": 0.7, "RB": 0.6, "LB": 0.6, "CM": 0.4,
    "CAM": 0.3, "RW": 0.2, "LW": 0.2, "ST": 0.1,
}

# Base-tag press intensity on a 0-100 scale (higher = squeezes higher up the
# pitch). Reactive/hold tags sit in the middle.
_TAG_PRESS = {
    "gegenpress": 95.0,
    "high_press": 80.0,
    "balanced": 50.0,
    "tiki_taka": 60.0,
    "counter": 40.0,
    "low_block": 20.0,
    "park_bus": 10.0,
}

# Squad attributes folded into each ability axis (derive_profile's 0-99 scale).
_ABILITY_SOURCE: dict[str, tuple[str, ...]] = {
    "attack": ("shooting", "technical"),
    "pace": ("pace",),
    "defence": ("tackling", "positioning"),
    "passing": ("passing", "decision_making"),
    "physical": ("physicality",),
    "keeper": ("gk",),
}


def _clamp100(v: float) -> float:
    return round(max(0.0, min(100.0, float(v))), 1)


def _slot_index(slots: list[str], weights: dict[str, float]) -> float:
    outfield = [s for s in slots if s != "GK"]
    total = sum(weights.get(s, 0.5) for s in outfield)
    return 100.0 * total / max(len(outfield), 1)


def playbook_axes(archetype: str) -> dict[str, float]:
    """How the archetype's mind sets up, on six 0-100 axes.

    Computed from the live strategy table (decide.STRATEGIES) so the radar can
    never drift from what the manager actually does on a matchday. Attack and
    defence blend the first-choice formation's slot weights (60%) with the
    base tag's aggression (40%) — the shape is where players stand, the tag is
    how far up the pitch they go.
    """
    strat = STRATEGIES.get(archetype or "", STRATEGIES["tactician"])
    formation = str(strat["formations"][0])
    slots = _formation_slots(formation)
    tags = list(strat.get("tags") or ["balanced"])
    base_tag = str(tags[0]) if tags else "balanced"
    reactive = str(tags[-1]) if len(tags) > 1 else base_tag
    pick = str(strat.get("pick") or "shape")
    press = _TAG_PRESS.get(base_tag, 50.0)
    return {
        "attack": _clamp100(0.6 * _slot_index(slots, _SLOT_ATTACK_W) + 0.4 * press),
        "press": _clamp100(press),
        "defence": _clamp100(0.6 * _slot_index(slots, _SLOT_DEFENCE_W) + 0.4 * (100.0 - press)),
        "counter": _clamp100(85.0 if reactive == "counter" else 30.0),
        "system": _clamp100(90.0 if pick == "shape" else 35.0),
        "stars": _clamp100(90.0 if pick == "rating" else 35.0),
    }


def playbook_summary(archetype: str) -> dict[str, Any]:
    """The concrete choices behind the radar (shape, tag, selection style)."""
    strat = STRATEGIES.get(archetype or "", STRATEGIES["tactician"])
    tags = list(strat.get("tags") or ["balanced"])
    return {
        "formation": str(strat["formations"][0]),
        "base_tag": str(tags[0]) if tags else "balanced",
        "reactive_tag": str(tags[-1]) if len(tags) > 1 else (str(tags[0]) if tags else "balanced"),
        "pick": str(strat.get("pick") or "shape"),
        "shapes": [str(f) for f in strat.get("formations") or []],
    }


def _squad_attributes(agent_id: str) -> list[dict[str, float]]:
    """Derived attribute profiles for the squad the manager can actually pick
    (healthy + unsuspended, like the decide loop) — falls back to the whole
    roster when everyone is unavailable."""
    club = get_club(agent_id) or {}
    squad = [p for p in club.get("squad") or [] if isinstance(p, dict)]
    if not squad:
        return []
    available = [
        p
        for p in squad
        if not p.get("injury") and int(p.get("suspension_matches") or 0) <= 0
    ]
    return [derive_profile(p) for p in (available or squad)]


def ability_axes(agent_id: str) -> Optional[dict[str, float]]:
    """Squad-average attributes on six 0-100 radar axes.

    ``None`` when the manager has no squad (never played, club not seeded) —
    the UI hides the radar instead of drawing a zeroed one.
    """
    profiles = _squad_attributes(agent_id)
    if not profiles:
        return None
    out: dict[str, float] = {}
    for axis, names in _ABILITY_SOURCE.items():
        vals = [
            attrs.get(name, 0.0)
            for attrs in profiles
            for name in names
            if name not in ("fitness", "morale")
        ]
        out[axis] = _clamp100(sum(vals) / len(vals) if vals else 0.0)
    return out


def record_series(agent_id: str) -> dict[str, Any]:
    """The manager's season so far from stored results, oldest first.

    ``matches`` skips byes (no fixture). Each point carries the opponent and
    venue so the UI can label it. xG comes from the engine's per-shot fold
    already stored on every result.
    """
    from gaming.src.stack.agentic.games.football_managers import season as S

    out: list[dict[str, Any]] = []
    try:
        # raw stored state — get_season()'s public snapshot omits matchday results
        season = S._state().get("season") or {}
    except Exception:
        season = {}
    matchdays = season.get("matchdays") or {}
    for md_key in sorted(int(k) for k in matchdays):
        info = matchdays[str(md_key)] or {}
        for r in info.get("results") or []:
            if agent_id not in (r.get("home_agent_id"), r.get("away_agent_id")):
                continue
            is_home = r.get("home_agent_id") == agent_id
            hg, ag = int(r.get("home_goals") or 0), int(r.get("away_goals") or 0)
            ours, theirs = (hg, ag) if is_home else (ag, hg)
            stats = r.get("stats") or {}
            xg_for = float(stats.get("shots_xg_home" if is_home else "shots_xg_away") or 0.0)
            xg_against = float(stats.get("shots_xg_away" if is_home else "shots_xg_home") or 0.0)
            out.append(
                {
                    "matchday": md_key,
                    "venue": "home" if is_home else "away",
                    "opponent_id": r.get("away_agent_id" if is_home else "home_agent_id"),
                    "opponent_club": r.get("away_club" if is_home else "home_club"),
                    "gf": ours,
                    "ga": theirs,
                    "outcome": "W" if ours > theirs else ("L" if ours < theirs else "D"),
                    "xg_for": round(xg_for, 2),
                    "xg_against": round(xg_against, 2),
                }
            )

    played = len(out)
    wins = sum(1 for m in out if m["outcome"] == "W")
    draws = sum(1 for m in out if m["outcome"] == "D")
    losses = played - wins - draws
    goals_for = sum(m["gf"] for m in out)
    goals_against = sum(m["ga"] for m in out)
    xg_for = round(sum(m["xg_for"] for m in out), 2)
    xg_against = round(sum(m["xg_against"] for m in out), 2)
    return {
        "matches": [
            {
                k: m[k]
                for k in ("matchday", "venue", "opponent_id", "opponent_club", "gf", "ga", "outcome", "xg_for", "xg_against")
            }
            for m in out
        ],
        "totals": {
            "played": played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "points": wins * 3 + draws,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "xg_for": xg_for,
            "xg_against": xg_against,
        },
        "form": "".join(m["outcome"] for m in out[-5:]),
    }


def manager_card(agent: dict[str, Any], archetype: Optional[str] = None) -> dict[str, Any]:
    """The full detail card for one marketplace manager row.

    ``archetype`` is the caller's resolved mind archetype (registry records
    carry it under ``mind.archetype``). Pure projection — safe to embed on
    every marketplace row (cheap folds over stored state, no writes, no RNG).
    """
    agent_id = str(agent.get("agent_id") or "")
    arch = str(archetype) if archetype else _arch_of(agent)
    abilities = ability_axes(agent_id)
    record = record_series(agent_id)
    return {
        "playbook": {
            "axes": playbook_axes(arch),
            "axis_order": list(PLAYBOOK_AXES),
            "summary": playbook_summary(arch),
        },
        "ability": (
            {"axes": abilities, "axis_order": list(ABILITY_AXES)} if abilities else None
        ),
        "record": record,
    }
