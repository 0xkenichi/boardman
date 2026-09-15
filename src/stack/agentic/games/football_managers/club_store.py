"""AFM club store — agent-owned clubs, rosters, tactics and locked lineups.

Agents play AFM by owning a club, setting a formation + tactical tags and
submitting a legal XI + bench before kickoff (afm_set_lineup). The tactics
board renders exactly this state; the match engine consumes it.

Persistence: data/agentic/afm_clubs.json via the shared JSON store.
Ownership of catalog players is derived from each club's roster (single
source of truth per agent_id; uniqueness enforced by seeding and validation).
"""
from __future__ import annotations

import copy
import hashlib
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.catalog import (
    get_player,
    list_players,
    set_owner,
)
from gaming.src.stack.agentic.games.football_managers.club import create_club
from gaming.src.stack.agentic.games.football_managers.rules import (
    FORMATIONS,
    MAX_BENCH,
    MAX_SQUAD_SIZE,
    STARTERS,
    TACTICAL_TAGS,
    WAGE_RUNWAY_MATCHDAYS,
)
from gaming.src.stack.agentic.store import load_json, save_json

STATE_FILE = "afm_clubs.json"
STARTING_BUDGET_USDC = Decimal("140.00")
GAME_ID = "agentic.football_managers"

# Demo AFM manager agents get clubs; key = agent_id prefix -> club name.
# Football only — Raja/Nero are the chess duo and never own AFM clubs.
_DEMO_CLUBS: dict[str, str] = {
    "bluelock": "Blue Lock FC",
    "aoashi": "Ao Ashi FC",
    "matchslice": "Match-Slice FC",
}

_lock = threading.RLock()


def _state() -> dict[str, Any]:
    return load_json(STATE_FILE, {"clubs": {}})


