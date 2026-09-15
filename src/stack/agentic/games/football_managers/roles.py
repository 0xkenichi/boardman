"""FM-style role catalogue + deterministic role suitability.

Football Manager shows each player's suitability (1–5★) for the roles of
their position. We mirror that: every slot has a family of roles, and each
role weights the attributes the engine already derives (`attributes.py`).
Suitability is a weighted mean of those attributes scaled to 1–5★ — a pure
function of the player's deterministic attribute profile, so the same player
always shows the same roles. No stored role data, no RNG.

These roles are also the vocabulary the engine will consume once per-role
duties land (roadmap row "role/duty-level instructions"), so keeping the
catalogue here (Python, authoritative) means the squad screen and the engine
can agree on what a "Box-to-Box Midfielder" is.
"""

from __future__ import annotations

from typing import Any, Optional

# Role families per slot. Weights sit over the 0-99 skill attributes
# (pace, technical, physicality, decision_making, positioning, shooting,
# passing, tackling, gk). Shared families alias so RB/LB and RW/LW agree.
_ROLE_FAMILIES: dict[str, list[tuple[str, dict[str, float]]]] = {
    "GK": [
        ("Goalkeeper (Defend)", {"gk": 2.0, "positioning": 1.2, "decision_making": 1.0,
                                 "physicality": 0.8, "tackling": 0.4, "pace": 0.3}),
        ("Sweeper Keeper (Support)", {"gk": 1.4, "passing": 1.0, "technical": 0.9,
                                      "decision_making": 1.1, "pace": 0.8, "positioning": 0.8}),
    ],
    "FB": [  # RB / LB
        ("Full-Back (Defend)", {"tackling": 1.6, "pace": 1.3, "positioning": 1.2,
                                "physicality": 1.1, "passing": 0.9, "technical": 0.8}),
        ("Wing-Back (Attack)", {"pace": 1.7, "technical": 1.2, "passing": 1.2,
                                "decision_making": 0.9, "tackling": 0.9, "positioning": 0.9}),
        ("Inverted Full-Back (Support)", {"technical": 1.4, "passing": 1.5, "decision_making": 1.2,
                                          "tackling": 1.1, "positioning": 1.0, "pace": 0.9}),
    ],
    "CB": [
        ("Centre-Back (Defend)", {"tackling": 1.7, "positioning": 1.6, "physicality": 1.5,
                                  "decision_making": 1.2, "pace": 0.8}),
        ("Ball-Playing Defender", {"tackling": 1.3, "passing": 1.5, "technical": 1.3,
                                   "decision_making": 1.3, "positioning": 1.2, "physicality": 1.1,
                                   "pace": 0.8}),
        ("No-Nonsense Centre-Back", {"physicality": 1.7, "tackling": 1.7, "positioning": 1.3,
                                     "decision_making": 0.9, "pace": 0.9, "technical": 0.3}),
    ],
    "DM": [  # CDM
        ("Defensive Midfielder (Defend)", {"tackling": 1.6, "positioning": 1.4, "physicality": 1.3,
                                           "decision_making": 1.3, "passing": 1.0}),
        ("Deep-Lying Playmaker (Defend)", {"passing": 1.7, "technical": 1.4, "decision_making": 1.4,
                                           "positioning": 1.0, "tackling": 0.9}),
        ("Half-Back", {"tackling": 1.4, "positioning": 1.5, "decision_making": 1.3,
                       "passing": 1.1, "physicality": 1.2}),
    ],
    "CM": [
        ("Box-to-Box Midfielder", {"pace": 1.3, "physicality": 1.2, "tackling": 1.2, "passing": 1.2,
                                   "decision_making": 1.1, "positioning": 1.1, "shooting": 0.8,
                                   "technical": 0.9}),
        ("Advanced Playmaker (Attack)", {"passing": 1.6, "technical": 1.6, "decision_making": 1.4,
                                         "shooting": 0.8, "pace": 0.7}),
        ("Mezzala (Attack)", {"technical": 1.4, "passing": 1.3, "shooting": 1.2,
                              "decision_making": 1.1, "pace": 1.0, "physicality": 0.9}),
        ("Central Midfielder (Support)", {"passing": 1.4, "technical": 1.2, "decision_making": 1.2,
                                          "tackling": 1.0, "positioning": 1.0, "physicality": 0.9}),
    ],
    "AM": [  # CAM
        ("Advanced Playmaker (Attack)", {"passing": 1.6, "technical": 1.7, "decision_making": 1.4,
                                         "shooting": 1.0, "pace": 0.8}),
        ("Trequartista", {"technical": 1.8, "passing": 1.5, "decision_making": 1.3,
                          "shooting": 1.0, "pace": 0.6, "physicality": 0.2}),
        ("Shadow Striker (Attack)", {"shooting": 1.6, "pace": 1.3, "technical": 1.2,
                                     "decision_making": 1.1, "positioning": 1.2, "passing": 0.8}),
    ],
    "W": [  # RW / LW
        ("Winger (Support)", {"pace": 1.8, "technical": 1.4, "passing": 1.1,
                              "decision_making": 0.9, "shooting": 0.6, "positioning": 0.5}),
        ("Inside Forward (Attack)", {"pace": 1.5, "shooting": 1.5, "technical": 1.3,
                                     "decision_making": 1.1, "positioning": 1.2, "passing": 0.7}),
        ("Inverted Winger (Attack)", {"technical": 1.5, "pace": 1.5, "passing": 1.2,
                                      "decision_making": 1.1, "shooting": 0.9}),
    ],
    "ST": [
        ("Advanced Forward", {"pace": 1.7, "shooting": 1.7, "positioning": 1.5, "technical": 1.2,
                              "decision_making": 1.0, "physicality": 0.7, "passing": 0.5}),
        ("Pressing Forward (Attack)", {"physicality": 1.6, "pace": 1.4, "decision_making": 1.2,
                                       "shooting": 1.1, "positioning": 1.2, "technical": 0.7}),
        ("Target Man (Support)", {"physicality": 1.8, "shooting": 1.4, "positioning": 1.3,
                                  "technical": 1.0, "decision_making": 0.8, "passing": 0.8,
                                  "pace": 0.4}),
        ("False Nine (Support)", {"technical": 1.7, "passing": 1.6, "decision_making": 1.4,
                                  "shooting": 1.1, "pace": 0.9, "physicality": 0.4}),
        ("Poacher", {"shooting": 1.9, "positioning": 1.7, "decision_making": 1.0,
                     "pace": 1.1, "technical": 0.7, "physicality": 0.6}),
        ("Complete Forward", {"shooting": 1.5, "technical": 1.4, "physicality": 1.2, "passing": 1.1,
                              "decision_making": 1.1, "pace": 1.1, "positioning": 1.0}),
    ],
}

