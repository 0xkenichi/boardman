"""
AFM match simulation engine (Phase 0).

A headless, deterministic, event-sourced football match engine. Takes two
teams' XIs + benches + tactics (formation, mentality, role instructions,
set-piece takers) and simulates a complete match as a sequence of discrete,
timestamped events: kickoff, possession chains, passes, tackles /
interceptions, shots, goals, fouls, yellow/red cards, offside, corners,
throw-ins, goal kicks, substitutions, injuries, half-time, stoppage time,
full time and — when the competition requires a result — extra time and a
penalty shootout.

Design points (see the Phase 0 scope doc):

  * Deterministic core — every random draw goes through a single RNG seeded
    from the match_id; the same inputs reproduce an identical event log.
  * Player attributes meaningfully affect outcomes: shooting/positioning vs
    the keeper decide goals; pace vs defensive line height decides offside;
    tackling/physicality decide duels and fouls; pressing/aggression decide
    turnovers and cards; fitness drains through the match, morale rides form,
    and substitutions bring fresh legs.
  * Referee logic — offside calls, foul/card decisions (second yellow = red,
    red = the team plays on with ten), stoppage time derived from the events
    of each half.
  * The event log is the only output: a renderer can reconstruct the match,
    and a post-match stats summary is a pure fold over the log
    (`derive_stats`).
  * No knowledge of money, ownership, leagues or agents' internals.

Backward compatibility: `simulate_match(...)` keeps its original keyword
signature and MatchResult field set (score, feed, points, outcome, reason).
Benches, half-time tactical adjustments and `require_result` are optional
additions that default to the previous behaviour. Ordinary matches keep a
kickoff event first and a full_time event last at minute 90.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.attributes import (
    derive_profile,
    group_skill,
)
from gaming.src.stack.agentic.games.football_managers.catalog import get_player
from gaming.src.stack.agentic.games.football_managers.rules import (
    FORMATION_AGGRESSION,
    FORMATION_MODS,
    FORMATION_STYLE,
    POINTS_DRAW,
    POINTS_LOSS,
    POINTS_WIN,
    TAG_AGGRESSION,
    TAG_MODS,
)

# v1.4: weighted chance distribution (shots spread across the attacking pool,
# not one best attacker), assists + key passes, set-piece chances (corner
# headers, direct free kicks, in-play penalties), score-state adjustments
# (chasing sides push late, leaders manage the game), and half-time
# contingency plans (trailing/level/leading → the season passes the manager's
# pre-committed plan and the engine applies the one the HT score calls for).
ENGINE_VERSION = "afm-engine-v1.4"  # event-log schema version — bump deliberately

# Pitch model for the spatial overlay: x runs the length (home attacks toward
# x=100, away toward x=0), y runs the width, z is ball height in metres.
PITCH_LENGTH = 100.0
PITCH_WIDTH = 68.0
_GOAL_X = {"home": PITCH_LENGTH, "away": 0.0}
_SPOT_X = {"home": PITCH_LENGTH - 11.0, "away": 11.0}
# attacking third / box edges (length coords) for each side's own goal
_BOX_INNER = {"home": PITCH_LENGTH - 16.5, "away": 16.5}
_BOX_OUTER = {"home": PITCH_LENGTH, "away": 0.0}

MENTALITIES = ("balanced", "attacking", "defensive")
YELLOWS_TO_RED = 2
MAX_SUBS_90 = 3
MAX_SUBS_WITH_ET = 5
# manager substitution windows in the second half (55', 64', 72')
SUB_WINDOWS = (55, 64, 72)

_GROUP_OF_SLOT = {
    "GK": "GK",
    "RB": "DEF", "CB": "DEF", "LB": "DEF",
    "CDM": "MID", "CM": "MID", "CAM": "MID",
    "RW": "FWD", "ST": "FWD", "LW": "FWD",
}
# how much a player's attacking / midfield / defensive value feeds the side's
# department totals, by position group
_ATTACK_W = {"GK": 0.0, "DEF": 0.18, "MID": 0.5, "FWD": 1.0}
_MID_W = {"GK": 0.0, "DEF": 0.18, "MID": 1.0, "FWD": 0.3}
_DEF_W = {"GK": 0.2, "DEF": 1.0, "MID": 0.35, "FWD": 0.08}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _fmt(h: int, a: int) -> str:
    return f"{h}-{a}"


def _seed_int(match_id: str) -> int:
    h = hashlib.sha256(match_id.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


# ---------------------------------------------------------------- tactics


def _mentality_for(formation: str, tags: list[str]) -> str:
    """Default mentality when a manager didn't set one: derive from shape/tags."""
    style = FORMATION_STYLE.get(formation or "4-3-3", "balanced")
    if style == "attack":
        return "attacking"
    if style == "defensive":
        return "defensive"
    agg = FORMATION_AGGRESSION.get(formation or "4-3-3", 0.0) + sum(
        TAG_AGGRESSION.get(t, 0.0) for t in tags
    )
    if agg <= -0.25:
        return "defensive"
    if agg >= 0.3:
        return "attacking"
    return "balanced"


def _tag_mods(formation: str, tags: list[str]) -> dict[str, float]:
    """Department mods from formation class + tactical tags."""
    style = FORMATION_STYLE.get(formation or "4-3-3", "balanced")
    mods = dict(FORMATION_MODS.get(style, FORMATION_MODS["balanced"]))
    for tag in tags or []:
        m = TAG_MODS.get(tag)
        if m:
            for k in ("att", "mid", "def"):
                mods[k] *= m.get(k, 1.0)
    return mods


def _normalize_instructions(raw: Optional[dict[str, Any]]) -> dict[str, float]:
    """Role instructions → 0..1 intensities (1 = most committed / highest)."""
    lookup = {"low": 0.15, "mid": 0.5, "high": 0.9, "balanced": 0.5}
    names = ("pressing", "tempo", "line_height")
    out: dict[str, float] = {}
    r = dict(raw or {})
    for name in names:
        v = r.get(name, "mid")
        if isinstance(v, str):
            v = lookup.get(str(v).lower(), 0.5)
        out[name] = _clamp(float(v))
    return out


