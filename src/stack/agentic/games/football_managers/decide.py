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
  youth_dev                — the academy: fresh legs earn minutes, energetic
                             pressing shapes, heavy rotation for condition.
  galactico                — stars and only stars: all-out attack shapes,
                             best-rated XI whatever the slot.
  catenaccio               — the wall: parked-bus base, absorbs everything,
                             steals the 1-0.
  tinkerer                 — chaos as a brand: a new shape almost every
                             matchday, reads nobody, springs surprises.

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

v1.5 additions (manager variety engine):
  * matchday rotation — from matchday 2 the formation ranges across the
    archetype's shape list (seeded, core shape still the plurality pick)
    instead of freezing on formations[0]/[1] all season.
  * opponent reads — managers read the opposition's observable shape/tag
    and most matchdays line up a shape that punishes it: overloads against
    a back five, a creator between the lines against a bus, a bypass
    against a high press.
  * surprise shapes — rarely a manager springs a shape from outside its
    core list. All of it is seeded per (season, matchday, manager), so
    decide_matchday stays deterministic and the webhook brain
    (decide_from_ask) reproduces the House's exact plan from the ask alone.

decide_matchday() is pure and deterministic given the season + club state,
so the tests and the live keeper observe identical behaviour. The decision
runs exactly once per matchday (at open); a human edit after open — before
the deadline — still wins for that matchday.
"""
from __future__ import annotations

import hashlib
import random
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
    "youth_dev": {
        "formations": ["4-1-4-1", "4-4-2", "4-2-3-1"],
        "tags": ["high_press", "counter"],
        "pick": "shape",  # legs over logos: fresh condition earns minutes
    },
    "galactico": {
        "formations": ["3-4-3", "4-3-3", "3-5-2"],
        "tags": ["gegenpress", "long_ball"],
        "pick": "rating",  # stars, and only stars
    },
    "catenaccio": {
        "formations": ["5-3-2", "4-1-4-1", "4-4-2"],
        "tags": ["park_bus", "low_block"],
        "pick": "shape",
    },
    "tinkerer": {
        "formations": ["4-4-2", "3-5-2", "4-2-3-1"],
        "tags": ["long_ball", "balanced"],
        "pick": "shape",
        # chaos knobs: he rarely reads the opponent and springs surprises hard
        "read_follow_prob": 0.4,
        "surprise_prob": 0.45,
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
    "youth_dev": {
        "trailing": {"formation": "4-4-2", "tags": ["high_press"], "mentality": "attacking"},
        "level": {"formation": "4-1-4-1", "tags": ["high_press"], "mentality": "balanced"},
        "leading": {"formation": "4-2-3-1", "tags": ["counter"], "mentality": "defensive"},
    },
    "galactico": {
        "trailing": {"formation": "3-4-3", "tags": ["gegenpress"], "mentality": "attacking"},
        "level": {"formation": "3-4-3", "tags": ["long_ball"], "mentality": "attacking"},
        "leading": {"formation": "4-3-3", "tags": ["counter"], "mentality": "balanced"},
    },
    "catenaccio": {
        "trailing": {"formation": "4-4-2", "tags": ["long_ball"], "mentality": "attacking"},
        "level": {"formation": "5-3-2", "tags": ["low_block"], "mentality": "balanced"},
        "leading": {"formation": "5-3-2", "tags": ["park_bus"], "mentality": "defensive"},
    },
    "tinkerer": {
        "trailing": {"formation": "3-5-2", "tags": ["long_ball"], "mentality": "attacking"},
        "level": {"formation": "4-4-2", "tags": ["balanced"], "mentality": "balanced"},
        "leading": {"formation": "4-2-3-1", "tags": ["counter"], "mentality": "defensive"},
    },
}

# ---------------------------------------------------------------- variety (v1.5)
# From matchday 2 a manager's shape stops freezing on formations[0]/[1].
# One seeded roll per (season, matchday, manager) picks the flavour: an
# opponent read usually wins, a surprise shape is rare, otherwise the
# manager rotates across its core list with the base shape still favourite.

ROTATION_WEIGHTS = (0.5, 0.3, 0.2)  # share across the archetype's shape list
READ_FOLLOW_PROB = 0.64  # chance a matched opponent read is followed
SURPRISE_PROB = 0.12  # chance of a shape from outside the core list

# Shapes a manager can spring as a surprise — deliberately outside its core
# list (a striker parking in 3-5-2, a pragmatist venturing into 4-3-3).
SURPRISE_FORMATIONS: dict[str, list[str]] = {
    "striker": ["3-5-2"],
    "tactician": ["4-4-2", "3-4-3"],
    "pragmatist": ["4-3-3"],
    "possession": ["3-5-2", "4-4-2"],
    "balanced": ["3-5-2", "3-4-3"],
    "youth_dev": ["3-5-2", "4-3-3"],
    "galactico": ["4-2-3-1", "4-4-2"],
    "catenaccio": ["3-5-2"],  # the bus, but with a midfield under it
    "tinkerer": ["5-3-2", "3-4-3", "4-3-3"],
}

# Opponent reads -> shapes that punish the read, per archetype, in preference
# order. Triggers come from the opposition's observable formation (back three
# or back five) or its tactical tag.
REACTIVE_FORMATIONS: dict[str, dict[str, list[str]]] = {
    "striker": {
        "back_five": ["4-3-3", "4-2-3-1"],  # width plus a No.10 between the lines
        "back_three": ["4-4-2", "3-4-3"],  # two strikers pin the back three
        "high_press": ["4-4-2", "3-4-3"],  # meet fire with fire, go direct
        "low_block": ["4-2-3-1", "4-3-3"],  # a creator to unlock the bus
        "counter": ["4-3-3", "4-2-3-1"],  # pin them deep, body between the lines
    },
    "tactician": {
        "back_five": ["4-2-3-1", "4-3-3"],
        "back_three": ["4-3-3", "4-2-3-1"],
        "high_press": ["4-1-4-1", "4-2-3-1"],  # pivot protection, play through
        "low_block": ["4-1-4-1", "4-2-3-1"],
        "counter": ["4-2-3-1", "4-1-4-1"],
    },
    "pragmatist": {
        "back_five": ["4-4-2", "4-1-4-1"],
        "back_three": ["4-1-4-1", "4-4-2"],
        "high_press": ["5-3-2", "4-1-4-1"],  # absorb the press, hit back
        "low_block": ["4-1-4-1", "4-4-2"],
        "counter": ["5-3-2", "4-1-4-1"],
    },
    "possession": {
        "back_five": ["4-3-3", "4-2-3-1"],
        "back_three": ["4-3-3", "4-1-4-1"],
        "high_press": ["4-3-3", "4-1-4-1"],
        "low_block": ["4-2-3-1", "4-3-3"],
        "counter": ["4-1-4-1", "4-3-3"],
    },
    "balanced": {
        "back_five": ["4-2-3-1", "4-3-3"],
        "back_three": ["4-3-3", "4-4-2"],
        "high_press": ["4-2-3-1", "4-1-4-1"],
        "low_block": ["4-2-3-1", "4-3-3"],
        "counter": ["4-3-3", "4-1-4-1"],
    },
    "youth_dev": {
        "back_five": ["4-2-3-1", "4-1-4-1"],
        "back_three": ["4-4-2", "4-1-4-1"],
        "high_press": ["4-1-4-1", "4-4-2"],  # out-run the pressers
        "low_block": ["4-2-3-1", "4-4-2"],
        "counter": ["4-1-4-1", "4-4-2"],
    },
    "galactico": {
        "back_five": ["3-4-3", "4-3-3"],
        "back_three": ["4-3-3", "3-4-3"],
        "high_press": ["4-3-3", "3-4-3"],  # meet fire with fire
        "low_block": ["4-3-3", "3-5-2"],
        "counter": ["3-4-3", "4-3-3"],
    },
    "catenaccio": {
        "back_five": ["5-3-2", "4-1-4-1"],
        "back_three": ["5-3-2", "4-1-4-1"],
        "high_press": ["5-3-2", "4-1-4-1"],  # let them tire against the wall
        "low_block": ["4-1-4-1", "5-3-2"],
        "counter": ["5-3-2", "4-1-4-1"],
    },
    "tinkerer": {
        "back_five": ["3-5-2", "4-2-3-1"],
        "back_three": ["4-4-2", "3-5-2"],
        "high_press": ["4-2-3-1", "3-5-2"],
        "low_block": ["4-4-2", "3-5-2"],
        "counter": ["3-5-2", "4-4-2"],
    },
}

# How the feed phrases a followed read.
READ_LABELS: dict[str, str] = {
    "back_five": "spreading their back five",
    "back_three": "attacking the back three",
    "high_press": "bypassing the press",
    "low_block": "breaking down the bus",
    "counter": "covering the counter",
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
        # group buckets must be keyed by the slot's GROUP (DEF/MID/FWD) — the
        # catalog's primary_pos is a specific slot ("CB"), so keying by it
        # raw made every group lookup miss and pushed fills into "any player"
        pos = str(p.get("primary_pos") or "MID").upper()
        by_group.setdefault(_GROUP_OF.get(pos, pos), []).append(p)
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
        if not got:  # last resort (see _pick_xi): keepers only when unavoidable
            left = [p for p in live(by_rating) if p["player_id"] not in used]
            got = next(
                (p for p in left if str(p.get("slot") or "").upper() != "GK"), None,
            ) or (left[0] if left else None)
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
        # group buckets must be keyed by the slot's GROUP (DEF/MID/FWD) — the
        # catalog's primary_pos is a specific slot ("CB"), so keying by it
        # raw made every group lookup miss and pushed fills into "any player"
        pos = str(p.get("primary_pos") or "MID").upper()
        by_group.setdefault(_GROUP_OF.get(pos, pos), []).append(p)
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
        if not got:  # any remaining player (position be damned) — but only
            # field a keeper as the very last resort: two GKs on the pitch is
            # not a formation, it is a bug
            left = [p for p in by_rating if p["player_id"] not in used]
            got = next(
                (p for p in left if str(p.get("slot") or "").upper() != "GK"), None,
            ) or (left[0] if left else None)
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
        "opp_formation": str(opp_club.get("formation") or ""),
        "stronger": opp_avg > own_avg or opp_pts > own_pts,
        "trailing": opp_pts > own_pts,
        "home_agent": fx.home_agent_id,
        "away_agent": fx.away_agent_id,
    }


def _seed_int(text: str) -> int:
    """Stable integer seed from a seed string (sha256 — never hash())."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def _variety_seed(season_no: int, matchday: int, agent_id: str) -> str:
    """The variety seed for one manager on one matchday — deterministic."""
    return f"afm-v1.5:{int(season_no or 1)}:{int(matchday or 1)}:{agent_id}"


