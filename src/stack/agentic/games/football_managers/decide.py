"""AFM manager decision loop — agents set their lineup before each deadline.

Before a matchday locks, each manager *decides* its own formation, XI,
bench and tactical tags instead of relying on whatever was last saved. The
decision is driven by the manager's mind (archetype) and the season context
(next opponent, standings):

  striker    (Blue Lock)   — stars over system: highest-rated XI, attack-first
                             shapes (3-4-3 / 4-3-3), never parks the bus.
  tactician  (Ao Ashi)     — system over stars: position-disciplined XI,
                             balanced shapes (4-2-3-1 / 4-1-4-1), reads the
                             opponent's tag (counter an aggressive side, keep
                             the ball against a bus).
  pragmatist               — low block + counters: 5-3-2 / 4-1-4-1, absorbs
                             pressure and hits on the break.
  possession               — keep the ball: tiki-taka shapes, patient
                             buildup, counter only when chased.
  balanced                 — mid-block solo-brain: 4-3-3 / 4-2-3-1 with always
                             one pivot, position-disciplined XI, presses
                             poor first touches, counters aggressive sides.

Each strategy's `tags` list is ordered base-tag first, reactive-tag last:
when trailing or facing an aggressive side the manager switches to the
reactive tag, otherwise it stays on its base tag. `pick` controls XI
selection: `rating` (best-rated, loose position fit) or `shape`
(position-disciplined, exact-slot first).

v1.4 additions:
  * condition-aware XI — selection ranks by rating * current condition, so
    exhausted stars rotate to the bench and fresh legs start (a 92-rated
    player at condition 0.55 loses his place to a fit 88).
  * `instructions` — a one-line tactical note carried with the plan (rendered
    by the feed, echoed in the matchday ask).
  * `plans` — half-time contingency plans keyed by game state
    ({"trailing"|"level"|"leading"}: {formation, tags, mentality}); the
    engine applies the plan the HT score calls for, so managers adjust at
    the break without a live webhook round-trip.

decide_matchday() is pure and deterministic given the season + club state,
so the tests and the live keeper observe identical behaviour. The decision
runs exactly once per matchday (at open); a human edit after open — before
the deadline — still wins for that matchday.

decide_matchday() is pure and deterministic given the season + club state,
so the tests and the live keeper observe identical behaviour. The decision
runs exactly once per matchday (at open); a human edit after open — before
the deadline — still wins for that matchday.
"""
from __future__ import annotations

from typing import Any, Optional

# archetype -> strategy. mind["archetype"] picks one; fallback by agent_id
# substring keeps any future manager playable without a mind entry.
STRATEGIES: dict[str, dict[str, Any]] = {
    "striker": {
        "formations": ["3-4-3", "4-3-3", "4-2-3-1"],
        "tags": ["gegenpress", "high_press"],
        "pick": "rating",  # best-rated XI, loose position fit
    },
    "tactician": {
        "formations": ["4-2-3-1", "4-1-4-1", "4-3-3"],
        "tags": ["tiki_taka", "counter"],
        "pick": "shape",  # position-disciplined XI, exact-slot first
    },
    "pragmatist": {
        "formations": ["5-3-2", "4-1-4-1", "4-4-2"],
        "tags": ["low_block", "counter"],
        "pick": "shape",
    },
    "possession": {
        "formations": ["4-3-3", "4-2-3-1", "4-1-4-1"],
        "tags": ["tiki_taka", "counter"],
        "pick": "shape",
    },
    "balanced": {
        "formations": ["4-3-3", "4-2-3-1", "4-1-4-1"],
        "tags": ["high_press", "counter"],
        "pick": "shape",
    },
}

MAX_BENCH = 5

# condition below which a starter is considered exhausted and rotates out
# (unless the squad is too thin to replace him)
FATIGUE_ROTATION_THRESHOLD = 0.62