def _normalize_tactics(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    t = dict(raw or {})
    formation = str(t.get("formation") or "4-3-3")
    tags = [str(x) for x in (t.get("tags") or []) if str(x) in TAG_MODS] or ["balanced"]
    mentality = str(t.get("mentality") or "")
    if mentality not in MENTALITIES:
        mentality = _mentality_for(formation, tags)
    return {
        "formation": formation,
        "tags": tags,
        "mentality": mentality,
        "instructions": _normalize_instructions(t.get("instructions")),
        "set_pieces": dict(t.get("set_pieces") or {}),
    }


def _stance(formation: str, tags: list[str], mentality: str,
            instructions: dict[str, float]) -> dict[str, float]:
    """Aggression, pressing, line height, tempo for a side's stance."""
    style = FORMATION_STYLE.get(formation or "4-3-3", "balanced")
    agg = FORMATION_AGGRESSION.get(formation or "4-3-3", 0.0)
    agg += sum(TAG_AGGRESSION.get(t, 0.0) for t in tags)
    if mentality == "attacking":
        agg += 0.35
    elif mentality == "defensive":
        agg -= 0.35
    press = 0.30 + (0.22 if style == "attack" else -0.10 if style == "defensive" else 0.0)
    line = 0.42 + (0.22 if style == "attack" else -0.15 if style == "defensive" else 0.0)
    tempo = 0.5
    if mentality == "attacking":
        press += 0.22
        line += 0.18
        tempo += 0.14
    elif mentality == "defensive":
        press -= 0.12
        line -= 0.18
        tempo -= 0.10
    press += (instructions["pressing"] - 0.5) * 0.5
    line += (instructions["line_height"] - 0.5) * 0.5
    tempo += (instructions["tempo"] - 0.5) * 0.4
    return {
        "agg": max(-1.1, min(1.4, agg)),
        "press": _clamp(press, 0.05, 0.98),
        "line": _clamp(line, 0.08, 0.95),
        "tempo": _clamp(tempo, 0.1, 0.95),
    }


# ---------------------------------------------------------------- side state


@dataclass
class _SideState:
    agent_id: str
    xi: list[str]
    bench: list[str]
    tactics: dict[str, Any]
    stance: dict[str, float]
    profiles: dict[str, dict[str, float]] = field(default_factory=dict)
    on_pitch: list[str] = field(default_factory=list)
    off: list[str] = field(default_factory=list)
    yellows: dict[str, int] = field(default_factory=dict)
    subs_used: int = 0
    max_subs: int = MAX_SUBS_90
    # department strengths (recomputed on red cards / HT / subs via _recompute_strengths)
    att: float = 0.0
    mid: float = 0.0
    dfn: float = 0.0
    gk: float = 0.0
    pace: float = 0.0
    shooting: float = 0.0

    def mean_effective(self) -> float:
        """Team-wide fitness×morale factor (≈1 fresh, <1 as legs go)."""
        if not self.on_pitch:
            return 1.0
        total = 0.0
        for pid in self.on_pitch:
            prof = self.profiles.get(pid)
            total += (prof.get("morale", 0.75) * (1.0 - 0.5 * (1.0 - prof.get("fitness", 1.0)))
                      if prof else 0.8)
        return total / len(self.on_pitch)

    def outfielders(self) -> list[str]:
        return [pid for pid in self.on_pitch
                if (self.profiles.get(pid) or {}).get("group") != "GK"]

    def bench_ranked(self) -> list[str]:
        used = set(self.off)
        pool = [pid for pid in self.bench if pid not in used and pid not in self.on_pitch]
        pool.sort(key=lambda pid: (self.profiles.get(pid) or {}).get("overall", 70.0), reverse=True)
        return pool


def _resolve_profiles(
    xi: list[str],
    bench: list[str],
    fatigue: Optional[dict[str, float]] = None,
) -> dict[str, dict[str, float]]:
    """Attribute profiles for every involved player (defaults for unknowns).

    `fatigue` carries condition across fixtures (G4): a player's in-match
    fitness *starts* at the carried value (0..1) instead of a fresh 1.0.
    """
    carried = {pid: _clamp(float(v), 0.05, 1.0) for pid, v in (fatigue or {}).items()}
    profiles: dict[str, dict[str, float]] = {}
    for pid in xi + bench:
        p = get_player(pid)
        prof = derive_profile(p)
        slot = str((p or {}).get("slot") or (p or {}).get("primary_pos") or "CM").upper()
        prof["group"] = _GROUP_OF_SLOT.get(slot, "MID")
        prof["overall"] = (
            prof["gk"]
            if prof["group"] == "GK"
            else group_skill(prof, "pace", "technical", "physicality", "decision_making",
                             "positioning", "shooting", "passing", "tackling")
        )
        prof["fitness"] = carried.get(pid, 1.0)
        profiles[pid] = prof
    return profiles


def _weighted_means(profiles: dict[str, dict[str, float]], ids: list[str]) -> dict[str, float]:
    """Contribution-weighted department averages across the current XI."""
    s_att = s_mid = s_def = 0.0
    w_att = w_mid = w_def = 0.0
    pace_sum = pace_w = 0.0
    shoot_sum = shoot_w = 0.0
    gk_sum = gk_w = 0.0
    for pid in ids:
        prof = profiles.get(pid)
        if not prof:
            continue
        g = prof.get("group", "MID")
        eff = prof.get("morale", 0.75) * (1.0 - 0.5 * (1.0 - prof.get("fitness", 1.0)))
        av = group_skill(prof, "shooting", "pace", "technical", "decision_making") * eff
        mv = group_skill(prof, "passing", "technical", "decision_making") * eff
        dv = group_skill(prof, "tackling", "physicality", "positioning", "pace") * eff
        wa, wm, wd = _ATTACK_W[g], _MID_W[g], _DEF_W[g]
        if wa:
            s_att += av * wa
            w_att += wa
        if wm:
            s_mid += mv * wm
            w_mid += wm
        if wd:
            s_def += dv * wd
            w_def += wd
        if g == "GK":
            gk_sum += prof.get("gk", 70.0) * eff
            gk_w += 1.0
        elif g in ("FWD", "MID"):
            w_p = 1.0 if g == "FWD" else 0.5
            pace_sum += prof.get("pace", 70.0) * w_p
            pace_w += w_p
            shoot_sum += prof.get("shooting", 70.0) * (1.0 if g == "FWD" else 0.4)
            shoot_w += 1.0 if g == "FWD" else 0.4
        elif g == "DEF":
            pace_sum += prof.get("pace", 70.0) * 0.4
            pace_w += 0.4
    return {
        "att": (s_att / w_att) if w_att else 70.0,
        "mid": (s_mid / w_mid) if w_mid else 70.0,
        "dfn": (s_def / w_def) if w_def else 70.0,
        "gk": (gk_sum / gk_w) if gk_w else 70.0,
        "pace": (pace_sum / pace_w) if pace_w else 70.0,
        "shooting": (shoot_sum / shoot_w) if shoot_w else 70.0,
    }


def _recompute_strengths(side: _SideState, *, jitter: bool,
                         rng: Optional[random.Random] = None) -> None:
    """Recompute department strengths from the current on-pitch profiles.

    Called at build (small deterministic jitter), at half-time after an
    in-match tactical change, and after a red card / forced change.
    """
    means = _weighted_means(side.profiles, side.on_pitch)
    t = side.tactics
    mods = _tag_mods(t["formation"], t["tags"])

    def scale(x: float, mod: float) -> float:
        v = x * (1.0 + 0.55 * (mod - 1.0))
        if jitter and rng is not None:
            v *= 0.97 + rng.random() * 0.06
        return v

    side.att = max(20.0, scale(means["att"], mods["att"]))
    side.mid = max(20.0, scale(means["mid"], mods["mid"]))
    side.dfn = max(20.0, scale(means["dfn"], mods["def"]))
    if t["mentality"] == "attacking":
        side.att *= 1.05
        side.dfn *= 0.96
    elif t["mentality"] == "defensive":
        side.att *= 0.96
        side.dfn *= 1.06
    side.gk = means["gk"] or 70.0
    side.pace = means["pace"]
    side.shooting = means["shooting"]


def _fatigue_tick(side: _SideState, rng: random.Random) -> None:
    """Drain each on-pitch player's fitness; pressing/tempo sides tire faster."""
    drain = 0.0032 * (1.0 + side.stance["press"] * 0.9 + side.stance["tempo"] * 0.35)
    for pid in side.on_pitch:
        prof = side.profiles.get(pid)
        if prof:
            prof["fitness"] = max(0.05, prof["fitness"] - drain * (0.75 + rng.random() * 0.5))


def _make_side(
    agent_id: str,
    xi: list[str],
    bench: list[str],
    tactics_raw: Optional[dict[str, Any]],
    rng: random.Random,
    fatigue: Optional[dict[str, float]] = None,
) -> _SideState:
    tactics = _normalize_tactics(tactics_raw)
    side = _SideState(
        agent_id=agent_id,
        xi=list(xi),
        bench=list(bench),
        tactics=tactics,
        stance=_stance(tactics["formation"], tactics["tags"], tactics["mentality"],
                       tactics["instructions"]),
        profiles=_resolve_profiles(xi, bench, fatigue=fatigue),
        on_pitch=list(xi),
    )
    _recompute_strengths(side, jitter=True, rng=rng)
    return side


# ---------------------------------------------------------------- result


@dataclass
class MatchResult:
    match_id: str
    home_agent_id: str
    away_agent_id: str
    home_goals: int
    away_goals: int
    feed: list[dict[str, Any]] = field(default_factory=list)
    home_points: int = 0
    away_points: int = 0
    reason: str = "full_time"
    home_pen_goals: int = 0
    away_pen_goals: int = 0
    phases: list[dict[str, Any]] = field(default_factory=list)
    player_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    # final condition (0..1) of every involved player, per side — the season
    # carries this into the next matchday so tiredness bites across fixtures
    fatigue: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "home_agent_id": self.home_agent_id,
            "away_agent_id": self.away_agent_id,
            "score": _fmt(self.home_goals, self.away_goals),
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_points": self.home_points,
            "away_points": self.away_points,
            "reason": self.reason,
            "home_pen_goals": self.home_pen_goals,
            "away_pen_goals": self.away_pen_goals,
            "stats": derive_stats(self.feed, self.home_goals, self.away_goals),
            "feed": self.feed,
            "phases": self.phases,
            "outcome": _outcome(self),
            "engine": ENGINE_VERSION,
            "player_stats": self.player_stats,
            "fatigue": self.fatigue,
        }


def _outcome(result: "MatchResult") -> str:
    if result.reason in ("extra_time", "penalties"):
        # a decider match never ends level — the shootout settled it
        if result.home_pen_goals != result.away_pen_goals:
            return "home_win" if result.home_pen_goals > result.away_pen_goals else "away_win"
        return "home_win" if result.home_goals > result.away_goals else "away_win"
    if result.home_goals > result.away_goals:
        return "home_win"
    if result.away_goals > result.home_goals:
        return "away_win"
    return "draw"


# ---------------------------------------------------------------- spatial overlay

# The spatial overlay is a *pure* post-processing fold over the finished feed.
# It never consumes the match RNG, so it cannot change outcomes: positions are
# derived from a separate deterministic hash stream keyed on (match_id,
# event_index, field) — the same match always yields the same coordinates.