def _weighted_pick(formations: list[str], rng: random.Random) -> str:
    """Pick from the archetype's core list; the base shape stays favourite."""
    if not formations:
        return "4-3-3"
    if len(formations) == 1:
        return formations[0]
    weights = list(ROTATION_WEIGHTS[: len(formations)])
    weights += [weights[-1]] * (len(formations) - len(weights))
    r = rng.random() * sum(weights)
    acc = 0.0
    for f, w in zip(formations, weights):
        acc += w
        if r < acc:
            return f
    return formations[-1]


def _read_opposition(
    arch: str, opp_formation: str, opp_tag: str
) -> tuple[str, list[str]]:
    """What a manager reads from the *observable* opposition setup.

    Returns (trigger, shapes): the opposition's back-line shape first, then
    its tag. The shapes punish the read and are always legal formations.
    """
    f = (opp_formation or "").strip()
    tag = (opp_tag or "").strip().lower()
    if f.startswith("5-"):
        trigger = "back_five"
    elif f.startswith("3-"):
        trigger = "back_three"
    elif tag in ("gegenpress", "high_press"):
        trigger = "high_press"
    elif tag in ("park_bus", "low_block"):
        trigger = "low_block"
    elif tag in ("counter", "long_ball"):
        trigger = "counter"
    else:
        return "", []
    return trigger, list(REACTIVE_FORMATIONS.get(arch or "", {}).get(trigger, []))


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
    seed: str = "",
    matchday: int = 1,
    opp_formation: str = "",
) -> dict[str, Any]:
    """One manager's plan from its archetype strategy + observable context.

    Shared by the in-process `decide_matchday` and the webhook servers'
    `decide_from_ask`, so the demo managers answer the ask with exactly the
    same mind the House would have used for them. `condition` (0..1 per
    player) drives v1.4 rotation: exhausted stars drop below fresh legs.

    v1.5 variety: with a `seed` and matchday > 1 the formation is rotated
    across the archetype's list, usually overridden by an opponent read
    (`opp_formation`/`opp_tag`), rarely a surprise shape. An empty `seed`
    or matchday 1 keeps the legacy single-shape pick.
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

    # v1.5 variety: one seeded roll decides the flavour of the base pick.
    note = ""
    if seed and int(matchday) > 1:
        rng = random.Random(_seed_int(seed))
        trigger, reads = _read_opposition(arch, opp_formation, opp_tag)
        # archetypes can carry their own chaos knobs (see the tinkerer)
        read_p = (float(strat.get("read_follow_prob") or READ_FOLLOW_PROB) if reads else 0.0)
        surprise_p = float(strat.get("surprise_prob") or SURPRISE_PROB)
        roll = rng.random()
        if reads and roll < read_p:
            formation = reads[rng.randrange(len(reads))]
            note = READ_LABELS[trigger]
        elif roll < read_p + surprise_p:
            pool = SURPRISE_FORMATIONS.get(arch or "", [])
            if pool:
                formation = pool[rng.randrange(len(pool))]
                note = "surprise shape"
        else:
            formation = _weighted_pick(formations, rng)

    instructions = f"{formation}, {tags[0]}" + (f" — {note}" if note else "")
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
        seed=_variety_seed(int(season.get("season_no") or 1), matchday, agent_id),
        matchday=int(matchday),
        opp_formation=str(ctx.get("opp_formation") or ""),
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
    matchday = int((ask or {}).get("matchday") or 1)
    asker = str((ask or {}).get("agent_id") or "")
    return plan_for_strategy(
        arch,
        squad,
        own_avg=own_avg,
        opp_avg=opp_avg,
        own_pts=own_pts,
        opp_pts=opp_pts,
        opp_tag=opp_tag,
        seed=_variety_seed(int((ask or {}).get("season_no") or 1), matchday, asker)
        if asker
        else "",
        matchday=matchday,
        opp_formation=str(opp.get("formation") or ""),
    )