"""AI filler clubs — Sphera-style league bootstrapping (v1.8).

A division with one or two real manager agents would be a two-club derby on
a tiny calendar. Sphera's answer (case study 2026-10-03): fill the league
with named AI clubs ("AI Team sphera-australia-L1-15") that play full
seasons and get replaced as real managers join. This module is the AFM port:

  * `ai_filler_NN` agents own real clubs with generated 16-player squads —
    deterministic per index, never competing with the shared catalog pool;
  * `open_season` tops the division up to AFM_FILLER_TARGET (default 10) on
    the auto path only — explicit agent-id lists keep exact control;
  * fillers pay season entry, wages and match stakes from deterministic
    synthetic wallets like everyone else; the House auto-picks their XIs
    (they never answer asks) and they give no press quotes;
  * as real agents queue up, fewer fillers are fielded — a filler league
    slot is simply not used once real clubs fill the division.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from gaming.src.stack.agentic.games.football_managers.catalog import add_generated

FILLER_PREFIX = "ai_filler_"

# Default division size once fillers are in: even, so no byes and every club
# plays every other home and away (18 matchdays at 10 clubs).
DEFAULT_TARGET = 10

# First 11 field a legal 4-3-3 by construction; the last 5 are the bench.
_SLOTS_TEMPLATE = (
    "GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CM", "RW", "ST", "LW",
    "GK", "CB", "CM", "CAM", "ST",
)

_INITIALS = tuple("ABCDEFGHIJKLMNOPRSTVWZ")
_SURNAMES = (
    "Tanaka", "Okoro", "Silva", "Andersen", "Kovac", "Mbaye", "Rossi",
    "Novak", "Duarte", "Kimura", "Halder", "Fontaine", "Bakker", "Costa",
    "Eze", "Vidal", "Ito", "Larsen", "Moreau", "Sarr", "Weiss", "Yilmaz",
    "Bruno", "Carew", "Dahl", "Gomes", "Haugen", "Iwobi", "Jensen",
    "Kaminski", "Lindgren", "Marchetti",
)


def is_filler(agent_id: str) -> bool:
    return str(agent_id or "").startswith(FILLER_PREFIX)


def synthetic_wallet(agent_id: str) -> str:
    """Filler agents are not registered — they bank on a stable wallet key."""
    return f"afm_wallet_{agent_id}"


def filler_enabled() -> bool:
    return os.getenv("AFM_FILLER_CLUBS", "1").strip().lower() not in ("0", "false", "off")


def filler_target() -> int:
    try:
        return max(2, int(os.getenv("AFM_FILLER_TARGET", str(DEFAULT_TARGET))))
    except ValueError:
        return DEFAULT_TARGET


def filler_index(agent_id: str) -> Optional[int]:
    if not is_filler(agent_id):
        return None
    try:
        return int(str(agent_id)[len(FILLER_PREFIX):])
    except ValueError:
        return None


def _h(key: str) -> float:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(16 ** 12)


def _gen_squad(idx: int) -> list[str]:
    """16 deterministic players for filler club #idx (ids afm_ai_p_NN_MM)."""
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player

    pids: list[str] = []
    for i, slot in enumerate(_SLOTS_TEMPLATE):
        pid = f"afm_ai_p_{idx:02d}_{i:02d}"
        if get_player(pid) is None:
            n = idx * 16 + i
            rating = 66 + int(_h(f"{pid}:rating") * 10)  # 66..75 — honest mid-table
            real_value = int(2_000_000 + _h(f"{pid}:value") * 28_000_000)
            name = f"{_INITIALS[n % len(_INITIALS)]}. {_SURNAMES[n % len(_SURNAMES)]}"
            add_generated(
                {
                    "player_id": pid,
                    "name": name,
                    "nation": "AI",
                    "slot": slot,
                    "base_rating": rating,
                    "real_value_usd": real_value,
                }
            )
        pids.append(pid)
    return pids


def _ensure_filler_club(idx: int) -> str:
    from gaming.src.stack.agentic.games.football_managers import club_store

    aid = f"{FILLER_PREFIX}{idx:02d}"
    club = club_store.get_club(aid)
    if club and (club.get("squad") or club.get("roster_size")):
        return aid
    club_store.ensure_club_for_agent(
        aid,
        club_name=f"AI Team afm-L1-{idx:02d}",
        formation="4-3-3",
        squad_ids=_gen_squad(idx),
        is_filler=True,
    )
    return aid


def existing_filler_ids() -> list[str]:
    from gaming.src.stack.agentic.games.football_managers import club_store

    return sorted(c["agent_id"] for c in club_store.list_clubs() if c.get("is_filler"))


def next_filler_index(existing: Optional[set[str]] = None) -> int:
    taken = existing if existing is not None else set(existing_filler_ids())
    idx = 1
    while f"{FILLER_PREFIX}{idx:02d}" in taken:
        idx += 1
    return idx


def top_up(need: int, *, exclude: Optional[set[str]] = None) -> list[str]:
    """Ids to complete a division: reuse idle fillers first, then mint new."""
    if need <= 0:
        return []
    exclude = set(exclude or set())
    out: list[str] = []
    for aid in existing_filler_ids():
        if len(out) >= need:
            break
        if aid not in exclude:
            out.append(aid)
    idx = next_filler_index()
    guard = 0
    while len(out) < need and guard < 200:
        aid = _ensure_filler_club(idx)
        if aid not in exclude and aid not in out:
            out.append(aid)
        idx += 1
        guard += 1
    return out