def _save(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


# --------------------------------------------------------------- condition

FATIGUE_RECOVERY = 0.35  # condition regained per matchday of rest (cap 1.0)


def _club_state(agent_id: str) -> dict[str, Any]:
    """Mutable club record (or {}) without copying — internal helper."""
    return _state().get("clubs", {}).get(agent_id) or {}


def record_match_fatigue(agent_id: str, fatigue: dict[str, float]) -> None:
    """Store the condition a squad carries out of a fixture (0..1 per player).

    Called by the season after each fixture with the engine's final fatigue
    fold. Values are clamped to a sane band; unknown players are ignored.
    """
    clean = {
        str(pid): max(0.05, min(1.0, float(v)))
        for pid, v in (fatigue or {}).items()
        if isinstance(v, (int, float))
    }
    with _lock:
        state = _state()
        rec = state.get("clubs", {}).get(agent_id)
        if rec is None:
            return
        rec["condition"] = clean
        rec["condition_updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(state)


def current_condition(agent_id: str) -> dict[str, float]:
    """The condition each squad player carries into the next fixture.

    Stored post-match condition recovers `FATIGUE_RECOVERY` per matchday
    since it was recorded (capped at fresh 1.0). Players with no recorded
    condition (new signings, never played) come back fresh.
    """
    rec = _club_state(agent_id)
    cond = rec.get("condition") or {}
    if not cond:
        return {}
    weeks = 1
    try:
        stamp = rec.get("condition_updated_at")
        if stamp:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(str(stamp))).total_seconds()
            weeks = max(1, int(elapsed // 86400) + 1)
    except Exception:
        weeks = 1
    boost = min(1.0, FATIGUE_RECOVERY * weeks)
    return {
        str(pid): min(1.0, float(v) + boost)
        for pid, v in cond.items()
    }


def _resolve(player_id: str) -> Optional[dict[str, Any]]:
    p = get_player(player_id)
    return p if p else None


def _club_for_agent(agent_id: str) -> Optional[dict[str, Any]]:
    return copy.deepcopy(_state().get("clubs", {}).get(agent_id))


def _agent_display_name(agent_id: str) -> str:
    from gaming.src.stack.agentic.registry import get_registry

    try:
        rec = get_registry().get_agent(agent_id) or {}
        name = (rec.get("name") or "").strip()
        if name:
            return name
    except Exception:
        pass
    return agent_id


def club_name_for_agent(agent_id: str) -> str:
    aid = agent_id.lower()
    for key, name in _DEMO_CLUBS.items():
        if key in aid:
            return name
    return f"{_agent_display_name(agent_id)} FC"


def _price(p: dict[str, Any]) -> Decimal:
    return Decimal(str(p.get("game_price_usdc") or "0"))


def _cost_with_runway(p: dict[str, Any]) -> Decimal:
    wage = Decimal(str(p.get("wage_per_matchday_usdc") or "0"))
    return _price(p) + wage * WAGE_RUNWAY_MATCHDAYS


def _formation_slots(formation: str) -> list[str]:
    # Slots mirror the formation shapes shared with the frontend tactics board.
    _shapes = {
        "4-3-3": ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CM", "LW", "RW", "ST"],
        "4-2-3-1": ["GK", "RB", "CB", "CB", "LB", "CDM", "CDM", "RW", "CAM", "LW", "ST"],
        "4-4-2": ["GK", "RB", "CB", "CB", "LB", "CM", "CM", "RW", "LW", "ST", "ST"],
        "3-5-2": ["GK", "CB", "CB", "CB", "RB", "LB", "CDM", "CM", "CM", "ST", "ST"],
        "5-3-2": ["GK", "RB", "CB", "CB", "CB", "LB", "CDM", "CM", "CM", "ST", "ST"],
        "4-1-4-1": ["GK", "RB", "CB", "CB", "LB", "CDM", "RW", "CM", "CM", "LW", "ST"],
        "3-4-3": ["GK", "CB", "CB", "CB", "RB", "LB", "CDM", "CM", "CM", "LW", "RW"],
    }
    return list(_shapes.get(formation, _shapes["4-3-3"]))


def _auto_roster(
    formation: str,
    budget: Decimal,
    exclude: set[str] | None = None,
) -> list[str]:
    """Greedy, rating-first squad build within budget (XI + bench up to 16).

    `exclude` = player ids already owned elsewhere (one copy per player).
    """
    from gaming.src.stack.agentic.games.football_managers.catalog import SLOT_GROUP

    slots = _formation_slots(formation)
    exclude = exclude or set()
    pool = [p for p in list_players() if p["player_id"] not in exclude]
    pool.sort(key=lambda p: (-int(p.get("base_rating") or 0), -(int(p.get("real_value_usd") or 0))))
    budget_left = budget
    roster: list[str] = []
    used_ids = set()

    def try_add(p: dict[str, Any]) -> bool:
        nonlocal budget_left
        if p["player_id"] in used_ids or p["player_id"] in exclude:
            return False
        c = _cost_with_runway(p)
        if c > budget_left:
            return False
        budget_left -= c
        used_ids.add(p["player_id"])
        roster.append(p["player_id"])
        return True

    # 1) fill the XI slots
    for idx, need in enumerate(slots):
        for p in pool:
            if p["player_id"] in used_ids:
                continue
            slot = str(p.get("slot") or "")
            group = str(p.get("primary_pos") or SLOT_GROUP.get(slot, "MID"))
            ok = slot == need
            if not ok and need in {"RB", "LB"} and slot in {"RB", "LB"}:
                ok = True
            if not ok:
                want_group = "GK" if need == "GK" else "DEF" if need in {"RB", "CB", "LB"} else "MID" if need in {"CDM", "CM", "CAM"} else "FWD"
                ok = group == want_group
            if ok and try_add(p):
                break

    # 2) best remaining affordable players as bench
    for p in pool:
        if len(roster) >= MAX_SQUAD_SIZE or len(roster) >= STARTERS + MAX_BENCH:
            break
        try_add(p)
    if len(roster) < STARTERS:
        # never leave a club short of a legal XI
        for p in pool:
            if len(roster) >= STARTERS:
                break
            try_add(p)
    return roster


def _afm_demo_agents() -> list[dict[str, Any]]:
    """Registered demo managers whose only game is football managers."""
    from gaming.src.stack.agentic.registry import get_registry

    out = []
    for a in get_registry().ensure_demo_agents():
        if (a.get("role") or "") == "house":
            continue
        if GAME_ID in (a.get("game_ids") or []):
            out.append(a)
    return out


def ensure_club_for_agent(
    agent_id: str,
    *,
    club_name: Optional[str] = None,
    formation: str = "4-3-3",
    budget: Optional[Decimal] = None,
    exclude: Optional[set[str]] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create (or return) an AFM club for an agent with an affordable roster.

    Builds a rating-first squad within `budget` (XI + bench, legal by
    construction), sets the default lineup and marks catalog players owned.
    Used by demo seeding and by the owner seat's "create a manager" flow —
    any registered AFM agent owns exactly one club. `force` rebuilds the
    roster from scratch (releasing the old one).
    """
    with _lock:
        state = _state()
        existing = state.get("clubs", {}).get(agent_id)
        if existing and not force:
            return _club_out(agent_id, existing)

        formation = formation if formation in FORMATIONS else "4-3-3"
        budget = budget if budget is not None else STARTING_BUDGET_USDC
        exclude = set(exclude or set())
        if existing:
            exclude.update(existing.get("roster") or [])
            for pid in existing.get("roster") or []:
                try:
                    set_owner(pid, None)  # release before rebuilding
                except Exception:
                    pass

        roster = _auto_roster(formation, budget, exclude=exclude)
        rec = create_club(
            agent_id,
            club_name=club_name or club_name_for_agent(agent_id),
            starting_budget=budget,
        ).to_dict()
        rec["formation"] = formation
        rec["tactical_tags"] = ["balanced"]
        rec["roster"] = roster
        # legal default lineup = first 11 (covers all slots by construction)
        starters = roster[:STARTERS]
        bench = roster[STARTERS : STARTERS + MAX_BENCH]
        rec["starters"] = starters if len(starters) >= STARTERS else []
        rec["bench"] = bench
        for pid in roster:
            try:
                set_owner(pid, agent_id)
            except Exception:
                pass
        state.setdefault("clubs", {})[agent_id] = rec
        _save(state)
        return _club_out(agent_id, rec)


def seed_demo_clubs(*, force: bool = False) -> list[dict[str, Any]]:
    """Give every demo AFM manager agent a club with an affordable auto-roster.

    Prunes clubs whose owner is a *registered* agent that no longer plays AFM
    (e.g. the chess-only Raja / Nero demo bots) so football ownership stays
    clean and unique. Owner-created managers are registered AFM agents, so
    their clubs survive re-seeding.
    """
    with _lock:
        state = _state()
        agents = _afm_demo_agents()

        # drop clubs whose owner is a registered non-AFM agent (chess etc.)
        from gaming.src.stack.agentic.registry import get_registry

        reg = get_registry()
        registered = {a["agent_id"] for a in reg.list_agents()}
        afm_registered = {
            a["agent_id"]
            for a in reg.list_agents()
            if GAME_ID in (a.get("game_ids") or [])
            and (a.get("role") or "contestant") != "house"
        }
        stale = [aid for aid in state.get("clubs", {}) if aid in registered and aid not in afm_registered]
        if stale:
            for aid in stale:
                for pid in state["clubs"].get(aid, {}).get("roster") or []:
                    try:
                        set_owner(pid, None)  # release players back to the market
                    except Exception:
                        pass
                state["clubs"].pop(aid, None)
            _save(state)
            state = _state()

        owned: set[str] = set()
        for club in state.get("clubs", {}).values():
            owned.update(club.get("roster") or [])

        for a in agents:
            aid = a["agent_id"]
            club = state.get("clubs", {}).get(aid)
            if club and not force:
                owned.update(club.get("roster") or [])
                continue
            out = ensure_club_for_agent(
                aid,
                club_name=club_name_for_agent(aid),
                formation="4-3-3",
                budget=STARTING_BUDGET_USDC,
                exclude=owned,
                force=force,
            )
            # _club_out has no raw roster key — own the resolved squad ids
            owned.update(p["player_id"] for p in (out.get("squad") or []))
        return list_clubs()


def _club_out(aid: str, club: dict[str, Any]) -> dict[str, Any]:
    players = {p["player_id"]: p for p in list_players()}
    def resolve(ids: list[str]) -> list[dict[str, Any]]:
        out = []
        for pid in ids:
            p = players.get(pid)
            if p:
                out.append(copy.deepcopy(p))
        return out

    spend = sum(
        (_price(players.get(pid)) + Decimal(str(players.get(pid, {}).get("wage_per_matchday_usdc") or "0")) * WAGE_RUNWAY_MATCHDAYS)
        for pid in club.get("roster", [])
        if pid in players
    )
    return {
        "agent_id": aid,
        "club_name": club.get("club_name") or club_name_for_agent(aid),
        "budget_usdc": club.get("budget_usdc"),
        "spend_usdc": str(spend),
        "formation": club.get("formation") or "4-3-3",
        "tactical_tags": list(club.get("tactical_tags") or ["balanced"]),
        "roster_size": len(club.get("roster") or []),
        "starters": resolve(club.get("starters") or []),
        "bench": resolve(club.get("bench") or []),
        "squad": resolve(club.get("roster") or []),
    }


def list_clubs() -> list[dict[str, Any]]:
    with _lock:
        state = _state()
        return [_club_out(aid, club) for aid, club in state.get("clubs", {}).items()]


def get_club(agent_id: str) -> Optional[dict[str, Any]]:
    club = _club_for_agent(agent_id)
    return _club_out(agent_id, club) if club else None


def set_lineup(
    agent_id: str,
    *,
    formation: Optional[str] = None,
    starters: Optional[list[str]] = None,
    bench: Optional[list[str]] = None,
    tactical_tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Set a club's lineup + tactics (agent's afm_set_lineup). Validates hard rules."""
    with _lock:
        club = _club_for_agent(agent_id)
        if not club:
            raise ValueError("agent has no AFM club — seed demo clubs first")
        roster = set(club.get("roster") or [])

        if formation is not None and formation not in FORMATIONS:
            raise ValueError(f"formation not allowed: {formation} (use one of {', '.join(FORMATIONS)})")
        if tactical_tags is not None:
            for t in tactical_tags:
                if t not in TACTICAL_TAGS:
                    raise ValueError(f"unknown tactical tag: {t} (use one of {', '.join(TACTICAL_TAGS)})")

        if starters is not None:
            ids = list(dict.fromkeys(starters))
            if len(ids) != STARTERS:
                raise ValueError(f"a legal XI needs exactly {STARTERS} starters (got {len(ids)})")
            unknown = [p for p in ids if p not in roster]
            if unknown:
                raise ValueError(f"starters not owned by this club: {unknown}")
            injured = [p for p in ids if (_resolve(p) or {}).get("injury")]
            banned = [p for p in ids if int((_resolve(p) or {}).get("suspension_matches") or 0) > 0]
            if injured:
                raise ValueError(f"injured players cannot start: {injured}")
            if banned:
                raise ValueError(f"suspended players cannot start: {banned}")
            has_gk = any(str((_resolve(p) or {}).get("slot") or "").upper() == "GK" for p in ids)
            if not has_gk:
                raise ValueError("the XI must include exactly one GK (slot GK)")
            club["starters"] = ids
            if bench is not None:
                bl = list(dict.fromkeys(bench))
                if len(bl) > MAX_BENCH:
                    raise ValueError(f"bench limited to {MAX_BENCH} players (got {len(bl)})")
                unknown_b = [p for p in bl if p not in roster]
                if unknown_b:
                    raise ValueError(f"bench players not owned by this club: {unknown_b}")
                overlap = set(bl) & set(ids)
                if overlap:
                    raise ValueError(f"players cannot be both starters and bench: {sorted(overlap)}")
                club["bench"] = bl

        if formation is not None:
            club["formation"] = formation
        if tactical_tags is not None:
            club["tactical_tags"] = list(tactical_tags) or ["balanced"]

        state = _state()
        state.setdefault("clubs", {})[agent_id] = club
        _save(state)
        return _club_out(agent_id, club)


def club_tactics(agent_id: str) -> tuple[str, list[str]]:
    club = _club_for_agent(agent_id)
    if not club:
        return "4-3-3", ["balanced"]
    return str(club.get("formation") or "4-3-3"), list(club.get("tactical_tags") or ["balanced"])


def _contract_years_left(player_id: str) -> int:
    """Deterministic 2–5y contract projection per player.

    There is no real contract ledger yet — like attributes, this is a stable
    derived value (same player → same years left) so the FM-style squad screen
    can show a contract column without inventing stored data.
    """
    h = hashlib.sha256(f"afm:contract:{player_id}".encode("utf-8")).digest()
    return 2 + int.from_bytes(h[:4], "big") % 4


def squad_view(agent_id: str) -> list[dict[str, Any]]:
    """FM-style enriched squad for a club's squad screen.

    One record per rostered player with: derived attributes (via
    `attributes.derive_profile` — deterministic per player), form / fitness /
    morale, status (starter | bench | squad from the locked lineup), wage +
    value, and a derived contract projection. Ordered starter → bench → squad,
    then rating desc — the FM squad-table default.
    """
    from gaming.src.stack.agentic.games.football_managers.attributes import derive_profile
    from gaming.src.stack.agentic.games.football_managers.roles import role_suitability
    from gaming.src.stack.agentic.games.football_managers.rules import WAGE_RUNWAY_MATCHDAYS

    club = _club_for_agent(agent_id)
    if not club:
        return []
    starters = list(club.get("starters") or [])
    bench = list(club.get("bench") or [])
    status_of: dict[str, str] = {pid: "starter" for pid in starters}
    for pid in bench:
        status_of[pid] = "bench"
    players = {p["player_id"]: p for p in list_players()}

    rows: list[dict[str, Any]] = []
    carried = current_condition(agent_id)  # G4: condition carried from the last fixture
    for pid in club.get("roster") or []:
        p = players.get(pid)
        if not p:
            continue
        attrs = derive_profile(p)
        condition = carried.get(pid)
        rows.append(
            {
                **copy.deepcopy(p),
                "status": status_of.get(pid, "squad"),
                "attributes": {k: round(float(v), 1) for k, v in attrs.items()},
                "fitness": round(float(condition if condition is not None else attrs.get("fitness", 1.0)), 2),
                "condition": round(float(condition), 2) if condition is not None else None,
                "morale": round(float(attrs.get("morale", 0.7)), 2),
                "roles": role_suitability(str(p.get("slot") or "CM"), attrs),
                "contract": {
                    "years_left": _contract_years_left(pid),
                    "wage_usdc": str(p.get("wage_per_matchday_usdc") or "0"),
                    "value_usdc": str(p.get("game_price_usdc") or "0"),
                    "runway_matchdays": int(WAGE_RUNWAY_MATCHDAYS),
                },
            }
        )

    rank = {"starter": 0, "bench": 1, "squad": 2}
    rows.sort(key=lambda r: (rank.get(r["status"], 3), -int(r.get("base_rating") or 0)))
    return rows