def _spatial_unit(match_id: str, i: int, field: str) -> float:
    h = hashlib.sha256(f"afm-spatial:{match_id}:{i}:{field}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / (2**32)


def _unit_in(match_id: str, i: int, field: str, lo: float, hi: float) -> float:
    return lo + _spatial_unit(match_id, i, field) * (hi - lo)


def _clamp_coord(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _facing_for(side: str | None, unit: float) -> float:
    """Degrees [0, 360): home attacks toward +x (90°), away toward −x (270°)."""
    base = 90.0 if side == "home" else 270.0 if side == "away" else 0.0
    return round((base + (unit - 0.5) * 40.0) % 360.0, 1)


def spatialize_feed(feed: list[dict[str, Any]], match_id: str) -> list[dict[str, Any]]:
    """Add x/y/z/facing/actor_id to every event (deterministic, additive).

    Positions are event-type aware so a renderer gets believable, football-
    shaped geometry straight from the log:

      kickoff              — centre spot
      possession / pass    — ball drifts toward the holder's attacking goal
      shot / goal          — inside the attacking box, on target toward goal
      corner               — attacking corner flag
      goal_kick            — keeper's six-yard area
      throw_in             — touchline where play stopped
      penalty / shootout   — the penalty spot
      card / foul / tackle — wherever the ball was
      substitution         — touchline near the halfway line

    Existing keys are untouched; consumers that ignore the new keys see the
    exact same feed as before. Replays are byte-identical because the overlay
    is a pure function of (match_id, event index).
    """
    out: list[dict[str, Any]] = []
    ball_x = PITCH_LENGTH / 2.0
    ball_y = PITCH_WIDTH / 2.0

    for i, ev in enumerate(feed):
        typ = ev.get("type")
        side = ev.get("side")
        # separate unit draws per coordinate so x/y/z don't correlate
        ux = _spatial_unit(match_id, i, "x")
        uy = _spatial_unit(match_id, i, "y")
        uz = _spatial_unit(match_id, i, "z")
        uf = _spatial_unit(match_id, i, "f")

        x, y, z = ball_x, ball_y, 0.0
        if typ == "kickoff":
            x, y = PITCH_LENGTH / 2.0, PITCH_WIDTH / 2.0
        elif typ == "possession":
            # drift toward the holder's attacking goal, with lateral wander
            if side in _GOAL_X:
                x += (1.0 if side == "home" else -1.0) * _unit_in(match_id, i, "x", 3.0, 14.0)
            y += (uy - 0.5) * 18.0
        elif typ == "pass":
            if side in _GOAL_X:
                x += (1.0 if side == "home" else -1.0) * _unit_in(match_id, i, "x", 2.0, 12.0)
            y += (uy - 0.5) * 14.0
            z = round(0.4 + uz * 3.6, 2)  # lofted balls carry height
        elif typ in ("shot", "goal"):
            if side in _GOAL_X:
                x = _unit_in(match_id, i, "x", _BOX_INNER[side], _BOX_OUTER[side])
            else:
                x = PITCH_LENGTH / 2.0 + (ux - 0.5) * 30.0
            y = _unit_in(match_id, i, "y", 0.0, PITCH_WIDTH)
            z = round(0.1 + uz * 1.4, 2)
        elif typ == "corner":
            if side in _GOAL_X:
                x = _GOAL_X[side]
            # hug one of the two corner flags on the attacking end (~2–9m out)
            if uy < 0.5:
                y = PITCH_WIDTH * (0.03 + uy * 0.20)
            else:
                y = PITCH_WIDTH * (0.87 + (uy - 0.5) * 0.20)
            z = 0.0
        elif typ == "goal_kick":
            if side in _GOAL_X:
                x = _unit_in(match_id, i, "x", _BOX_INNER[side], _BOX_OUTER[side])
            y = PITCH_WIDTH / 2.0 + (uy - 0.5) * 24.0
            z = 0.0
        elif typ == "throw_in":
            x = _clamp_coord(x + (ux - 0.5) * 10.0, 2.0, PITCH_LENGTH - 2.0)
            y = 0.5 if uy < 0.5 else PITCH_WIDTH - 0.5
            z = 0.0
        elif typ == "penalty":
            if side in _SPOT_X:
                x = _SPOT_X[side]
            y = PITCH_WIDTH / 2.0
            z = 0.0
        elif typ in ("substitution",):
            x = PITCH_LENGTH / 2.0 + (ux - 0.5) * 14.0
            y = 0.5 if uy < 0.5 else PITCH_WIDTH - 0.5
            z = 0.0
        elif typ in ("yellow", "red", "foul", "offside", "tackle", "interception",
                     "injury", "blocked_shot"):
            x = _clamp_coord(x + (ux - 0.5) * 12.0, 2.0, PITCH_LENGTH - 2.0)
            y = _clamp_coord(y + (uy - 0.5) * 16.0, 1.0, PITCH_WIDTH - 1.0)
            z = round(0.1 + uz * 1.2, 2)
        # halftime / full_time / added_time / extra_time_end / penalties_* keep
        # the ball where it was; a neutral event pins it to the centre circle
        elif typ in ("halftime", "full_time", "extra_time_end", "penalties_start",
                     "penalties_end"):
            x, y = PITCH_LENGTH / 2.0, PITCH_WIDTH / 2.0
            z = 0.0

        x = round(_clamp_coord(x, 0.0, PITCH_LENGTH), 1)
        y = round(_clamp_coord(y, 0.0, PITCH_WIDTH), 1)

        new = dict(ev)
        new["x"] = x
        new["y"] = y
        new["z"] = z
        new["facing"] = _facing_for(side, uf)
        new["actor_id"] = ev.get("player_id") or (side if side else "ball")
        out.append(new)

        # carry the ball forward for the next event
        if typ in ("possession", "pass", "shot", "goal", "goal_kick"):
            ball_x, ball_y = x, y
    return out


def _shot_xg(shooter: Optional[str], atk: _SideState, dfn: _SideState,
              side: str, ev_idx: int, match_id: str) -> float:
    """Per-shot expected goals — a deterministic fold over the shooter's

    finishing quality, the keeper's saving quality, the shot's attacking
    position and the defensive pressure at the moment.

    The shot's coordinate is taken from the same deterministic hash stream
    the spatial overlay uses (keyed on (match_id, ev_idx) via `_spatial_unit`),
    so the xG and the overlay positions are identical and replay-safe.

    Individual skill drives the shot: the shooter's shooting attribute, not
    the team shooting mean, anchors the finish. The keeper's gk anchors the
    save. This is the path toward "a 6.4-rated midfielder can score a
    worldie, rarely" — shot quality is per-actor, not only team-aggregate.
    """
    if shooter is None:
        return 0.012
    prof = atk.profiles.get(shooter) or {}
    shoot = float(prof.get("shooting", 70.0))
    place = float(prof.get("positioning", 70.0))
    gk_skill = dfn.gk if dfn is not None else 70.0
    # attacking position: inside the attacking box → materially higher xG.
    # Read the shot's x from the same stream the overlay will use.
    x_unit = _spatial_unit(match_id, ev_idx, "sx")
    inside_box = x_unit > 0.55  # ~45% of shots from inside the box
    # central-ish lateral position is slightly better
    y_unit = _spatial_unit(match_id, ev_idx, "sy")
    y_centre = 1.0 - min(abs(y_unit - 0.5) * 2.0, 1.0)
    # baseline difficulty from keeper vs shooter (per-actor, not team mean)
    base = 0.052 + (shoot - gk_skill) / 900.0 + (atk.stance["tempo"] - 0.5) * 0.015
    # position multiplier (inside the box is the big one)
    pos_mult = 2.0 if inside_box else 1.0
    # placement bonus: a well-positioned shooter picks a better angle
    place_mult = 1.0 + (place - 70.0) / 500.0
    # defensive pressure at the moment: high line + press compresses xG
    press_penalty = dfn.stance["press"] * 0.05 + max(0.0, dfn.stance["agg"]) * 0.02 if dfn else 0.0
    xg = base * pos_mult * place_mult * (1.0 - press_penalty)
    # small deterministic wobble per shot so identical-looking shots differ
    wobble = 0.88 + _spatial_unit(match_id, ev_idx, "xg") * 0.24
    return _clamp(float(xg) * wobble * y_centre, 0.005, 0.72)


def derive_player_stats(
    feed: list[dict[str, Any]],
    match_id: str,
    home_agent_id: str,
    away_agent_id: str,
    home_goals: int,
    away_goals: int,
    home_xi: Optional[list[str]] = None,
    away_xi: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Per-player post-match performance — a pure fold over the spatialized feed.

    Needs `get_player` for name lookup when building match_errors. Imported
    lazily to avoid circular imports at module load time.

    Every event carries an `actor_id` (set by `spatialize_feed`), so the fold
    attributes contributions to real players rather than team aggregates:
    minutes, shots, shots on target, goals, xG (cumulative per-shot xG when
    the player was the shooter), key passes, tackles, interceptions, fouls,
    yellows, reds, cards, passes.

    A 0-99 performance `rating` is derived from the same feed: finishing
    (goals vs xG), shot quality, defensive actions, passing and presence.
    Ratings are comparable to `base_rating` so a great match can push a
    player above their real rating (and a poor one below) — that is the
    point of a post-match rating rather than a static attribute.

    Backward compatible: this is additive. Consumers that ignore the new
    field see the same MatchResult they saw before.
    """
    from collections import defaultdict

    # per-player accumulators
    minutes_seen: dict[str, set[int]] = defaultdict(set)  # player_id -> set of minutes
    shots: dict[str, int] = defaultdict(int)
    shots_on_target: dict[str, int] = defaultdict(int)
    goals: dict[str, int] = defaultdict(int)
    xg: dict[str, float] = defaultdict(float)
    key_passes: dict[str, int] = defaultdict(int)
    tackles: dict[str, int] = defaultdict(int)
    interceptions: dict[str, int] = defaultdict(int)
    fouls_committed: dict[str, int] = defaultdict(int)
    yellows: dict[str, int] = defaultdict(int)
    reds: dict[str, int] = defaultdict(int)
    passes: dict[str, int] = defaultdict(int)
    assists: dict[str, int] = defaultdict(int)
    errors: dict[str, list[dict[str, Any]]] = defaultdict(list)

    team_xg: dict[str, float] = {"home": 0.0, "away": 0.0}
    team_goals: dict[str, int] = {"home": home_goals, "away": away_goals}

    def actor(ev: dict[str, Any]) -> Optional[str]:
        return ev.get("actor_id")

    def side_of(ev: dict[str, Any]) -> Optional[str]:
        return ev.get("side")

    # costliest missed shots: high xG shots that did not become goals are the
    # clearest "error that cost us" signal; a high xG miss is an error for the
    # shooting side's player.
    missed_high_xg: list[tuple[float, dict[str, Any]]] = []

    for ev in feed:
        pid = actor(ev)
        st = side_of(ev)
        typ = ev.get("type")
        minute = int(ev.get("minute") or 0)

        if pid:
            minutes_seen[pid].add(minute)

        if typ == "possession":
            continue
        if typ == "pass":
            if pid:
                passes[pid] += 1
            continue
        if typ == "tackle" or typ == "interception":
            if pid:
                if typ == "tackle":
                    tackles[pid] += 1
                else:
                    interceptions[pid] += 1
            continue
        if typ == "foul":
            if pid:
                fouls_committed[pid] += 1
            continue
        if typ == "yellow":
            if pid:
                yellows[pid] += 1
            continue
        if typ == "red":
            if pid:
                reds[pid] += 1
            continue
        if typ == "shot":
            if pid:
                shots[pid] += 1
                xv = float(ev.get("xG", 0.0))
                if xv > 0:
                    xg[pid] += xv
                    if st in ("home", "away"):
                        team_xg[st] += xv
                if ev.get("on_target"):
                    shots_on_target[pid] += 1
                # a high xG shot that was blocked/saved/off-target is a costly miss
                if xv >= 0.18 and not ev.get("on_target", False):
                    missed_high_xg.append((xv, ev))
            continue
        if typ == "goal":
            if pid:
                goals[pid] += 1
                xv = float(ev.get("xG", 0.0))
                if xv > 0:
                    xg[pid] += xv
                    if st in ("home", "away"):
                        team_xg[st] += xv
                # goals are not errors; they are the positive end of the xG chain
                asst = ev.get("assist")
                if asst:
                    assists[asst] += 1
                    key_passes[asst] += 1  # the goal-leading pass is a key pass
            continue
        # cards/fulls already handled above; anything else is neutral for stats

    # match-level critical errors: the highest-xG misses, plus sending-offs
    match_errors: list[dict[str, Any]] = []
    # a player's side comes from their red event in the feed (side_of the loop
    # below is just the iteration variable — never attribute by it)
    red_side_of: dict[str, str] = {}
    red_minute_of: dict[str, int] = {}
    for ev in feed:
        if ev.get("type") == "red" and ev.get("player_id"):
            pid = str(ev["player_id"])
            red_side_of[pid] = str(ev.get("side") or "")
            red_minute_of[pid] = int(ev.get("minute") or 0)
    for pid, count in list(reds.items()):
        if count > 0:
            match_errors.append({
                "minute": red_minute_of.get(pid, 0),
                "type": "sent_off",
                "player_id": pid,
                "side": red_side_of.get(pid),
                "note": f"{count} red card{'s' if count > 1 else ''} — player sent off",
            })
    for sid in ("home", "away"):
        # top high-xG misses for this side (up to 2)
        side_misses = [m for m in missed_high_xg if side_of(m[1]) == sid]
        side_misses.sort(key=lambda m: -m[0])
        for xv, ev in side_misses[:2]:
            pid = actor(ev)
            try:
                from gaming.src.stack.agentic.games.football_managers.catalog import get_player as _gp
                pname_val = ((_gp(pid) or {}).get("name") or pid) if pid else ""
            except Exception:
                pname_val = pid or ""
            match_errors.append({
                "minute": int(ev.get("minute") or 0),
                "type": "missed_high_xg",
                "player_id": pid,
                "side": sid,
                "xG": round(xv, 3),
                "note": f"{ev.get('minute', 0)}' · {pname_val} missed a high-xG chance",
            })
    # also flag the margin between xG and goals for each side as a match-level note
    for sid in ("home", "away"):
        delta = team_goals[sid] - team_xg[sid]
        if abs(delta) >= 1.0:
            over = delta > 0
            match_errors.append({
                "minute": 90,
                "type": "xG_over_performance" if over else "xG_under_performance",
                "player_id": None,
                "side": sid,
                "xG": round(team_xg[sid], 3),
                "goals": team_goals[sid],
                "note": (
                    f"{sid} overperformed their xG by {round(delta, 2)} goals"
                    if over
                    else f"{sid} underperformed their xG by {round(-delta, 2)} goals"
                ),
            })

    # true minutes on pitch: reconstructed from the starting XIs plus
    # substitution / red-card events. Event-presence alone credits a 90-minute
    # starter only with the minutes something happened *near* him (a quiet
    # centre-back could show "13 minutes") — the lineup timeline fixes that.
    def _minutes_on_pitch() -> dict[str, int]:
        if home_xi is None and away_xi is None:
            return {pid: len(m) for pid, m in minutes_seen.items()}
        ft_minute = max((int(ev.get("minute") or 0) for ev in feed), default=90)
        entry: dict[str, int] = {}
        exit_at: dict[str, int] = {}
        for pid in (home_xi or []):
            entry[str(pid)] = 0
        for pid in (away_xi or []):
            entry[str(pid)] = 0
        for ev in feed:
            typ = ev.get("type")
            m = int(ev.get("minute") or 0)
            if typ == "substitution":
                off, on = ev.get("off"), ev.get("on")
                if off and str(off) not in exit_at:
                    exit_at[str(off)] = m  # first exit wins (off then red, etc.)
                if on:
                    entry.setdefault(str(on), m)
            elif typ == "red" and ev.get("player_id"):
                exit_at.setdefault(str(ev["player_id"]), m)
        return {pid: max(0, exit_at.get(pid, ft_minute) - ent)
                for pid, ent in entry.items()}

    minutes_on_pitch = _minutes_on_pitch()

    # build per-player records
    # NB: assists deliberately do NOT create recs on their own — an assister
    # virtually always has other attributed events; an assist-only rec would
    # carry minutes=0 and poison the report's rating sort.
    all_pids: set[str] = (set(minutes_seen) | set(shots) | set(goals) | set(xg)
                          | set(tackles) | set(interceptions) | set(fouls_committed)
                          | set(yellows) | set(reds) | set(passes)
                          | set(minutes_on_pitch))  # every XI player gets a rec
    out: dict[str, dict[str, Any]] = {}
    for pid in all_pids:
        mins = minutes_on_pitch.get(pid, len(minutes_seen.get(pid, set())))
        if mins <= 0:
            # attributed events but never on the pitch in the reconstructed
            # timeline — drop the rec rather than poison the rating sort
            continue
        rating = _player_rating(
            pid=pid,
            goals=goals.get(pid, 0),
            xg=xg.get(pid, 0.0),
            shots=shots.get(pid, 0),
            shots_on_target=shots_on_target.get(pid, 0),
            passes=passes.get(pid, 0),
            tackles=tackles.get(pid, 0),
            interceptions=interceptions.get(pid, 0),
            fouls=fouls_committed.get(pid, 0),
            yellows=yellows.get(pid, 0),
            reds=reds.get(pid, 0),
            minutes=mins,
        )
        perrors = errors.get(pid, [])
        # attach missed high-xG to the shooting player's error list
        for xv, ev in missed_high_xg:
            if ev.get("actor_id") == pid:
                perrors.append({
                    "minute": int(ev.get("minute") or 0),
                    "type": "missed_high_xg",
                    "xG": round(xv, 3),
                    "note": f"{ev.get('minute', 0)}' · missed a {round(xv, 2)} xG chance",
                })
        out[pid] = {
            "player_id": pid,
            "minutes": mins,
            "shots": shots.get(pid, 0),
            "shots_on_target": shots_on_target.get(pid, 0),
            "goals": goals.get(pid, 0),
            "xG": round(xg.get(pid, 0.0), 3),
            "key_passes": key_passes.get(pid, 0),
            "tackles": tackles.get(pid, 0),
            "interceptions": interceptions.get(pid, 0),
            "fouls_committed": fouls_committed.get(pid, 0),
            "yellows": yellows.get(pid, 0),
            "reds": reds.get(pid, 0),
            "cards": yellows.get(pid, 0) + reds.get(pid, 0),
            "passes": passes.get(pid, 0),
            "assists": assists.get(pid, 0),
            "rating": rating,
            "errors": sorted(perrors, key=lambda e: -(e.get("xG", 0.0) or 0.0)),
        }
    return out


def _player_rating(
    *,
    pid: str,
    goals: int,
    xg: float,
    shots: int,
    shots_on_target: int,
    passes: int,
    tackles: int,
    interceptions: int,
    fouls: int,
    yellows: int,
    reds: int,
    minutes: int,
) -> int:
    """Derive a 0-99 post-match performance rating from the feed fold.

    Finishing (goals vs xG) is the strongest signal; shot volume and quality,
    defensive actions, passing involvement and discipline shape the rest.
    Ratings are clamped to a sane band so a single lucky goal does not send a
    role player to 99, and a calamitous match cannot push below a floor.
    """
    if minutes <= 0:
        return 60
    # finishing: how much did the player over/under-perform their xG
    fin = 0.0
    if shots > 0:
        fin = (goals - xg) * 6.0  # each goal above xG lifts ~6 points
    # shot involvement: a forward/mid who touched the ball in attack should
    # get some credit for being in the game even without a goal
    shot_score = min(20.0, shots_on_target * 3.0 + (shots - shots_on_target) * 0.6)
    # defensive contribution
    def_score = min(18.0, tackles * 2.2 + interceptions * 2.6)
    # passing involvement (low weight so it doesn't dominate)
    pass_score = min(8.0, passes * 0.25)
    # discipline penalty
    card_penalty = yellows * 3.0 + reds * 12.0
    # base rating from involvement
    base = 62.0 + fin + shot_score + def_score + pass_score - card_penalty
    # presence floor/ceiling: someone on the pitch for 90 doing nothing useful
    # should not rate like a star; someone heavily involved should not tank
    presence = min(12.0, (shots + passes + tackles + interceptions) * 0.4)
    base += presence
    return int(max(35, min(96, round(base))))


def derive_stats(feed: list[dict[str, Any]], home_goals: int, away_goals: int) -> dict[str, Any]:
    """Post-match stats summary — a pure fold over the event log.

    Every shot, goal, foul, card, offside, corner, throw-in, goal kick,
    tackle, interception, substitution, injury and possession minute is an
    event, so the summary is derived purely from the feed (the engine stores
    exactly what a downstream consumer could derive itself).

    Per-shot xG is folded here as a pure function of the shot/goal events
    (each carries its own xG in `extra` once the spatial overlay has run).
    Totals are additive and reproducible by any downstream consumer that
    re-derives them from the same feed.
    """
    poss = {"home": 0, "away": 0}
    per_type: dict[str, dict[str, int]] = {}
    on_target = {"home": 0, "away": 0}
    blocked = {"home": 0, "away": 0}
    xg = {"home": 0.0, "away": 0.0}

    def bump(typ: str, side: Any) -> None:
        if side not in ("home", "away"):
            return
        per_type.setdefault(typ, {})
        per_type[typ][side] = per_type[typ].get(side, 0) + 1

    for ev in feed:
        typ = ev.get("type")
        side = ev.get("side")
        if typ == "possession":
            if side in poss:
                poss[side] += 1
        elif typ == "shot":
            bump("shot", side)
            if ev.get("on_target"):
                on_target[side] = on_target[side] + 1
            if ev.get("blocked"):
                blocked[side] = blocked[side] + 1
            xv = float(ev.get("xG", 0.0))
            if side in xg and xv > 0:
                xg[side] += xv
        elif typ == "goal":
            bump("goal", side)
            xv = float(ev.get("xG", 0.0))
            if side in xg and xv > 0:
                xg[side] += xv
        else:
            bump(typ, side)

    def n(typ: str, side: str) -> int:
        return (per_type.get(typ) or {}).get(side, 0)

    total_poss = poss["home"] + poss["away"]
    poss_home = round(100.0 * poss["home"] / total_poss, 1) if total_poss else 50.0
    return {
        "possession_home": poss_home,
        "possession_away": round(100.0 - poss_home, 1),
        "shots_home": n("shot", "home") + n("goal", "home"),
        "shots_away": n("shot", "away") + n("goal", "away"),
        "shots_on_target_home": on_target["home"] + n("goal", "home"),
        "shots_on_target_away": on_target["away"] + n("goal", "away"),
        "shots_xg_home": round(xg["home"], 3),
        "shots_xg_away": round(xg["away"], 3),
        "goals_home": home_goals,
        "goals_away": away_goals,
        "corners_home": n("corner", "home"),
        "corners_away": n("corner", "away"),
        "fouls_home": n("foul", "home"),
        "fouls_away": n("foul", "away"),
        "offsides_home": n("offside", "home"),
        "offsides_away": n("offside", "away"),
        "yellow_cards_home": n("yellow", "home"),
        "yellow_cards_away": n("yellow", "away"),
        "red_cards_home": n("red", "home"),
        "red_cards_away": n("red", "away"),
        "tackles_home": n("tackle", "home"),
        "tackles_away": n("tackle", "away"),
        "interceptions_home": n("interception", "home"),
        "interceptions_away": n("interception", "away"),
        "passes_home": n("pass", "home"),
        "passes_away": n("pass", "away"),
        "throw_ins_home": n("throw_in", "home"),
        "throw_ins_away": n("throw_in", "away"),
        "goal_kicks_home": n("goal_kick", "home"),
        "goal_kicks_away": n("goal_kick", "away"),
        "substitutions_home": n("substitution", "home"),
        "substitutions_away": n("substitution", "away"),
        "injuries_home": n("injury", "home"),
        "injuries_away": n("injury", "away"),
    }


# ---------------------------------------------------------------- simulate


def simulate_match(
    match_id: str,
    *,
    home_agent_id: str,
    away_agent_id: str,
    home_xi: list[str],
    away_xi: list[str],
    home_tactics: Optional[dict[str, Any]] = None,
    away_tactics: Optional[dict[str, Any]] = None,
    home_bench: Optional[list[str]] = None,
    away_bench: Optional[list[str]] = None,
    home_tactics_2h: Optional[dict[str, Any]] = None,
    away_tactics_2h: Optional[dict[str, Any]] = None,
    require_result: bool = False,
    home_fatigue: Optional[dict[str, float]] = None,
    away_fatigue: Optional[dict[str, float]] = None,
    home_plans: Optional[dict[str, Any]] = None,
    away_plans: Optional[dict[str, Any]] = None,
) -> MatchResult:
    """Simulate a full match, deterministic per `match_id`.

    Optional Phase 0 extensions (defaulted so existing callers keep the same
    shape of result):

      home_bench / away_bench   — substitute pool (empty → no substitutions)
      home_tactics_2h / ...     — in-match adjustment applied at half-time
      require_result            — a draw must be settled: extra time + shootout
      home_fatigue / away_fatigue — carried condition (0..1) per player from
                                    the previous fixture (default: fresh legs)
      home_plans / away_plans   — half-time contingency plans keyed by game
                                    state: {"trailing": {...}, "level": {...},
                                    "leading": {...}}; the engine applies the
                                    plan the HT score calls for (an explicit
                                    ``*_tactics_2h`` still wins when both are
                                    given)
    """
    rng = random.Random(_seed_int(match_id))
    home = _make_side(home_agent_id, list(home_xi), list(home_bench or []), home_tactics, rng,
                      fatigue=home_fatigue)
    away = _make_side(away_agent_id, list(away_xi), list(away_bench or []), away_tactics, rng,
                      fatigue=away_fatigue)
    # home advantage (crowd + familiarity)
    home.att *= 1.025
    home.mid *= 1.015
    home.dfn *= 1.01
    home.gk *= 1.01

    feed: list[dict[str, Any]] = []
    hg = ag = 0
    holder: str = "home" if rng.random() < 0.5 else "away"

    def spatialize() -> None:
        nonlocal feed
        feed = spatialize_feed(feed, match_id)

    def set_holder(value: str) -> None:
        nonlocal holder
        holder = value

    def set_holder_of(s: _SideState) -> None:
        set_holder(side_of(s))

    def emit(minute: int, typ: str, text: str, side: Optional[str] = None,
             player_id: Optional[str] = None, extra: Optional[dict[str, Any]] = None) -> None:
        ev: dict[str, Any] = {"minute": minute, "type": typ, "text": text}
        if side:
            ev["side"] = side
        if player_id:
            ev["player_id"] = player_id
        if extra:
            ev.update(extra)
        feed.append(ev)

    def pname(pid: Optional[str]) -> str:
        p = get_player(pid) if pid else None
        return str((p or {}).get("name") or (pid or ""))

    def side_of(s: _SideState) -> str:
        return "home" if s is home else "away"

    def other_of(s: _SideState) -> _SideState:
        return away if s is home else home

    def holder_side() -> _SideState:
        return home if holder == "home" else away

    def possession_prob() -> float:
        w_h = home.mid * 0.62 + home.att * 0.25 + home.stance["tempo"] * 16 + home.stance["press"] * 5
        w_a = away.mid * 0.62 + away.att * 0.25 + away.stance["tempo"] * 16 + away.stance["press"] * 5
        return _clamp(w_h / (w_h + w_a + 1e-9), 0.28, 0.72)

    def advance_possession() -> None:
        nonlocal holder
        p = possession_prob()
        if holder == "home":
            holder = "home" if rng.random() < p + 0.16 else "away"
        else:
            holder = "away" if rng.random() < (1.0 - p) + 0.16 else "home"

    def attack_likely() -> float:
        atk = holder_side()
        dfn = other_of(atk)
        q = 0.34 + (atk.att - dfn.dfn) / 900.0 + atk.stance["agg"] * 0.06 - dfn.stance["press"] * 0.05
        q += (atk.stance["tempo"] - 0.5) * 0.16
        return _clamp(q, 0.15, 0.6)

    def goal_odds(atk: _SideState, dfn: _SideState) -> float:
        a = atk.shooting * atk.mean_effective()
        d = dfn.gk * dfn.mean_effective()
        p = 0.078 + (a - d) / 900.0 + (atk.att - dfn.dfn) / 2000.0
        return _clamp(p, 0.04, 0.30)

    def stoppage_time(half_events: list[dict[str, Any]]) -> int:
        subs = sum(1 for e in half_events if e["type"] == "substitution")
        cards = sum(1 for e in half_events if e["type"] in ("yellow", "red"))
        goals = sum(1 for e in half_events if e["type"] == "goal")
        injuries = sum(1 for e in half_events if e["type"] == "injury")
        extra = min(4, subs // 2 + cards // 3 + injuries * 2 + goals // 2)
        return max(1, min(6, 1 + int(rng.random() * 2.5) + extra))

    def best_attacker(s: _SideState) -> Optional[str]:
        pool = [pid for pid in s.on_pitch
                if (s.profiles.get(pid) or {}).get("group") in ("FWD", "MID")]
        if not pool:
            pool = list(s.on_pitch)
        if not pool:
            return None
        pool.sort(key=lambda pid: (s.profiles.get(pid) or {}).get("shooting", 70.0), reverse=True)
        return pool[0]

    def chance_taker(s: _SideState) -> Optional[str]:
        """Who takes THIS chance — weighted across the attacking pool.

        Real teams do not funnel every shot through their best shooter: off-ball
        movement (positioning), finishing quality and how advanced the player's
        group is decide who finds the ball in a shooting position. Forwards get
        the lion's share, midfielders a real slice — so a 6.4-rated midfielder
        can arrive late and snag one, and a marked-out star has teammates who
        shoot too. Weighted draw through the match RNG: deterministic per seed.
        """
        pool = [pid for pid in s.on_pitch
                if (s.profiles.get(pid) or {}).get("group") in ("FWD", "MID")]
        if not pool:
            pool = list(s.on_pitch)
        if not pool:
            return None
        weights: list[float] = []
        for pid in pool:
            prof = s.profiles.get(pid) or {}
            g = prof.get("group", "MID")
            w = 1.0 if g == "FWD" else 0.38
            # movement finds chances; finishing quality turns up more often too
            w *= 0.55 + prof.get("positioning", 70.0) / 130.0
            w *= 0.65 + (prof.get("shooting", 70.0) - 60.0) / 180.0
            w = max(0.05, w)
            weights.append(w)
        return rng.choices(pool, weights=weights, k=1)[0]

    def best_passer(s: _SideState) -> Optional[str]:
        """The side's most reliable distributor on the pitch (set-piece taker
        fallback: corners and free kicks go to the best passer on the pitch
        unless the manager named one in tactics.set_pieces)."""
        pool = [pid for pid in s.on_pitch
                if (s.profiles.get(pid) or {}).get("group") != "GK"]
        if not pool:
            pool = list(s.on_pitch)
        if not pool:
            return None
        pool.sort(key=lambda pid: group_skill(s.profiles.get(pid, {}), "passing", "technical", "decision_making"),
                  reverse=True)
        return pool[0]

    def _named_taker(s: _SideState, kind: str) -> Optional[str]:
        """The manager's named set-piece taker when they're on the pitch."""
        named = (s.tactics.get("set_pieces") or {}).get(kind)
        if named and named in s.on_pitch:
            return str(named)
        return None

    def game_state_shift(minute: int) -> float:
        """Score-state adjustment to the holder's appetite (chasing → push,
        leading late → manage). Deliberately small: it bends the game, it does
        not take it over."""
        my = hg if holder == "home" else ag
        opp = ag if holder == "home" else hg
        if my - opp <= -1:
            return 0.045 if minute >= 60 else 0.025
        if my - opp >= 1 and minute >= 60:
            return -0.025
        return 0.0

    def assist_for(atk: _SideState, scorer: Optional[str]) -> Optional[str]:
        """The assister on an open-play goal (~62% of them have one).

        Weighted toward creators (passing/technical) and never the scorer
        himself; the last passer before the finish."""
        if rng.random() >= 0.62:
            return None
        pool = [pid for pid in atk.on_pitch
                if pid != scorer and (atk.profiles.get(pid) or {}).get("group") != "GK"]
        if not pool:
            return None
        weights: list[float] = []
        for pid in pool:
            prof = atk.profiles.get(pid) or {}
            w = 0.6 + group_skill(prof, "passing", "technical", "decision_making") / 100.0
            g = prof.get("group", "MID")
            if g == "MID":
                w *= 1.25  # creators feed the finish
            weights.append(max(0.1, w))
        return rng.choices(pool, weights=weights, k=1)[0]

    def best_defender(s: _SideState) -> Optional[str]:
        """Who commits this foul / makes this defensive action (v1.4).

        Weighted, not deterministic: the best tackler is the most *likely*
        offender but every defender/midfielder shares the load — a fixed
        funnel heaped every foul on one player and produced phantom
        two-yellow sendings-off inside ten minutes.
        """
        pool = [pid for pid in s.on_pitch
                if (s.profiles.get(pid) or {}).get("group") in ("DEF", "MID")]
        if not pool:
            pool = list(s.on_pitch)
        if not pool:
            return None
        weights: list[float] = []
        for pid in pool:
            prof = s.profiles.get(pid) or {}
            w = 0.5 + group_skill(prof, "tackling", "physicality") / 100.0
            if prof.get("group") == "DEF":
                w *= 1.35
            weights.append(max(0.1, w))
        return rng.choices(pool, weights=weights, k=1)[0]

    def score_goal(minute: int, scorer: Optional[str], scoring_side: str,
                  shot_xg: float = 0.0, assister: Optional[str] = None,
                  kind: str = "open_play") -> None:
        nonlocal hg, ag
        if scoring_side == "home":
            hg += 1
        else:
            ag += 1
        extra: dict[str, Any] = {"score": _fmt(hg, ag), "xG": round(shot_xg, 3), "kind": kind}
        if assister and assister != scorer:
            extra["assist"] = assister
        emit(minute, "goal",
             f"{minute}' · GOAL ({scoring_side}) · {pname(scorer)} · {_fmt(hg, ag)}",
             side=scoring_side, player_id=scorer, extra=extra)

    def give_card(minute: int, s: _SideState, pid: Optional[str], kind: str, why: str) -> None:
        """Book a player; second yellow or a straight red sends them off (10 men)."""
        if pid is None or pid not in s.on_pitch:
            return
        tag = side_of(s)
        if kind == "yellow":
            s.yellows[pid] = s.yellows.get(pid, 0) + 1
            emit(minute, "yellow", f"{minute}' · yellow card ({tag}) · {pname(pid)}",
                 side=tag, player_id=pid)
            if s.yellows[pid] >= YELLOWS_TO_RED:
                s.on_pitch = [x for x in s.on_pitch if x != pid]
                _recompute_strengths(s, jitter=False)
                emit(minute, "red", f"{minute}' · RED CARD ({tag}) — second yellow · {pname(pid)}",
                     side=tag, player_id=pid)
        else:
            s.on_pitch = [x for x in s.on_pitch if x != pid]
            _recompute_strengths(s, jitter=False)
            emit(minute, "red", f"{minute}' · RED CARD ({tag}) · {pname(pid)} ({why})",
                 side=tag, player_id=pid)

    def _pick_replacement(s: _SideState, forced_off: Optional[str],
                          want_group: Optional[str]) -> Optional[str]:
        """Position-sane replacement from the bench.

        Prefers the same position group as the player going off (and never
        burns the spare keeper on an outfield change); falls back to any
        outfield player only when the bench offers nothing closer. The keeper
        only ever replaces the keeper.
        """
        pool = [pid for pid in s.bench_ranked() if pid != forced_off]
        if not pool:
            return None

        def group_of(pid: str) -> str:
            return str((s.profiles.get(pid) or {}).get("group") or "MID")

        off_group = group_of(forced_off) if forced_off else None
        if off_group == "GK":
            gks = [pid for pid in pool if group_of(pid) == "GK"]
            return gks[0] if gks else None
        outfield = [pid for pid in pool if group_of(pid) != "GK"]
        if not outfield:
            return None
        if want_group:
            same = [pid for pid in outfield if group_of(pid) == want_group]
            if same:
                return same[0]
        if off_group:
            same = [pid for pid in outfield if group_of(pid) == off_group]
            if same:
                return same[0]
        return outfield[0]

    def attempt_sub(s: _SideState, minute: int, forced_off: Optional[str] = None,
                    reason: str = "tactical") -> None:
        """One substitution for `s`; emits the event when it happens.

        Match-type aware: a side protecting a lead sends on fresh legs in
        defence/midfield and keeps its scorers on; a side chasing a game
        throws on attackers. The replacement is position-sane — a keeper only
        replaces a keeper, and like replaces like where the bench allows.
        """
        if s.subs_used >= s.max_subs or not s.bench:
            return
        tag = side_of(s)
        my_goals = hg if s is home else ag
        opp_goals = ag if s is home else hg
        leading, trailing = my_goals > opp_goals, my_goals < opp_goals
        if forced_off is None:
            outfield = s.outfielders()
            if not outfield:
                return
            # a carded player is the manager's first hook; otherwise the most
            # tiring outfielder (keepers are not rotated for fitness)
            carded = [pid for pid in outfield if (s.yellows.get(pid) or 0) > 0]
            pool = carded or outfield
            pool.sort(key=lambda pid: (s.profiles.get(pid) or {}).get("fitness", 1.0))
            forced_off = pool[0]
        off_group = str((s.profiles.get(forced_off) or {}).get("group") or "MID")
        # who should come on: chasing → attacker; protecting → fresh legs at
        # the back; an injury just replaces like-for-like
        want = None
        if reason == "injury":
            want = off_group if off_group != "GK" else None
        elif trailing:
            want = "FWD"
        elif leading:
            want = "DEF" if off_group != "MID" else "MID"
        replacement = _pick_replacement(s, forced_off, want)
        if replacement is None:
            return
        s.on_pitch = [pid for pid in s.on_pitch if pid != forced_off] + [replacement]
        s.off.append(forced_off)
        s.subs_used += 1
        prof = s.profiles.get(replacement)
        if prof:
            prof["fitness"] = 1.0  # fresh legs
        emit(minute, "substitution",
             f"{minute}' · substitution ({tag}): {pname(forced_off)} off, {pname(replacement)} on",
             side=tag,
             extra={"off": forced_off, "on": replacement, "kind": reason,
                    "match_type": "chasing" if trailing else "protecting" if leading else "level"})
        _recompute_strengths(s, jitter=False)

    def run_regular_minute(minute: int, phase: str) -> None:
        """One minute of open play: fouls/cards, a possession, possibly an attack."""
        nonlocal holder
        # injuries first (forced changes)
        for s in (home, away):
            if rng.random() < 0.0026:
                pid = chance_taker(s) or (s.on_pitch[0] if s.on_pitch else None)
                if pid:
                    emit(minute, "injury",
                         f"{minute}' · injury ({side_of(s)}): {pname(pid)} needs treatment",
                         side=side_of(s), player_id=pid)
                    attempt_sub(s, minute, forced_off=pid, reason="injury")
        # fouls can happen in quiet play too
        for s in (home, away):
            p_foul = 0.045 + s.stance["press"] * 0.05 + max(0.0, s.stance["agg"]) * 0.02
            if rng.random() >= p_foul:
                continue
            pid = best_defender(s) or (s.on_pitch[0] if s.on_pitch else None)
            if pid is None:
                continue
            emit(minute, "foul", f"{minute}' · foul ({side_of(s)}): {pname(pid)}",
                 side=side_of(s), player_id=pid)
            r = rng.random()
            if r < 0.15 + max(0.0, s.stance["agg"]) * 0.05:
                give_card(minute, s, pid, "yellow", "tactical foul")
            elif r < 0.165 + max(0.0, s.stance["agg"]) * 0.06:
                give_card(minute, s, pid, "red", "serious foul play")
            elif side_of(s) != holder and rng.random() < 0.06:
                # fouled the side in possession in a promising spot — a
                # dangerous free kick plays out (v1.4)
                resolve_set_piece(minute, "free_kick", holder_side(), s)

        # the minute's possession — appetite bends with the game state
        shift = game_state_shift(minute)
        p_base = possession_prob() + shift
        if holder == "home":
            holder = "home" if rng.random() < p_base + 0.16 else "away"
        else:
            holder = "away" if rng.random() < (1.0 - p_base) + 0.16 else "home"
        emit(minute, "possession",
             f"{minute}' · {home_agent_id if holder == 'home' else away_agent_id} in possession",
             side=holder)

        # manager substitution windows
        if phase == "second" and minute in SUB_WINDOWS:
            p_sub = 0.55 if minute == 55 else 0.45 if minute == 64 else 0.4
            for s in (home, away):
                if s.subs_used < s.max_subs and rng.random() < p_sub:
                    attempt_sub(s, minute)

        if rng.random() >= min(0.68, attack_likely() + shift):
            # quiet minute — occasionally a midfielder keeps it ticking
            if rng.random() < 0.18:
                pid = best_attacker(holder_side()) or (holder_side().on_pitch[0] if holder_side().on_pitch else None)
                if pid:
                    emit(minute, "pass", f"{minute}' · {pname(pid)} keeps it ticking",
                         side=holder, player_id=pid)
            return

        atk = holder_side()
        dfn = other_of(atk)
        atk_tag, dfn_tag = holder, side_of(dfn)

        # build-up passes (the last passer may become the assister's story)
        rr = rng.random()
        n_pass = 1 if rr < 0.4 else 2 if rr < 0.62 else 0
        last_passer: Optional[str] = None
        for _ in range(n_pass):
            pid = best_passer(atk) or (atk.on_pitch[0] if atk.on_pitch else None)
            if pid:
                emit(minute, "pass", f"{minute}' · {pname(pid)} works it forward",
                     side=atk_tag, player_id=pid)
                last_passer = pid

        # 1) defending side wins it back?
        p_turn = _clamp(0.16 + (dfn.dfn - atk.att) / 1100.0 + dfn.stance["press"] * 0.11
                        - atk.stance["tempo"] * 0.05, 0.07, 0.5)
        if rng.random() < p_turn:
            pid = best_defender(dfn) or (dfn.on_pitch[0] if dfn.on_pitch else None)
            typ = "tackle" if rng.random() < 0.62 else "interception"
            emit(minute, typ, f"{minute}' · {typ} by {pname(pid)} ({dfn_tag}) wins it back",
                 side=dfn_tag, player_id=pid)
            set_holder(dfn_tag)
            return

        # 2) offside? (referee call)
        p_off = _clamp(0.03 + (atk.pace * atk.mean_effective() - 74.0) * 0.004
                       + (dfn.stance["line"] - 0.45) * 0.09 + dfn.stance["press"] * 0.03,
                       0.012, 0.2)
        if rng.random() < p_off:
            pid = chance_taker(atk) or (atk.on_pitch[0] if atk.on_pitch else None)
            emit(minute, "offside",
                 f"{minute}' · offside ({atk_tag}) — {pname(pid)} caught ahead of the line",
                 side=atk_tag, player_id=pid)
            set_holder(dfn_tag)
            return

        # 3a) a spot kick? A foul in the box stops play and hands the
        #     referee the biggest single chance in football (rare, ~1/match)
        if rng.random() < 0.010:
            emit(minute, "foul", f"{minute}' · foul ({dfn_tag}) in the box — PENALTY!",
                 side=dfn_tag, player_id=best_defender(dfn))
            take_in_play_penalty(minute, atk, dfn)
            return

        # 3) cynical foul on the break?
        if rng.random() < 0.09 + dfn.stance["press"] * 0.08:
            pid = best_defender(dfn) or (dfn.on_pitch[0] if dfn.on_pitch else None)
            emit(minute, "foul", f"{minute}' · foul ({dfn_tag}): {pname(pid)} stops the break",
                 side=dfn_tag, player_id=pid)
            r = rng.random()
            agg = max(0.0, dfn.stance["agg"])
            if r < 0.13 + agg * 0.04:
                give_card(minute, dfn, pid, "yellow", "professional foul")
            elif r < 0.145 + agg * 0.05:
                give_card(minute, dfn, pid, "red", "last-man foul")
            elif r < 0.215 + agg * 0.05:
                # dangerous territory: a direct free kick plays out (v1.4).
                # The band sits fully above the card bands (both of which
                # stretch with aggression) so it can never be eaten by them.
                resolve_set_piece(minute, "free_kick", atk, dfn)
                return
            return

        # 4) the shot — WHO takes it is weighted across the attacking pool,
        #    not always the same star (v1.4 chance distribution)
        shooter = chance_taker(atk) or (atk.on_pitch[0] if atk.on_pitch else None)
        ev_idx = len(feed)
        shot_xg = _shot_xg(shooter, atk, dfn, atk_tag, ev_idx, match_id)
        if rng.random() < goal_odds(atk, dfn):
            assister = last_passer if (last_passer and last_passer != shooter and rng.random() < 0.55) \
                else assist_for(atk, shooter)
            score_goal(minute, shooter, atk_tag, shot_xg, assister=assister)
            set_holder(dfn_tag)
            return
        r = rng.random()
        is_blocked = r < 0.28
        on_target = (not is_blocked) and r < 0.72
        if is_blocked:
            if rng.random() < 0.6:
                emit(minute, "corner",
                     f"{minute}' · corner ({atk_tag}) — {pname(shooter)}'s shot deflected",
                     side=atk_tag, player_id=shooter)
                resolve_set_piece(minute, "corner", atk, dfn)
                return
            else:
                emit(minute, "shot", f"{minute}' · shot blocked ({atk_tag}) · {pname(shooter)}",
                     side=atk_tag, player_id=shooter,
                     extra={"on_target": False, "blocked": True, "xG": round(shot_xg, 3)})
        else:
            emit(minute, "shot",
                 f"{minute}' · shot {'on target — saved' if on_target else 'off target'} ({atk_tag}) · {pname(shooter)}",
                 side=atk_tag, player_id=shooter,
                 extra={"on_target": bool(on_target), "blocked": False, "xG": round(shot_xg, 3)})
            if rng.random() < 0.8:
                restart = "goal_kick" if rng.random() < 0.62 else "throw_in"
                restart_side = dfn_tag if restart == "goal_kick" else atk_tag
                emit(minute, restart, f"{minute}' · {restart.replace('_', ' ')} ({restart_side})",
                     side=restart_side)
        set_holder(dfn_tag)

    def take_in_play_penalty(minute: int, atk: _SideState, dfn: _SideState) -> None:
        """A spot kick in open play — the referee points to it, the taker
        (manager-named or the side's best converter) walks up (v1.4)."""
        atk_tag = side_of(atk)
        taker = _named_taker(atk, "penalty") or best_attacker(atk) or (atk.on_pitch[0] if atk.on_pitch else None)
        skill = group_skill(atk.profiles.get(taker, {}), "shooting", "technical", "decision_making")
        p_make = _clamp(0.76 + (skill - dfn.gk) / 550.0, 0.55, 0.95)
        ev_idx = len(feed)
        # recorded xG stays inside the phase-0 invariant band (<= 0.72) even
        # though the true conversion odds are higher
        pen_xg = _clamp(p_make * (0.9 + _spatial_unit(match_id, ev_idx, "pen") * 0.2), 0.4, 0.72)
        if rng.random() < p_make:
            score_goal(minute, taker, atk_tag, pen_xg, kind="penalty")
        else:
            saved = rng.random() < 0.72
            emit(minute, "shot",
                 f"{minute}' · PENALTY ({atk_tag}) · {pname(taker)} "
                 f"{'— saved by the keeper!' if saved else 'blazes it over!'}",
                 side=atk_tag, player_id=taker,
                 extra={"on_target": bool(saved), "blocked": False, "xG": round(pen_xg, 3), "kind": "penalty"})
        set_holder(side_of(dfn))

    def resolve_set_piece(minute: int, sp: str, atk: _SideState, dfn: _SideState) -> None:
        """A corner or a dangerous free kick actually plays out (v1.4).

        The taker (manager-named or the best passer) delivers; a weighted
        attacker attacks the ball. Corner headers convert at a header's xG,
        direct free kicks at ~0.06. Everything else recycles into open play
        (cleared / saved) so the flow keeps moving.
        """
        atk_tag = side_of(atk)
        dfn_tag = side_of(dfn)
        if sp == "corner":
            taker = _named_taker(atk, "corner") or best_passer(atk)
            emit(minute, "corner_delivery",
                 f"{minute}' · corner from {pname(taker)} ({atk_tag})",
                 side=atk_tag, player_id=taker,
                 extra={"set_piece": "corner"})
            # attacking the ball: weighted across the pool, defenders crash too
            pool = [pid for pid in atk.on_pitch
                    if (atk.profiles.get(pid) or {}).get("group") != "GK"]
            if not pool:
                set_holder(dfn_tag)
                return
            weights: list[float] = []
            for pid in pool:
                prof = atk.profiles.get(pid) or {}
                w = 0.6 + prof.get("physicality", 70.0) / 100.0
                if prof.get("group") == "FWD":
                    w *= 1.4
                weights.append(max(0.1, w))
            attacker = rng.choices(pool, weights=weights, k=1)[0]
            prof = atk.profiles.get(attacker) or {}
            header_xg = _clamp(0.10 + (prof.get("shooting", 70.0) - dfn.gk) / 700.0
                               + (prof.get("physicality", 70.0) - 70.0) / 900.0, 0.03, 0.28)
            if rng.random() < header_xg:
                score_goal(minute, attacker, atk_tag, header_xg,
                           assister=taker if taker != attacker else None, kind="corner")
            elif rng.random() < 0.45:
                emit(minute, "shot",
                     f"{minute}' · {pname(attacker)}'s header is off target ({atk_tag})",
                     side=atk_tag, player_id=attacker,
                     extra={"on_target": False, "blocked": False, "xG": round(header_xg, 3), "kind": "header"})
            else:
                emit(minute, "pass", f"{minute}' · cleared, {dfn_tag} regroup",
                     side=dfn_tag, player_id=best_defender(dfn))
            set_holder(dfn_tag if rng.random() < 0.55 else atk_tag)
        else:  # free_kick
            taker = _named_taker(atk, "free_kick") or best_passer(atk)
            emit(minute, "free_kick",
                 f"{minute}' · free kick ({atk_tag}) — {pname(taker)} stands over it",
                 side=atk_tag, player_id=taker,
                 extra={"set_piece": "free_kick"})
            fk_xg = _clamp(0.055 + (group_skill(atk.profiles.get(taker, {}), "shooting", "technical") - 78.0) / 550.0,
                           0.02, 0.18)
            if rng.random() < fk_xg:
                score_goal(minute, taker, atk_tag, fk_xg, kind="free_kick")
            elif rng.random() < 0.5:
                emit(minute, "shot",
                     f"{minute}' · {pname(taker)}'s free kick is deflected wide ({atk_tag})",
                     side=atk_tag, player_id=taker,
                     extra={"on_target": False, "blocked": True, "xG": round(fk_xg, 3), "kind": "free_kick"})
            set_holder(dfn_tag if rng.random() < 0.6 else atk_tag)

    def added_time_passage(base_minute: int, added: int) -> None:
        """A short passage of play across the added minutes of a half."""
        for k in range(1, added + 1):
            if rng.random() >= 0.5:
                continue
            advance_possession()
            atk_tag = holder
            atk = holder_side()
            dfn = other_of(atk)
            emit(base_minute, "possession",
                 f"{base_minute}+{k}' · {home_agent_id if holder == 'home' else away_agent_id} push forward",
                 side=holder)
            if rng.random() >= attack_likely() * 0.85:
                continue
            shooter = chance_taker(atk) or (atk.on_pitch[0] if atk.on_pitch else None)
            ev_idx = len(feed)
            shot_xg = _shot_xg(shooter, atk, dfn, atk_tag, ev_idx, match_id)
            if rng.random() < goal_odds(atk, dfn):
                score_goal(base_minute, shooter, atk_tag, shot_xg,
                           assister=assist_for(atk, shooter))
                set_holder_of(dfn)
            else:
                emit(base_minute, "shot", f"{base_minute}+{k}' · late shot ({atk_tag})",
                     side=atk_tag, player_id=shooter,
                     extra={"on_target": False, "blocked": False, "xG": round(shot_xg, 3)})

    # ------------------------------------------------------------ kickoff
    emit(0, "kickoff", f"Kickoff · {home_agent_id} vs {away_agent_id}", side=holder)

    # ------------------------------------------------------------- halves
    second_start = None
    for phase, lo, hi in (("first", 1, 46), ("second", 46, 91)):
        half_start = len(feed)
        if phase == "second":
            second_start = half_start
        for minute in range(lo, hi):
            _fatigue_tick(home, rng)
            _fatigue_tick(away, rng)
            run_regular_minute(minute, phase)
        if phase == "first":
            added1 = stoppage_time(feed[half_start:])
            if added1:
                emit(45, "added_time",
                     f"45' · referee signals {added1} minute{'s' if added1 > 1 else ''} of stoppage time",
                     extra={"added": added1})
                added_time_passage(45, added1)
            emit(45, "halftime", f"45' · Half-time · {_fmt(hg, ag)}", extra={"score": _fmt(hg, ag)})
            # the in-match window: managers may change tactics for half two.
        # v1.4 contingency plans: a manager can pre-commit a plan per HT game
        # state (trailing/level/leading); the engine applies the one the
        # scoreboard calls for. An explicit home_tactics_2h (the old path)
        # still wins when both are given.
            def _pick_2h(raw: Optional[dict[str, Any]],
                         plans: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
                if raw is not None:
                    return raw
                if not plans:
                    return None
                if hg > ag:
                    state = "leading"
                elif ag > hg:
                    state = "trailing"
                else:
                    state = "level"
                return plans.get(state)

            for s, raw, plans in ((home, home_tactics_2h, home_plans), (away, away_tactics_2h, away_plans)):
                chosen = _pick_2h(raw, plans)
                if chosen is None:
                    continue
                s.tactics = _normalize_tactics(chosen)
                s.stance = _stance(s.tactics["formation"], s.tactics["tags"],
                                   s.tactics["mentality"], s.tactics["instructions"])
                _recompute_strengths(s, jitter=True, rng=rng)
                emit(45, "tactical_change",
                     f"45' · {side_of(s)} change it at the break: "
                     f"{s.tactics['formation']} ({', '.join(s.tactics['tags']) or 'no tags'})",
                     side=side_of(s),
                     extra={"formation": s.tactics["formation"],
                            "tags": list(s.tactics["tags"]),
                            "mentality": s.tactics["mentality"]})

    # ------------------------------------------------- second-half stoppage
    added2 = stoppage_time(feed[second_start:]) if second_start is not None else 1
    if added2:
        emit(90, "added_time",
             f"90' · referee signals {added2} minute{'s' if added2 > 1 else ''} of stoppage time",
             extra={"added": added2})
        added_time_passage(90, added2)

    # ---------------------------------------------------------- extra time
    reason = "full_time"
    pen_h = pen_a = 0
    if require_result and hg == ag:
        emit(90, "full_time", f"90' · FT {_fmt(hg, ag)} · level — extra time needed",
             extra={"score": _fmt(hg, ag)})
        home.max_subs = MAX_SUBS_WITH_ET
        away.max_subs = MAX_SUBS_WITH_ET
        for lo, hi in ((91, 106), (106, 121)):
            for minute in range(lo, hi):
                _fatigue_tick(home, rng)
                _fatigue_tick(away, rng)
                advance_possession()
                atk_tag = holder
                atk = holder_side()
                dfn = other_of(atk)
                emit(minute, "possession",
                     f"{minute}' · {home_agent_id if holder == 'home' else away_agent_id} keep the ball",
                     side=holder)
                if rng.random() >= attack_likely() * 0.6:
                    continue
                shooter = chance_taker(atk) or (atk.on_pitch[0] if atk.on_pitch else None)
                # tired legs: shots come a touch easier in extra time
                if rng.random() < _clamp(goal_odds(atk, dfn) * 1.12, 0.0, 0.34):
                    ev_idx = len(feed)
                    sxg = _shot_xg(shooter, atk, dfn, atk_tag, ev_idx, match_id)
                    score_goal(minute, shooter, atk_tag, sxg,
                               assister=assist_for(atk, shooter))
                    set_holder_of(dfn)
                else:
                    ev_idx = len(feed)
                    sxg = _shot_xg(shooter, atk, dfn, atk_tag, ev_idx, match_id)
                    emit(minute, "shot", f"{minute}' · shot in extra time ({atk_tag})",
                         side=atk_tag, player_id=shooter,
                         extra={"on_target": False, "blocked": False, "xG": round(sxg, 3)})
        emit(121, "extra_time_end", f"121' · End of extra time · {_fmt(hg, ag)}",
             extra={"score": _fmt(hg, ag)})
        if hg != ag:
            reason = "extra_time"
        else:
            # -------------------------------------------------- shootout
            reason = "penalties"
            emit(121, "penalties_start", "Penalty shootout — best of five")
            made = {"home": 0, "away": 0}
            kicks = {"home": 0, "away": 0}
            total_kicks = 0

            def take_penalty(side_k: str) -> None:
                nonlocal total_kicks
                total_kicks += 1
                atk_s = home if side_k == "home" else away
                gk_s = away if side_k == "home" else home
                kicker = _named_taker(atk_s, "penalty") or best_attacker(atk_s) or (atk_s.on_pitch[0] if atk_s.on_pitch else None)
                skill = group_skill(atk_s.profiles.get(kicker, {}), "shooting")
                p_make = _clamp(0.74 + (skill - gk_s.gk) / 600.0, 0.5, 0.95)
                scored = rng.random() < p_make
                if scored:
                    made[side_k] += 1
                kicks[side_k] += 1
                emit(121 + total_kicks, "penalty",
                     f"PEN {side_k} · {pname(kicker)} {'scores' if scored else 'misses'} "
                     f"· {made['home']}-{made['away']}",
                     side=side_k, player_id=kicker, extra={"made": bool(scored)})

            def shootout_winner() -> Optional[str]:
                """The winning side once the shootout is mathematically decided.

                Regulation (first five rounds each): the shootout ends when the
                trailing side cannot even draw level by scoring every one of its
                remaining regulation kicks. After five rounds each, a level score
                rolls into sudden death, which is decided only once a side leads
                after an equal number of sudden-death kicks.
                """
                kh, ka = kicks["home"], kicks["away"]
                mh, ma = made["home"], made["away"]
                if kh < 5 or ka < 5:
                    if mh > ma and mh - ma > 5 - ka:
                        return "home"
                    if ma > mh and ma - mh > 5 - kh:
                        return "away"
                    return None
                if kh == ka:  # sudden death — decide only at equal kick counts
                    if mh > ma:
                        return "home"
                    if ma > mh:
                        return "away"
                return None

            # alternating kicks (home first) until the winner is certain
            while True:
                winner = shootout_winner()
                if winner is not None:
                    break
                take_penalty("home")
                winner = shootout_winner()
                if winner is not None:
                    break
                take_penalty("away")
            pen_h, pen_a = made["home"], made["away"]
            emit(121 + total_kicks + 1, "penalties_end",
                 f"Shootout {pen_h}-{pen_a} · "
                 f"{'home' if pen_h > pen_a else 'away'} win on penalties",
                 side=winner,
                 extra={"score": _fmt(pen_h, pen_a)})
    else:
        emit(90, "full_time", f"90' · FT · {_fmt(hg, ag)}", extra={"score": _fmt(hg, ag)})

    # -------------------------------------------------------------- points
    if reason in ("extra_time", "penalties"):
        if (hg > ag) or (hg == ag and pen_h > pen_a):
            hp, ap = POINTS_WIN, POINTS_LOSS
        else:
            hp, ap = POINTS_LOSS, POINTS_WIN
    elif hg > ag:
        hp, ap = POINTS_WIN, POINTS_LOSS
    elif ag > hg:
        hp, ap = POINTS_LOSS, POINTS_WIN
    else:
        hp = ap = POINTS_DRAW

    spatialize()

    # Phase stream is a pure function of the finished feed + lineups, so it is
    # built here (lazy import: phases imports match_engine for pitch constants).
    from gaming.src.stack.agentic.games.football_managers.phases import build_phase_stream

    player_stats = derive_player_stats(
        feed, match_id, home_agent_id, away_agent_id, hg, ag,
        home_xi=list(home_xi), away_xi=list(away_xi),
    )

    # final condition per player (0..1): what the season carries into the next
    # matchday so tired legs, subs and minutes bite across fixtures (G4)
    def _final_fatigue(s: _SideState) -> dict[str, float]:
        out: dict[str, float] = {}
        for pid in list(s.xi) + list(s.bench):
            prof = s.profiles.get(pid)
            if prof:
                out[pid] = round(_clamp(float(prof.get("fitness", 1.0)), 0.05, 1.0), 3)
        return out

    return MatchResult(
        match_id=match_id,
        home_agent_id=home_agent_id,
        away_agent_id=away_agent_id,
        home_goals=hg,
        away_goals=ag,
        feed=feed,
        home_points=hp,
        away_points=ap,
        reason=reason,
        home_pen_goals=pen_h,
        away_pen_goals=pen_a,
        phases=build_phase_stream(
            match_id,
            feed,
            list(home_xi),
            list(away_xi),
            str((home_tactics or {}).get("formation") or "4-3-3"),
            str((away_tactics or {}).get("formation") or "4-3-3"),
        ),
        player_stats=player_stats,
        fatigue={
            "home": _final_fatigue(home),
            "away": _final_fatigue(away),
        },
    )