# half-time contingency plans per archetype: game-state -> tactics tweak.
# mentality is the lever the engine actually feels; the formation change is
# the story the fans see in the feed's tactical_change event.
HT_PLANS: dict[str, dict[str, dict[str, Any]]] = {
    "striker": {
        "trailing": {"formation": "3-4-3", "tags": ["high_press"], "mentality": "attacking"},
        "level": {"formation": "4-3-3", "tags": ["high_press"], "mentality": "attacking"},
        "leading": {"formation": "4-2-3-1", "tags": ["counter"], "mentality": "balanced"},
    },
    "tactician": {
        "trailing": {"formation": "4-1-4-1", "tags": ["high_press"], "mentality": "attacking"},
        "level": {"formation": "4-2-3-1", "tags": ["tiki_taka"], "mentality": "balanced"},
        "leading": {"formation": "4-1-4-1", "tags": ["low_block"], "mentality": "defensive"},
    },
    "pragmatist": {
        "trailing": {"formation": "4-4-2", "tags": ["long_ball"], "mentality": "attacking"},
        "level": {"formation": "5-3-2", "tags": ["counter"], "mentality": "balanced"},
        "leading": {"formation": "5-3-2", "tags": ["park_bus"], "mentality": "defensive"},
    },
    "possession": {
        "trailing": {"formation": "4-3-3", "tags": ["tiki_taka"], "mentality": "attacking"},
        "level": {"formation": "4-3-3", "tags": ["tiki_taka"], "mentality": "balanced"},
        "leading": {"formation": "4-2-3-1", "tags": ["tiki_taka"], "mentality": "defensive"},
    },
    "balanced": {
        "trailing": {"formation": "4-4-2", "tags": ["high_press"], "mentality": "attacking"},
        "level": {"formation": "4-3-3", "tags": ["balanced"], "mentality": "balanced"},
        "leading": {"formation": "4-2-3-1", "tags": ["counter"], "mentality": "defensive"},
    },
}

_GROUP_OF = {
    "GK": "GK",
    "RB": "DEF", "CB": "DEF", "LB": "DEF",
    "CDM": "MID", "CM": "MID", "CAM": "MID",
    "RW": "FWD", "ST": "FWD", "LW": "FWD",
}


def _mind_for(agent_id: str) -> dict[str, Any]:
    from gaming.src.stack.agentic.registry import get_registry

    try:
        rec = get_registry().get_agent(agent_id) or {}
    except Exception:
        rec = {}
    mind = dict(rec.get("mind") or {})
    if not mind.get("archetype"):
        mind["archetype"] = "striker" if "bluelock" in agent_id.lower() else "tactician"
    return mind


def _club_players(agent_id: str) -> list[dict[str, Any]]:
    """Owned squad (resolved dicts), healthy and available only."""
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    club = get_club(agent_id) or {}
    out: list[dict[str, Any]] = []
    for p in club.get("squad") or []:
        if p.get("injury"):
            continue
        if int(p.get("suspension_matches") or 0) > 0:
            continue
        out.append(p)
    return out


def _avg_rating(players: list[dict[str, Any]]) -> float:
    rs = [float(p.get("base_rating") or 70) for p in players]
    return sum(rs) / len(rs) if rs else 70.0


def _cond_of(p: dict[str, Any], condition: dict[str, float]) -> float:
    """A player's current condition (0..1); fresh when unrecorded."""
    c = condition.get(str(p.get("player_id") or ""))
    return float(c) if c is not None else 1.0