_FAMILY_OF: dict[str, str] = {
    "GK": "GK", "RB": "FB", "LB": "FB", "CB": "CB", "CDM": "DM",
    "CM": "CM", "CAM": "AM", "RW": "W", "LW": "W", "ST": "ST",
}

STAR_BANDS: list[tuple[int, float]] = [
    (5, 90.0),
    (4, 84.0),
    (3, 78.0),
    (2, 70.0),
]


def _stars(score: float) -> int:
    for stars, lo in STAR_BANDS:
        if score >= lo:
            return stars
    return 1


def role_suitability(slot: str, attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """Suitability (score + 1–5★) for every role of a player's slot, best first.

    `attrs` is the player's attribute profile from `attributes.py` (keys on
    the 0-99 skill scale). The result is a pure function of (slot, attrs), so
    it is deterministic and needs no stored data.
    """
    family = _FAMILY_OF.get((slot or "").upper())
    roles = _ROLE_FAMILIES.get(family or "CM", _ROLE_FAMILIES["CM"])
    out: list[dict[str, Any]] = []
    for name, weights in roles:
        wsum = sum(weights.values())
        if wsum <= 0:
            continue
        score = sum(float(attrs.get(k, 70.0)) * w for k, w in weights.items()) / wsum
        score = max(1.0, min(99.0, score))
        out.append({
            "name": name,
            "score": round(score, 1),
            "stars": _stars(score),
        })
    out.sort(key=lambda r: (-r["score"], r["name"]))
    return out


def roles_for_squad(player: dict[str, Any]) -> list[dict[str, Any]]:
    """Convenience: role suitability straight from a squad/catalog record.

    Derives the attribute profile on the fly (same path as the engine), so a
    squad screen row can ask for roles without juggling attrs itself.
    """
    from gaming.src.stack.agentic.games.football_managers.attributes import derive_profile

    attrs = derive_profile(player)
    return role_suitability(str(player.get("slot") or "CM"), attrs)


def role_meta() -> dict[str, Any]:
    """Public summary (role names per family) for docs / tool surfaces."""
    return {
        "families": {fam: [name for name, _ in roles] for fam, roles in _ROLE_FAMILIES.items()},
        "star_bands": [{"stars": s, "min_score": lo} for s, lo in STAR_BANDS],
    }