"""Living player state — the FM layer: morale, form and development.

Phase 0 attributes are derived deterministically from a player's identity, so
they never move. This module adds the *state* half: a small per-player record
that the season tick updates after every resolved fixture and that the engine
consumes at lock time (snapshot → simulate, so recorded replays stay honest):

  morale   0..1 — team result moves it (win up, loss down), personal events
           move it more (goals lift, cards dent); bounded so a crisis never
           zeroes a player out.
  form     an EMA "last five matches" marker on the 4..9.5 scale the catalog
           uses; shown on squad screens and carried in the matchday ask so
           managers can reason about who is hot.
  delta    development — young legs with minutes trend upward, veterans trend
           down; applied as a rating adjustment at lock time (bounded ±small
           so a season of growth is a story, not a cheat).

State lives in data/agentic/afm_living.json under the same BOARDMAN_AGENTIC_DATA
store as everything else. All updates are idempotent per fixture (keyed by
match_id) so a replayed resolve never double-applies.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

_FILE = "afm_living.json"
_lock = threading.RLock()

MORALE_MIN = 0.35
MORALE_MAX = 1.0
DELTA_MIN = -1.5
DELTA_MAX = 2.5
FORM_MIN = 4.0
FORM_MAX = 9.5

# team-result morale swings (full 90) — a win lifts, a loss dents, a draw idles
MORALE_WIN = 0.055
MORALE_DRAW = 0.005
MORALE_LOSS = -0.055
# personal-event morale nudges
MORALE_GOAL = 0.03
MORALE_ASSIST = 0.02
MORALE_YELLOW = -0.015
MORALE_RED = -0.06
# development per matchday (scaled by minutes/90 and form)
DEV_YOUNG = 0.012
DEV_VETERAN = -0.008


def _now_key() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load() -> dict[str, dict[str, Any]]:
    from gaming.src.stack.agentic.store import load_json

    return load_json(_FILE, {"players": {}, "applied": {}})


def _save(data: dict[str, Any]) -> None:
    from gaming.src.stack.agentic.store import save_json

    save_json(_FILE, data)


def stage(player_id: str) -> tuple[str, int]:
    """A player's deterministic career stage: (stage, pseudo-age).

    The catalog carries no ages, so — like every Phase 0 attribute — the
    career stage is derived from the player's stable identity: ~22% young
    (21-23), ~15% veterans (31-34), the rest in their prime (24-30).
    """
    from gaming.src.stack.agentic.games.football_managers.attributes import _hash01

    r = _hash01(str(player_id), "career_stage")
    if r < 0.22:
        return "young", 21 + int(_hash01(str(player_id), "age_young") * 3)
    if r > 0.85:
        return "veteran", 31 + int(_hash01(str(player_id), "age_vet") * 4)
    return "prime", 24 + int(_hash01(str(player_id), "age_prime") * 7)


def _default(pid: str) -> dict[str, Any]:
    _stage, age = stage(pid)
    return {
        "morale": 0.72,
        "form": 6.5,
        "apps": 0,
        "minutes": 0,
        "goals": 0,
        "assists": 0,
        "delta": 0.0,
        "age": age,
        "stage": _stage,
        "updated_at": _now_key(),
    }


def get(pid: str) -> dict[str, Any]:
    with _lock:
        data = _load()
        rec = (data["players"].get(str(pid)) or {}).get("state")
        if rec:
            return dict(rec)
        return _default(pid)


def get_many(pids: list[str]) -> dict[str, dict[str, Any]]:
    with _lock:
        data = _load()
        out: dict[str, dict[str, Any]] = {}
        for pid in pids:
            rec = (data["players"].get(str(pid)) or {}).get("state")
            out[str(pid)] = dict(rec) if rec else _default(pid)
        return out


def snapshot(pids: list[str]) -> dict[str, dict[str, float]]:
    """The lock-time snapshot the engine consumes: {pid: {morale, delta}}."""
    states = get_many(list(pids))
    return {
        pid: {
            "morale": max(MORALE_MIN, min(MORALE_MAX, float(s["morale"]))),
            "delta": max(DELTA_MIN, min(DELTA_MAX, float(s["delta"]))),
        }
        for pid, s in states.items()
    }


def _clamp_morale(v: float) -> float:
    return max(MORALE_MIN, min(MORALE_MAX, v))


def _minutes_from_feed(feed: list[dict[str, Any]], xi: list[str]) -> dict[str, int]:
    """Minutes on pitch per player: starters from kickoff, subs from their entry."""
    mins = {pid: 90 for pid in xi}
    for ev in feed or []:
        if ev.get("type") != "substitution":
            continue
        on = ev.get("in")
        off = ev.get("off")
        minute = int(ev.get("minute") or 90)
        if off:
            # replaced: his minutes end at the substitution, not at full time
            mins[str(off)] = min(int(mins.get(str(off), 90)), minute)
        if on:
            mins[str(on)] = max(0, 90 - minute)
    return mins


def apply_matchday(
    match_id: str,
    result: dict[str, Any],
    home_xi: list[str],
    home_bench: list[str],
    away_xi: list[str],
    away_bench: list[str],
) -> dict[str, Any]:
    """Evolve living state for one resolved fixture. Idempotent per match_id.

    Reads the stored feed (goals/assists/cards/subs) and the scoreline; every
    involved player's morale, form and development move accordingly.
    """
    with _lock:
        data = _load()
        applied = data.setdefault("applied", {})
        if match_id in applied:
            return {"applied": False, "reason": "already applied"}

        hg = int(result.get("home_goals") or 0)
        ag = int(result.get("away_goals") or 0)
        feed = result.get("feed") or []

        sides: list[tuple[str, list[str], list[str]]] = [
            ("home", list(home_xi), list(home_bench or [])),
            ("away", list(away_xi), list(away_bench or [])),
        ]

        outcomes = {}
        if hg > ag:
            outcomes["home"] = MORALE_WIN
            outcomes["away"] = MORALE_LOSS
        elif ag > hg:
            outcomes["home"] = MORALE_LOSS
            outcomes["away"] = MORALE_WIN
        else:
            outcomes["home"] = MORALE_DRAW
            outcomes["away"] = MORALE_DRAW

        # personal events from the feed
        goals: dict[str, int] = {}
        assists: dict[str, int] = {}
        yellows: dict[str, int] = {}
        reds: dict[str, int] = {}
        for ev in feed:
            t = ev.get("type")
            pid = str(ev.get("player_id") or "")
            if not pid:
                continue
            if t == "goal":
                goals[pid] = goals.get(pid, 0) + 1
                a = str((ev.get("extra") or {}).get("assist") or "")
                if a:
                    assists[a] = assists.get(a, 0) + 1
            elif t == "yellow":
                yellows[pid] = yellows.get(pid, 0) + 1
            elif t == "red":
                reds[pid] = reds.get(pid, 0) + 1

        touched: dict[str, dict[str, Any]] = {}
        # one shared state cache for both sides: each player's record is read
        # once per fixture, so the side passes can never clobber each other
        everyone = list(dict.fromkeys(
            [pid for _side, s_xi, s_bench in sides for pid in s_xi + s_bench]
        ))
        states = get_many(everyone)
        for side, xi, bench in sides:
            mins = _minutes_from_feed(feed, xi)
            team_delta = outcomes[side]
            for pid in dict.fromkeys(xi + bench):
                st = states[pid]
                m = float(mins.get(pid, 0))
                if m <= 0 and pid in bench:
                    # unused bench: tiny idle drift only
                    st["morale"] = _clamp_morale(float(st["morale"]) + team_delta * 0.1)
                    touched[pid] = st
                    continue
                share = min(1.0, m / 90.0)
                dm = team_delta * share
                dm += MORALE_GOAL * goals.get(pid, 0)
                dm += MORALE_ASSIST * assists.get(pid, 0)
                dm += MORALE_YELLOW * yellows.get(pid, 0)
                dm += MORALE_RED * reds.get(pid, 0)
                st["morale"] = _clamp_morale(float(st["morale"]) + dm)

                # form EMA on the 4..9.5 scale
                personal = (
                    6.0
                    + (0.8 if team_delta > 0.01 else -0.8 if team_delta < -0.01 else 0.0)
                    + 0.7 * goals.get(pid, 0)
                    + 0.4 * assists.get(pid, 0)
                    - 0.4 * reds.get(pid, 0)
                )
                personal = max(FORM_MIN, min(FORM_MAX, personal))
                st["form"] = round(max(FORM_MIN, min(FORM_MAX, 0.75 * float(st["form"]) + 0.25 * personal)), 2)

                # development: young legs with real minutes grow, veterans fade
                _stage = st.get("stage") or stage(pid)[0]
                form_boost = 1.0 + (float(st["form"]) - 6.5) * 0.2
                if _stage == "young" and m >= 30:
                    st["delta"] = min(DELTA_MAX, float(st["delta"]) + DEV_YOUNG * share * form_boost)
                elif _stage == "veteran" and m >= 30:
                    st["delta"] = max(DELTA_MIN, float(st["delta"]) + DEV_VETERAN * share * max(0.6, form_boost))

                st["apps"] = int(st.get("apps") or 0) + 1
                st["minutes"] = int(st.get("minutes") or 0) + m
                st["goals"] = int(st.get("goals") or 0) + goals.get(pid, 0)
                st["assists"] = int(st.get("assists") or 0) + assists.get(pid, 0)
                st["updated_at"] = _now_key()
                touched[pid] = st

        for pid, st in touched.items():
            entry = data["players"].setdefault(str(pid), {})
            entry["state"] = st
        applied[match_id] = _now_key()
        _save(data)
        return {"applied": True, "players": len(touched)}


def apply_surprises(match_id: str, events: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Absorb pre-match surprise events (refs.py) as living-state dents.

    `events` is {player_id: surprise_event} — each carries a `dent` (+ lifts
    morale for good news, − dents it for bad) plus a `label`. The layer:

    * persists the dent into each player's morale (bounded by the usual
      clamps) so the mood carries into *later* fixtures too, not just this
      one — the next snapshot reads it;
    * is idempotent per fixture via a `"{match_id}#surprise"` key in the
      applied ledger, so a replayed resolve never double-applies.

    The caller (season resolve) additionally overrides this fixture's
    lock-time snapshot with the same dent, so the match itself plays with
    the disturbed mind even before the persistent state absorbs it.
    """
    if not events:
        return {"applied": False, "reason": "no events"}
    with _lock:
        data = _load()
        applied = data.setdefault("applied", {})
        key = f"{match_id}#surprise"
        if key in applied:
            return {"applied": False, "reason": "already applied"}

        touched = 0
        for pid, ev in events.items():
            try:
                dent = float(ev.get("dent") or 0.0)
            except (TypeError, ValueError):
                continue
            if dent == 0.0:
                continue
            entry = data["players"].setdefault(str(pid), {})
            st = entry.get("state") or _default(str(pid))
            st["morale"] = _clamp_morale(float(st["morale"]) + dent)
            st["updated_at"] = _now_key()
            entry["state"] = st
            touched += 1
        applied[key] = _now_key()
        _save(data)
        return {"applied": True, "players": touched}


def morale_form_map(pids: Optional[list[str]] = None) -> dict[str, dict[str, float]]:
    """{pid: {morale, form}} for ask payloads and squad screens."""
    with _lock:
        data = _load()
        players = data["players"]
        if pids is None:
            pids = list(players.keys())
        out: dict[str, dict[str, float]] = {}
        for pid in pids:
            rec = (players.get(str(pid)) or {}).get("state")
            st = rec if rec else _default(pid)
            out[str(pid)] = {
                "morale": round(_clamp_morale(float(st["morale"])), 2),
                "form": round(float(st["form"]), 2),
            }
        return out


def reset_all() -> None:
    """Dev/ops: clear the living store (season resets do not call this)."""
    with _lock:
        _save({"players": {}, "applied": {}})
