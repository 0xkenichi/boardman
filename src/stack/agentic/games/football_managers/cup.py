"""AFM knockout cup service — single-elimination, draws must produce a winner.

Runs alongside the season on the daily clock (docs/games/AGENTIC_FOOTBALL_
MANAGERS_GAME.md). While the league hands out 3/1/0 points for draws, a
knockout tie cannot stand level: every fixture is resolved on the engine
with `require_result=True`, so a draw after 90' goes to extra time and, if
still level, a penalty shootout — there is never a drawn decider.

Lifecycle, mirrored from `season.py`:

  open cup    → a knockout bracket is built from the entered agent clubs
                (first-round byes when the field is not a power of two)
  daily tick  → a round opens on its slot; at its deadline the ties resolve
                on the deterministic engine using each club's locked legal
                XI + bench + tactics (the club's saved lineup — managers'
                decide loop keeps it fresh); winners advance
  cup end     → the last round's winner is crowned champion

Design points:

  * Single-elimination, deterministic: a tie's match_id derives from the
    cup number + round + tie + the two agent ids, so a finished tie is
    auditable and replayable like a season fixture (same seed → same feed).
  * A cup tie's result is a full `MatchResult.to_dict()` (score, outcome,
    stats, minute feed, locked lineups) stored on the tie.
  * No money in v0: cup fixtures reuse the clubs' lineups without debiting
    wages or settling stakes (season matchday rails handle money).
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.season import (
    _club_display,
    _ids,
    _xi_for_club,
)
from gaming.src.stack.agentic.store import load_json, save_json

STATE_FILE = "afm_cup.json"

# schedule (daily cadence, same defaults as the season)
CADENCE_HOURS = 24
LOCK_HOURS = 6

_lock = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _state() -> dict[str, Any]:
    return load_json(STATE_FILE, {"cup": None, "history": []})


def _save(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


# ---------------------------------------------------------------- bracket


def build_bracket(agent_ids: list[str]) -> list[dict[str, Any]]:
    """Single-elimination rounds over the entered agents.

    Returns a list of round descriptors:

      [{"round_no": 1, "ties": [
           {"key": "R1-T0", "home_agent_id": ..., "away_agent_id": ...},
           {"key": "R1-T1", "home_agent_id": ..., "away_agent_id": None},  # bye
       ]}, ...]

    Rounds are numbered 1..ceil(log2 n). Round 1 is concrete: the first
    (n - 2^ceil) non-bye slots... non-power-of-two fields get first-round
    byes drawn from the top of the field ("top seeds"), and round-1 ties are
    the remaining teams paired in order. Later rounds are keyed placeholders
    whose two sides are only known once the previous round resolves (the
    service fills them from the ordered winners) — they are strict
    power-of-two pairings.
    """
    ids = list(dict.fromkeys(agent_ids))
    if len(ids) < 2:
        raise ValueError("a cup needs at least two entering clubs")
    rounds_needed = max(1, (len(ids) - 1).bit_length())
    byes = 2 ** rounds_needed - len(ids)

    rounds: list[dict[str, Any]] = []
    # round 1 — the last (n - byes) clubs play ((n - byes) is even), the first
    # `byes` rest. Byes are appended after the real ties, so a bye never meets
    # another bye in round 1 and the real knockout is front-loaded.
    r1: list[dict[str, Any]] = []
    for i in range(byes, len(ids) - 1, 2):
        r1.append(
            {
                "key": f"R1-T{len(r1)}",
                "round_no": 1,
                "home_agent_id": ids[i],
                "away_agent_id": ids[i + 1],
            }
        )
    for team in ids[:byes]:
        r1.append(
            {
                "key": f"R1-T{len(r1)}",
                "round_no": 1,
                "home_agent_id": team,
                "away_agent_id": None,  # bye — advances without playing
            }
        )
    rounds.append({"round_no": 1, "ties": r1})

    for r in range(2, rounds_needed + 1):
        n_ties = 2 ** (rounds_needed - r)
        rounds.append(
            {
                "round_no": r,
                "ties": [
                    {
                        "key": f"R{r}-T{i}",
                        "round_no": r,
                        "home_agent_id": None,  # filled at resolve time from winners
                        "away_agent_id": None,
                    }
                    for i in range(n_ties)
                ],
            }
        )
    return rounds


def _winner_of(tie: dict[str, Any]) -> Optional[str]:
    """The team that holds the tie's slot, in bracket order (None until played)."""
    if tie.get("status") == "played":
        return tie.get("winner_agent_id")
    if tie.get("away_agent_id") is None and tie.get("home_agent_id"):
        return tie.get("home_agent_id")  # a bye already owns its slot
    return None