def _pick_xi_conditioned(
    players: list[dict[str, Any]],
    formation: str,
    style: str,
    condition: dict[str, float],
) -> list[str]:
    """`_pick_xi`, but selection ranks by rating * condition (v1.4 rotation).

    An exhausted star (condition below FATIGUE_ROTATION_THRESHOLD and beaten
    on effective rating by a teammate for the same slot) drops to the bench;
    the ranking still guarantees a legal XI when the squad is thin.
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        _formation_slots,
    )

    slots = _formation_slots(formation)
    effective = {
        str(p["player_id"]): float(p.get("base_rating") or 70)
        * max(0.35, _cond_of(p, condition))
        for p in players
    }

    def key(p: dict[str, Any]) -> tuple[float, float]:
        pid = str(p["player_id"])
        return (effective.get(pid, 0.0), float(p.get("real_value_usd") or 0))

    by_slot: dict[str, list[dict[str, Any]]] = {}
    by_group: dict[str, list[dict[str, Any]]] = {}
    for p in players:
        by_slot.setdefault(str(p.get("slot") or "").upper(), []).append(p)
        by_group.setdefault(str(p.get("primary_pos") or "MID").upper(), []).append(p)
    for lst in by_slot.values():
        lst.sort(key=key, reverse=True)
    for lst in by_group.values():
        lst.sort(key=key, reverse=True)
    by_rating = sorted(players, key=key, reverse=True)

    # v1.4 rotation policy: an exhausted player (condition below the
    # threshold) who is beaten on effective rating by a same-slot teammate
    # sits this one out — the slot belongs to the fitter legs. He stays
    # eligible for the last-resort legality fill, never for a normal slot.
    rotated_out: set[str] = set()
    for pid, lst in by_slot.items():
        if pid == "GK":
            continue
        for p in lst:
            pp = str(p["player_id"])
            if _cond_of(p, condition) >= FATIGUE_ROTATION_THRESHOLD:
                continue
            if any(
                str(q["player_id"]) != pp and effective.get(str(q["player_id"]), 0.0) > effective.get(pp, 0.0)
                for q in lst
            ):
                rotated_out.add(pp)

    def live(lst: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [p for p in lst if str(p["player_id"]) not in rotated_out]

    used: set[str] = set()
    xi: list[str] = []

    def take(p: Optional[dict[str, Any]]) -> bool:
        if not p or p["player_id"] in used:
            return False
        used.add(p["player_id"])
        xi.append(p["player_id"])
        return True

    def first_free(lst: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return next((p for p in lst if p["player_id"] not in used), None)

    for need in slots:
        got: Optional[dict[str, Any]] = None
        if style == "shape":
            got = first_free(live(by_slot.get(need, [])))
            if not got:
                got = first_free(live(by_group.get(_GROUP_OF.get(need, "MID"), [])))
        else:
            group = _GROUP_OF.get(need, "MID")
            if need in by_slot:
                got = first_free(live(by_slot[need]))
            if not got:
                got = first_free(live(by_group.get(group, [])))
        if not got:
            got = next((p for p in live(by_rating) if p["player_id"] not in used), None)
        if got:
            take(got)

    if len(xi) < 11:
        # legality beats policy: thin squads may still need the tired legs
        for p in by_rating:
            if len(xi) >= 11:
                break
            take(p)
    if len(xi) != 11:
        raise ValueError(f"{formation} needs exactly 11 starters — squad has {len(players)} available")
    return xi


def _pick_xi(players: list[dict[str, Any]], formation: str, style: str) -> list[str]:
    """A legal 11 from the club's own squad for the formation's slots.

    `rating` style: best-rated players, loose position fit (stars over
    system). `shape` style: exact-slot first, then group, then any (system
    over stars). Always exactly 11 with a GK, drawn only from owned players.
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        _formation_slots,
    )

    slots = _formation_slots(formation)
    by_slot: dict[str, list[dict[str, Any]]] = {}
    by_group: dict[str, list[dict[str, Any]]] = {}
    for p in players:
        by_slot.setdefault(str(p.get("slot") or "").upper(), []).append(p)
        by_group.setdefault(str(p.get("primary_pos") or "MID").upper(), []).append(p)
    key = lambda p: (float(p.get("base_rating") or 0), float(p.get("real_value_usd") or 0))
    for lst in by_slot.values():
        lst.sort(key=key, reverse=True)
    for lst in by_group.values():
        lst.sort(key=key, reverse=True)
    by_rating = sorted(players, key=key, reverse=True)

    used: set[str] = set()
    xi: list[str] = []

    def take(p: Optional[dict[str, Any]]) -> bool:
        if not p or p["player_id"] in used:
            return False
        used.add(p["player_id"])
        xi.append(p["player_id"])
        return True

    def first_free(lst: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return next((p for p in lst if p["player_id"] not in used), None)

    for need in slots:
        got: Optional[dict[str, Any]] = None
        if style == "shape":
            got = first_free(by_slot.get(need, []))
            if not got:
                got = first_free(by_group.get(_GROUP_OF.get(need, "MID"), []))
        else:  # rating: best-rated player that fits the slot's group
            group = _GROUP_OF.get(need, "MID")
            if need in by_slot:
                got = first_free(by_slot[need])
            if not got:
                got = first_free(by_group.get(group, []))
        if not got:  # any remaining player (position be damned)
            got = next((p for p in by_rating if p["player_id"] not in used), None)
        if got:
            take(got)

    # never leave a club short of a legal XI (auto-rosters cover all slots)
    if len(xi) < 11:
        for p in by_rating:
            if len(xi) >= 11:
                break
            take(p)
    if len(xi) != 11:
        raise ValueError(f"{formation} needs exactly 11 starters — squad has {len(players)} available")
    return xi


def _bench(players: list[dict[str, Any]], xi: list[str]) -> list[str]:
    used = set(xi)
    rest = [p for p in players if p["player_id"] not in used]
    rest.sort(key=lambda p: (float(p.get("base_rating") or 0), float(p.get("real_value_usd") or 0)), reverse=True)
    # keep a keeper on the bench when possible (sensible + legal)
    bench = [p["player_id"] for p in rest if str(p.get("slot") or "").upper() == "GK"][:1]
    for p in rest:
        if len(bench) >= MAX_BENCH:
            break
        if p["player_id"] in bench:
            continue
        bench.append(p["player_id"])
    return bench


def matchday_context(
    agent_id: str,
    season: dict[str, Any],
    matchday: int,
) -> Optional[dict[str, Any]]:
    """Public context the House builds for a manager's matchday decision.

    Everything here is *observable* state (own squad, opposition lineup +
    record, standings) — never the opponent's hidden mind sliders. Returns
    None when the club has a bye or no playable squad. This is what the
    webhook ask payload is built from (see manager_protocol).
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.league import schedule_season

    club = get_club(agent_id) or {}
    players = _club_players(agent_id)
    if not players:
        return None

    sched = schedule_season(season["division"])
    fixtures = sched[matchday - 1] if 0 <= matchday - 1 < len(sched) else []
    fx = next((f for f in fixtures if agent_id in (f.home_agent_id, f.away_agent_id)), None)
    if fx is None:  # bye — nothing to decide
        return None
    opponent_id = fx.away_agent_id if fx.home_agent_id == agent_id else fx.home_agent_id

    opp_club = get_club(opponent_id) or {}
    opp_starters = [p for p in (opp_club.get("starters") or []) if isinstance(p, dict)]
    opp_players = opp_starters or _club_players(opponent_id)
    opp_avg = _avg_rating(opp_players)
    own_avg = _avg_rating(players)
    standings = season.get("standings") or {}
    own_pts = int((standings.get(agent_id) or {}).get("points") or 0)
    opp_pts = int((standings.get(opponent_id) or {}).get("points") or 0)
    opp_tags = list(opp_club.get("tactical_tags") or ["balanced"])
    opp_tag = opp_tags[0] if opp_tags else "balanced"

    return {
        "club": club,
        "players": players,
        "opponent_id": opponent_id,
        "opp_club": opp_club,
        "opp_players": opp_players,
        "own_avg": own_avg,
        "opp_avg": opp_avg,
        "own_pts": own_pts,
        "opp_pts": opp_pts,
        "opp_tag": opp_tag,
        "stronger": opp_avg > own_avg or opp_pts > own_pts,
        "trailing": opp_pts > own_pts,
        "home_agent": fx.home_agent_id,
        "away_agent": fx.away_agent_id,
    }


def plan_for_strategy(
    arch: str,
    players: list[dict[str, Any]],
    *,
    own_avg: float,
    opp_avg: float,
    own_pts: int,
    opp_pts: int,
    opp_tag: str,
    condition: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """One manager's plan from its archetype strategy + observable context.

    Shared by the in-process `decide_matchday` and the webhook servers'
    `decide_from_ask`, so the demo managers answer the ask with exactly the
    same mind the House would have used for them. `condition` (0..1 per
    player) drives v1.4 rotation: exhausted stars drop below fresh legs.
    """
    strat = STRATEGIES.get(arch or "", STRATEGIES["tactician"])
    formations = strat["formations"]
    tags = list(strat.get("tags") or ["balanced"])
    stronger = opp_avg > own_avg or opp_pts > own_pts
    trailing = opp_pts > own_pts
    plans = dict(HT_PLANS.get(arch or "") or HT_PLANS["tactician"])
    instructions: Optional[str] = None

    if strat["pick"] == "rating":
        # striker's ego: never park the bus; press everything
        formation = formations[0] if not stronger else formations[1]
        if trailing:
            tags = [tags[0]]
        elif opp_tag in ("park_bus", "low_block"):
            tags = [tags[-1]]
        else:
            tags = [tags[0]]
    elif arch == "balanced":
        # Match-Slice: mid-block solo-brain — holds the 4-3-3 base against a
        # peer, adds a second pivot (4-2-3-1) against a stronger side, and
        # counters when the opponent presses or we are trailing.
        formation = formations[0] if not stronger else formations[1]
        if trailing or opp_tag in ("gegenpress", "high_press"):
            tags = [tags[-1]]
        else:
            tags = [tags[0]]
    else:
        # system managers read the opponent: counter an aggressive or
        # trailing fixture, otherwise hold their base shape + tag
        formation = formations[0] if not stronger else formations[1]
        if trailing or opp_tag in ("gegenpress", "high_press", "counter"):
            tags = [tags[-1]]
        else:
            tags = [tags[0]]

    instructions = f"{formation}, {tags[0]}"
    if condition:
        xi = _pick_xi_conditioned(players, formation, strat["pick"], condition)
    else:
        xi = _pick_xi(players, formation, strat["pick"])
    bench = _bench(players, xi)
    return {
        "formation": formation,
        "starters": xi,
        "bench": bench,
        "tags": tags,
        "instructions": instructions,
        "plans": plans,
    }


def decide_matchday(
    agent_id: str,
    season: dict[str, Any],
    matchday: int,
) -> Optional[dict[str, Any]]:
    """The manager's plan for `matchday` — None when the club has a bye.

    Deterministic given the season + club state. Never raises for missing
    context — callers (the season tick) keep the saved lineup on any error.
    """
    ctx = matchday_context(agent_id, season, matchday)
    if not ctx:
        return None
    mind = _mind_for(agent_id)
    arch = str(mind.get("archetype") or "")
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        current_condition,
    )
    return plan_for_strategy(
        arch,
        ctx["players"],
        own_avg=ctx["own_avg"],
        opp_avg=ctx["opp_avg"],
        own_pts=ctx["own_pts"],
        opp_pts=ctx["opp_pts"],
        opp_tag=ctx["opp_tag"],
        condition=current_condition(agent_id),
    )


def _players_from_ask(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize ask payload player entries into the engine's player shape."""
    out: list[dict[str, Any]] = []
    for e in entries:
        slot = str(e.get("position") or e.get("slot") or "MID").upper()
        out.append(
            {
                "player_id": str(e.get("player_id") or ""),
                "name": str(e.get("name") or ""),
                "slot": slot,
                "primary_pos": slot,
                "base_rating": float(e.get("rating") or e.get("base_rating") or 70),
                "real_value_usd": float(e.get("value_usd") or 0),
            }
        )
    return out


def decide_from_ask(
    arch: str,
    ask: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """A webhook-served manager's answer, derived *only* from the ask payload.

    This is what demo manager servers (Blue Lock / Ao Ashi) run to reply to
    the House's matchday ask: same archetype strategy, same XI/tag rules as
    the deterministic path, but fed purely by what the House told them — own
    squad + the opposition lineup (never the opponent's hidden sliders).
    """
    my = (ask or {}).get("my_club") or {}
    opp = (ask or {}).get("opposition") or {}
    squad = _players_from_ask(my.get("squad") or [])
    if not squad:
        return None
    opp_lineup = _players_from_ask(opp.get("lineup") or [])
    own_avg = _avg_rating(squad)
    opp_avg = _avg_rating(opp_lineup) if opp_lineup else own_avg
    own_pts = int((my.get("record") or {}).get("points") or 0)
    opp_pts = int((opp.get("record") or {}).get("points") or 0)
    opp_tags = list(opp.get("tactical_tags") or ["balanced"])
    opp_tag = opp_tags[0] if opp_tags else "balanced"
    return plan_for_strategy(
        arch,
        squad,
        own_avg=own_avg,
        opp_avg=opp_avg,
        own_pts=own_pts,
        opp_pts=opp_pts,
        opp_tag=opp_tag,
    )