# ---------------------------------------------------------------- cup ops


def _round_open_at(c: dict[str, Any], round_no: int) -> datetime:
    start = _parse(c.get("started_at")) or _now()
    return start + timedelta(hours=int(c.get("cadence_hours", CADENCE_HOURS)) * (round_no - 1))


def _round_deadline(c: dict[str, Any], round_no: int) -> datetime:
    return _round_open_at(c, round_no) + timedelta(hours=int(c.get("lock_hours", LOCK_HOURS)))


def get_cup() -> Optional[dict[str, Any]]:
    c = _state().get("cup")
    return _snapshot(c) if c else None


def open_cup(
    agent_ids: Optional[list[str]] = None,
    *,
    start_at: Optional[datetime] = None,
    title: Optional[str] = None,
    salt: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Open a knockout cup over the entering agent clubs.

    Default entrants: every club that owns an AFM roster (v0 — no entry fee,
    no money moves). Pass explicit `agent_ids` to restrict the field, `salt`
    to control the seeded match ids (tests / replay fixtures), and `force`
    to replace an unfinished cup.
    """
    with _lock:
        st = _state()
        cur = st.get("cup")
        if cur and cur.get("status") == "open" and not force:
            raise ValueError("a cup is already running — tick it, finish it, or force a new one")

        from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

        clubs = {cl["agent_id"]: cl for cl in list_clubs()}
        if agent_ids is None:
            ids = sorted(clubs)
        else:
            ids = sorted(set(a for a in dict.fromkeys(agent_ids) if a in clubs))
        if len(ids) < 2:
            raise ValueError("need at least two clubs with AFM rosters to open a cup")

        history = st.get("history") or []
        no = 1 + max([int(h.get("cup_no") or 0) for h in history] + [0])
        if cur:
            no = max(no, int(cur.get("cup_no") or 0) + 1)

        bracket = build_bracket(ids)
        start = start_at or _now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        cup: dict[str, Any] = {
            "cup_no": no,
            "title": title or f"Agentic Cup #{no}",
            "status": "open",
            "salt": salt or f"afm_cup_{no}",
            "division": ids,
            "rounds_total": len(bracket),
            "current_round": 1,
            "cadence_hours": CADENCE_HOURS,
            "lock_hours": LOCK_HOURS,
            "started_at": _iso(start),
            "rounds": {},
            "champion": None,
            "finished_at": None,
            "created_at": _iso(_now()),
            "updated_at": _iso(_now()),
        }
        st["cup"] = cup
        _save(st)
        return _snapshot(cup)


def tick(now: Optional[datetime] = None) -> dict[str, Any]:
    """Advance the cup clock: open due rounds, resolve past deadlines.

    Rounds resolve one at a time (a round's pairings depend on the previous
    round's winners). Idempotent: played ties never re-resolve, so API,
    keeper and humans can all trigger it safely.
    """
    now = now or _now()
    with _lock:
        st = _state()
        c = st.get("cup")
        if not c or c.get("status") != "open":
            return {"action": "idle", "reason": "no open cup", "cup_status": c.get("status") if c else None}
        no = int(c["cup_no"])
        total = int(c["rounds_total"])
        r = int(c["current_round"])
        opened: list[int] = []
        resolved: list[int] = []
        while r <= total:
            if now < _round_open_at(c, r):
                break
            rinfo = c.get("rounds", {}).get(str(r))
            if rinfo is None:
                rinfo = _open_round(c, r)
                opened.append(r)
            if now < _round_deadline(c, r):
                break
            _resolve_round(c, rinfo)
            resolved.append(r)
            c["current_round"] = r + 1
            r += 1
        if c["current_round"] > total:
            _finish_cup(c)
        c["updated_at"] = _iso(_now())
        _save(st)
        return {
            "action": "tick",
            "cup_no": no,
            "opened": opened,
            "resolved": resolved,
            "current_round": int(c["current_round"]),
            "cup_status": c["status"],
            "champion": c.get("champion"),
        }


def reset_cup() -> dict[str, Any]:
    with _lock:
        st = _state()
        st["cup"] = None
        _save(st)
    return {"reset": True}


# ---------------------------------------------------------------- internals


def _participants_for_round(c: dict[str, Any], round_no: int) -> list[str]:
    """Teams qualified to play `round_no`, in bracket order."""
    prev = c.get("rounds", {}).get(str(round_no - 1)) if round_no > 1 else None
    if prev is None:
        return list(c["division"])
    winners: list[str] = []
    for tie in prev.get("ties") or []:
        w = _winner_of(tie)
        if w:
            winners.append(w)
    return winners


def _open_round(c: dict[str, Any], round_no: int) -> dict[str, Any]:
    """Create the round's tie records (participants known only now).

    Round 1 mirrors `build_bracket` exactly (top-seed byes + real ties over
    the rest of the field, in division order). Later rounds pair the previous
    round's ordered winners against each other — always a power-of-two field.
    """
    bracket_round = build_bracket(c["division"])[round_no - 1]
    template = bracket_round["ties"]
    if round_no == 1:
        teams = list(c["division"])
        byes = 2 ** int(c["rounds_total"]) - len(teams)
        play = len(teams) - byes  # real round-1 ties are over these teams
    else:
        teams = _participants_for_round(c, round_no)  # previous round's winners
        byes = 0
        play = len(teams)

    ties: list[dict[str, Any]] = []
    for i, slot in enumerate(template):
        if round_no == 1:
            if i < play // 2:  # a real tie: two of the non-bye clubs
                home, away = teams[byes + 2 * i], teams[byes + 2 * i + 1]
                bye = False
            else:  # a bye: one of the top seeds rests into round 2
                home, away, bye = teams[i - play // 2], None, True
        else:
            home = teams[2 * i] if 2 * i < len(teams) else None
            away = teams[2 * i + 1] if 2 * i + 1 < len(teams) else None
            bye = home is not None and away is None
        ties.append(
            {
                "key": slot["key"],
                "round_no": round_no,
                "home_agent_id": home,
                "away_agent_id": away,
                "bye": bye,
                "status": "played" if bye else "scheduled",
                "winner_agent_id": home if bye else None,
                "match_id": None,
                "result": None,
                "resolved_at": None,
            }
        )
    rinfo: dict[str, Any] = {
        "round_no": round_no,
        "status": "played" if all(t["status"] == "played" for t in ties) else "open",
        "open_at": _iso(_round_open_at(c, round_no)),
        "deadline_at": _iso(_round_deadline(c, round_no)),
        "ties": ties,
        "resolved_at": None,
    }
    c.setdefault("rounds", {})[str(round_no)] = rinfo
    return rinfo


def _resolve_round(c: dict[str, Any], rinfo: dict[str, Any]) -> None:
    """Simulate every scheduled tie on the deterministic engine (winner required)."""
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match

    no = int(c["cup_no"])
    salt = str(c.get("salt") or f"afm_cup_{no}")
    round_no = int(rinfo["round_no"])
    for tie in rinfo.get("ties") or []:
        if tie.get("status") == "played":
            continue  # bye — already advanced; never double-resolve
        home, away = tie.get("home_agent_id"), tie.get("away_agent_id")
        if not home or not away:
            continue
        mid = f"{salt}_r{round_no}_{tie['key'].replace('-', 'T')}_{home}_{away}"
        lineups: dict[str, dict[str, Any]] = {}
        auto: list[str] = []
        for aid in (home, away):
            club = get_club(aid) or {}
            xi, defaulted = _xi_for_club(club)
            if defaulted:
                auto.append(aid)
            lineups[aid] = {
                "xi": xi,
                "bench": _ids(club.get("bench")),
                "formation": club.get("formation") or "4-3-3",
                "tags": list(club.get("tactical_tags") or ["balanced"]),
            }
        res = simulate_match(
            mid,
            home_agent_id=home,
            away_agent_id=away,
            home_xi=lineups[home]["xi"],
            away_xi=lineups[away]["xi"],
            home_bench=lineups[home]["bench"],
            away_bench=lineups[away]["bench"],
            home_tactics={"formation": lineups[home]["formation"], "tags": lineups[home]["tags"]},
            away_tactics={"formation": lineups[away]["formation"], "tags": lineups[away]["tags"]},
            require_result=True,  # knockout: a draw goes to extra time / penalties
        ).to_dict()
        outcome = res.get("outcome")
        winner = home if outcome == "home_win" else away if outcome == "away_win" else None
        res["home_club"] = _club_display(home)
        res["away_club"] = _club_display(away)
        res["lineups"] = lineups
        tie["match_id"] = mid
        tie["result"] = res
        tie["winner_agent_id"] = winner
        tie["auto"] = auto
        tie["status"] = "played"
        tie["resolved_at"] = _iso(_now())
    rinfo["status"] = "played"
    rinfo["resolved_at"] = _iso(_now())


def _finish_cup(c: dict[str, Any]) -> None:
    if c.get("status") != "open":
        return  # defensive — tick guards, never crown twice
    final_round = c.get("rounds", {}).get(str(int(c["rounds_total"])))
    winners = [_winner_of(t) for t in (final_round or {}).get("ties") or [] if _winner_of(t)]
    c["champion"] = winners[0] if winners else None
    c["status"] = "finished"
    c["finished_at"] = _iso(_now())
    st = _state()
    st.setdefault("history", []).append(c)
    _save(st)


# ---------------------------------------------------------------- replay


def get_cup_replay(round_no: int, home: str, away: str) -> dict[str, Any]:
    """A recorded cup tie, replayable end-to-end (feed + locked lineups).

    Stored ties carry the full engine result. For legacy state that only
    holds summaries, the tie is reconstructed deterministically from the
    locked lineups (same seed → same match).
    """
    c = _state().get("cup")
    if not c:
        raise ValueError("no cup running")
    rinfo = c.get("rounds", {}).get(str(round_no)) or {}
    tie = next(
        (
            t
            for t in rinfo.get("ties") or []
            if t.get("home_agent_id") == home and t.get("away_agent_id") == away
        ),
        None,
    )
    if tie is None:
        raise ValueError(f"no cup replay for round {round_no}: {home} vs {away}")
    result = tie.get("result")
    if (result is None or not result.get("feed")) and tie.get("home_agent_id") and tie.get("away_agent_id"):
        result = _reconstruct_tie(c, round_no, tie)
    if result is None:
        raise ValueError(f"no replay data for round {round_no}: {home} vs {away}")

    def side(aid: str) -> dict[str, Any]:
        from gaming.src.stack.agentic.games.football_managers.catalog import get_player
        from gaming.src.stack.agentic.games.football_managers.club_store import get_club

        lu = (result.get("lineups") or {}).get(aid) or {}
        club = get_club(aid) or {}
        xi = []
        for pid in lu.get("xi") or []:
            p = get_player(pid) or {}
            xi.append(
                {
                    "player_id": pid,
                    "name": p.get("name") or pid,
                    "slot": str(p.get("slot") or "").upper(),
                    "primary_pos": str(p.get("primary_pos") or "MID").upper(),
                    "base_rating": p.get("base_rating") or 70,
                }
            )
        return {
            "agent_id": aid,
            "club_name": club.get("club_name") or _club_display(aid),
            "formation": lu.get("formation") or club.get("formation") or "4-3-3",
            "tags": list(lu.get("tags") or club.get("tactical_tags") or ["balanced"]),
            "xi": xi,
        }

    return {
        "cup_no": int(c["cup_no"]),
        "round": round_no,
        "tie": tie["key"],
        "match_id": tie.get("match_id") or result.get("match_id"),
        "result": result,
        "home": side(home),
        "away": side(away),
        "bye": bool(tie.get("bye")),
    }


def _reconstruct_tie(
    c: dict[str, Any], round_no: int, tie: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Re-run the deterministic engine for a tie whose feed was not stored."""
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match

    home, away = tie.get("home_agent_id"), tie.get("away_agent_id")
    if not home or not away:
        return None
    lineups: dict[str, dict[str, Any]] = {}
    for aid in (home, away):
        club = get_club(aid) or {}
        xi, _ = _xi_for_club(club)
        lineups[aid] = {
            "xi": xi,
            "bench": _ids(club.get("bench")),
            "formation": club.get("formation") or "4-3-3",
            "tags": list(club.get("tactical_tags") or ["balanced"]),
        }
    no = int(c["cup_no"])
    salt = str(c.get("salt") or f"afm_cup_{no}")
    mid = tie.get("match_id") or f"{salt}_r{round_no}_{tie['key'].replace('-', 'T')}_{home}_{away}"
    res = simulate_match(
        mid,
        home_agent_id=home,
        away_agent_id=away,
        home_xi=lineups[home]["xi"],
        away_xi=lineups[away]["xi"],
        home_bench=lineups[home]["bench"],
        away_bench=lineups[away]["bench"],
        home_tactics={"formation": lineups[home]["formation"], "tags": lineups[home]["tags"]},
        away_tactics={"formation": lineups[away]["formation"], "tags": lineups[away]["tags"]},
        require_result=True,
    ).to_dict()
    res["home_club"] = _club_display(home)
    res["away_club"] = _club_display(away)
    res["lineups"] = lineups
    return res


# ---------------------------------------------------------------- snapshot


def _summary(result: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not result:
        return {}
    return {
        "match_id": result.get("match_id"),
        "score": result.get("score"),
        "home_goals": result.get("home_goals"),
        "away_goals": result.get("away_goals"),
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "home_pen_goals": result.get("home_pen_goals"),
        "away_pen_goals": result.get("away_pen_goals"),
        "engine": result.get("engine"),
    }


def _snapshot(c: dict[str, Any]) -> dict[str, Any]:
    from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

    names = {cl["agent_id"]: cl.get("club_name") or _club_display(cl["agent_id"]) for cl in list_clubs()}
    rounds_out: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    for r in range(1, int(c["rounds_total"]) + 1):
        rinfo = c.get("rounds", {}).get(str(r)) or {}
        ties_out = []
        for t in rinfo.get("ties") or []:
            h, a = t.get("home_agent_id"), t.get("away_agent_id")
            ties_out.append(
                {
                    "key": t["key"],
                    "round_no": t.get("round_no"),
                    "status": t.get("status"),
                    "bye": bool(t.get("bye")),
                    "home_agent_id": h,
                    "home_club": names.get(h, h) if h else None,
                    "away_agent_id": a,
                    "away_club": names.get(a, a) if a else None,
                    "winner_agent_id": t.get("winner_agent_id"),
                    "auto": t.get("auto") or [],
                    **_summary(t.get("result")),
                }
            )
            if t.get("status") == "played" and not t.get("bye"):
                recent.append({"round": r, **_summary(t.get("result"))})
        rounds_out.append(
            {
                "round_no": r,
                "status": (rinfo or {}).get("status", "scheduled"),
                "open_at": (rinfo or {}).get("open_at") or _iso(_round_open_at(c, r)),
                "deadline_at": (rinfo or {}).get("deadline_at") or _iso(_round_deadline(c, r)),
                "ties": ties_out,
            }
        )
    return {
        "cup_no": int(c["cup_no"]),
        "title": c.get("title"),
        "status": c["status"],
        "division": [{"agent_id": a, "name": names.get(a, _club_display(a))} for a in c["division"]],
        "rounds_total": int(c["rounds_total"]),
        "current_round": int(c["current_round"]),
        "started_at": c.get("started_at"),
        "champion": c.get("champion"),
        "champion_club": names.get(c.get("champion"), c.get("champion")) if c.get("champion") else None,
        "finished_at": c.get("finished_at"),
        "rounds": rounds_out,
        "recent": recent,
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
    }
