"""AFM season league service — the game heartbeat.

Runs a division season on the daily clock (docs/games/AGENTIC_FOOTBALL_
MANAGERS_GAME.md):

  open season   → entries are paid into the season pot (USDC), schedule built
  daily tick    → a matchday opens at its slot; at its deadline the XIs are
                  locked (auto-fallback to the club's saved legal XI), wages
                  are debited, fixtures resolve on the deterministic engine,
                  matchday stakes settle through the ledger, standings update
  season end    → champion crowned, season pot paid out 70/30 (M=2) or
                  60/25/15 (M>=3)

Insolvency is tolerated, never fatal: if a club cannot cover wages or its
stake, the shortfall accrues as debt (wage_debt / stake_debt) and the club
still fields a legal XI. House never plays.
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic import ledger as L
from gaming.src.stack.agentic.games.football_managers.league import (
    Row,
    apply_result,
    new_standings,
    ranked,
    schedule_season,
    season_outcome,
)
from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match  # noqa: F401 (re-exported for the API/tests)

__all__ = [
    "open_season",
    "join_season",
    "tick",
    "reset_season",
    "get_season",
    "news_feed",
    "prematch_view",
    "replay_press_conference",
    "transcript_for_fixture",
    "get_matchday_transcript",
    "press_conference_for",
    "matchday_news_items",
    "simulate_match",
]

# lazy registry helper so season.py never imports the registry at module load
# and accidentally pull a heavy runtime path into the engine-only tests.
_reg = None


def _reg():
    global _reg
    if _reg is None:
        from gaming.src.stack.agentic.registry import get_registry

        _reg = get_registry
    return _reg()


PRESS_CONFERENCE_QUESTIONS = {
    "pre": [
        "What is your game plan for this matchday?",
        "Who is your key player this matchday and why?",
        "How are you preparing for the opposition's style?",
    ],
    "post": [
        "How do you rate your team's performance today?",
        "What will you change after this result?",
        "Any comments on the refereeing?",
    ],
}
from gaming.src.stack.agentic.store import load_json, save_json

STATE_FILE = "afm_season.json"

# money (USDC, v1 defaults)
SEASON_ENTRY_USDC = Decimal("25.00")
MATCH_STAKE_USDC = Decimal("5.00")
DEMO_FAUCET_FLOOR = Decimal("600.00")  # so a full derby season settles cleanly
SEASON_POT_SHARES_2 = (Decimal("0.70"), Decimal("0.30"))
SEASON_POT_SHARES_N = (Decimal("0.60"), Decimal("0.25"), Decimal("0.15"))

# schedule (daily cadence)
CADENCE_HOURS = 24
LOCK_HOURS = 6  # agents have until kickoff (deadline) to set lineups

_lock = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _state() -> dict[str, Any]:
    return load_json(STATE_FILE, {"season": None, "pending_joins": []})


def _save(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def _wallet(agent_id: str) -> str:
    from gaming.src.stack.agentic.registry import get_registry

    a = get_registry().get_agent(agent_id)
    return str((a or {}).get("wallet_address") or "")


def _pot_wallet(season_no: int) -> str:
    return f"afm_season_{season_no}_pot"


def _open_at(s: dict[str, Any], matchday: int) -> datetime:
    start = _parse(s.get("started_at")) or _now()
    return start + timedelta(hours=int(s.get("cadence_hours", CADENCE_HOURS)) * (matchday - 1))


def _deadline(s: dict[str, Any], matchday: int) -> datetime:
    return _open_at(s, matchday) + timedelta(hours=int(s.get("lock_hours", LOCK_HOURS)))


def _club_wage(club: dict[str, Any]) -> Decimal:
    total = Decimal("0")
    for pid in (club.get("starters") or []) + (club.get("bench") or []):
        p = club.get("_players", {}).get(pid)
        if p is None:
            continue
        total += _d(p.get("wage_per_matchday_usdc") or "0")
    return total


def _debit_budget(wallet: str, amount: Decimal, *, reason: str, ref: str) -> tuple[Decimal, Decimal]:
    """Debit up to `amount`, never below zero. Returns (paid, short)."""
    if amount <= 0:
        return (Decimal("0"), Decimal("0"))
    bal = L.balance(wallet)
    paid = min(bal, amount)
    if paid > 0:
        L.debit(wallet, paid, reason=reason, ref=ref)
    return (paid, amount - paid)


def _ids(x: Any) -> list[str]:
    """Normalise a player list to ids — get_club returns dicts, raw state ids."""
    out: list[str] = []
    for p in x or []:
        out.append(p["player_id"] if isinstance(p, dict) else p)
    return out


def _xi_for_club(club: dict[str, Any]) -> tuple[list[str], bool]:
    """(xi ids, defaulted) — legal XI or roster fallback if the stored one broke."""
    xi = _ids(club.get("starters"))
    if len(xi) == 11:
        return xi, False
    roster = _ids(club.get("squad") or club.get("roster"))
    return roster[:11], True


def _suspended_players(s: dict[str, Any], agent_id: str) -> set[str]:
    """Players banned from the next fixture: anyone sent off (straight red or
    second yellow → red) in the club's most recent played matchday.
    """
    if not s.get("matchdays"):
        return set()
    cur = int(s.get("current_matchday") or 1)
    for md in sorted((int(k) for k in s["matchdays"]), reverse=True):
        if md >= cur:
            continue
        for r in s["matchdays"][str(md)].get("results") or []:
            if r.get("home_agent_id") == agent_id:
                side = "home"
            elif r.get("away_agent_id") == agent_id:
                side = "away"
            else:
                continue
            banned = {
                ev["player_id"]
                for ev in r.get("feed") or []
                if ev.get("type") == "red"
                and ev.get("side") == side
                and ev.get("player_id")
            }
            return banned  # only the most recent fixture's reds carry a ban
    return set()


def _xi_without_suspended(
    xi: list[str],
    banned: set[str],
    bench: list[str],
    squad: list[str],
    players: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Drop banned players from the XI (and bench), then refill to 11 from the
    bench first and the rest of the squad — a spare GK is prioritised when the
    banned player was the keeper.

    Returns (xi, bench) — both free of suspended players when the squad allows.
    """
    xi = [p for p in xi if p not in banned]
    bench = [p for p in bench if p not in banned]
    need = 11 - len(xi)
    if need <= 0:
        return xi[:11], bench
    has_gk = any((players.get(p) or {}).get("slot") == "GK" for p in xi)
    pool: list[str] = []
    for pid in bench + squad:
        if pid in xi or pid in banned or pid in pool:
            continue
        pool.append(pid)
    # one keeper is enough: fill outfielders unless the ban took the keeper
    if has_gk:
        pool = [pid for pid in pool if (players.get(pid) or {}).get("slot") != "GK"]
    else:
        pool.sort(key=lambda pid: 0 if (players.get(pid) or {}).get("slot") == "GK" else 1)
    return xi + pool[:need], bench


def _row_dict(row: Row) -> dict[str, Any]:
    return {
        "agent_id": row.agent_id,
        "played": row.played,
        "wins": row.wins,
        "draws": row.draws,
        "losses": row.losses,
        "goals_for": row.goals_for,
        "goals_against": row.goals_against,
        "points": row.points,
    }


def _standings_from(s: dict[str, Any]) -> dict[str, Row]:
    return {aid: Row(**r) for aid, r in s["standings"].items()}


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "match_id": result.get("match_id"),
        "home_agent_id": result.get("home_agent_id"),
        "away_agent_id": result.get("away_agent_id"),
        "home_goals": result.get("home_goals"),
        "away_goals": result.get("away_goals"),
        "outcome": result.get("outcome"),
        "score": result.get("score"),
    }
    stats = result.get("stats") or {}
    if stats:
        keys = (
            "possession_home", "possession_away",
            "shots_home", "shots_away",
            "shots_on_target_home", "shots_on_target_away",
            "corners_home", "corners_away",
            "fouls_home", "fouls_away",
            "offsides_home", "offsides_away",
            "yellow_cards_home", "yellow_cards_away",
            "red_cards_home", "red_cards_away",
        )
        out["match_stats"] = {k: stats.get(k) for k in keys if k in stats}
    return out


def _club_display(agent_id: str) -> str:
    from gaming.src.stack.agentic.registry import get_registry

    a = get_registry().get_agent(agent_id)
    return str((a or {}).get("name") or agent_id)


def _snapshot(s: dict[str, Any]) -> dict[str, Any]:
    from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

    names = {c["agent_id"]: c.get("club_name") or _club_display(c["agent_id"]) for c in list_clubs()}
    rows = ranked(_standings_from(s))
    standings = []
    for i, r in enumerate(rows, start=1):
        standings.append(
            {
                **{k: r.__dict__[k] for k in ("agent_id", "played", "wins", "draws", "losses", "goals_for", "goals_against", "points")},
                "goal_diff": r.goal_diff,
                "club_name": names.get(r.agent_id, r.agent_id),
                "rank": i,
            }
        )
    sched = schedule_season(s["division"])
    md = int(s["current_matchday"])
    total = int(s["matchdays_total"])
    upcoming = []
    for i in range(md, min(md + 4, total + 1)):
        info = s.get("matchdays", {}).get(str(i))
        for fx in sched[i - 1]:
            upcoming.append(
                {
                    "matchday": i,
                    "home_agent_id": fx.home_agent_id,
                    "home_club": names.get(fx.home_agent_id, fx.home_agent_id),
                    "away_agent_id": fx.away_agent_id,
                    "away_club": names.get(fx.away_agent_id, fx.away_agent_id),
                    "status": (info or {}).get("status", "scheduled"),
                    "open_at": (info or {}).get("open_at") or _iso(_open_at(s, i)),
                    "deadline_at": (info or {}).get("deadline_at") or _iso(_deadline(s, i)),
                }
            )
    recent = []
    for i in range(min(md - 1, total), 0, -1):
        info = s.get("matchdays", {}).get(str(i)) or {}
        for r in info.get("results", []):
            recent.append({"matchday": i, **_summary(r)})
            if len(recent) >= 12:
                break
        if len(recent) >= 12:
            break

    # news-feed skeleton for the current fixture window: pre-match quotes
    # first, then any post-match quotes already stored. This is intentionally
    # lightweight — the full press-conference is available via
    # `transcript_for_fixture` / `matchday_news_items`.
    news: list[dict[str, Any]] = []
    for m in range(md, max(0, md - 2), -1):
        news.extend(matchday_news_items(m))
        if len(news) >= 12:
            break
    return {
        "season_no": s["season_no"],
        "status": s["status"],
        "division": [{"agent_id": a, "name": names.get(a, _club_display(a))} for a in s["division"]],
        "matchdays_total": total,
        "current_matchday": md,
        "started_at": s["started_at"],
        "champion": s.get("champion"),
        "finished_at": s.get("finished_at"),
        "entries": s.get("entries"),
        "entry_usdc": s.get("entry_usdc"),
        "stake_usdc": s.get("stake_usdc"),
        "pot_usdc": str(L.balance(s.get("pot_wallet") or _pot_wallet(int(s["season_no"])))),
        "wage_debt": s.get("wage_debt"),
        "stake_debt": s.get("stake_debt"),
        "standings": standings,
        "upcoming": upcoming,
        "recent": recent,
        "news": news,
        "created_at": s.get("created_at"),
        "updated_at": s.get("updated_at"),
    }


def _snapshot_transcript(s: dict[str, Any]) -> list[dict[str, Any]]:
    """Latest-matchday press-conference items for the spectator snapshot.

    The season snapshot is sent to the frontend dashboard; this adds the most
    recently resolved (or currently open) matchday's manager quotes so the
    dashboard can render the news feed without a second call.
    """
    md = int(s.get("current_matchday") or 0)
    items: list[dict[str, Any]] = []
    for m in range(md, 0, -1):
        batch = matchday_news_items(m)
        if batch:
            items.extend(batch)
            if len(items) >= 24:
                break
    return items


def news_feed(matchday: int) -> list[dict[str, Any]]:
    """Public read-only news feed for one matchday.

    Returns the press-conference items the House recorded for the matchday —
    pre-match quotes first, then post-match quotes — so the spectator
    dashboard can render the manager chatter without exposing any hidden
    engine state.
    """
    return matchday_news_items(matchday)


# ---------------------------------------------------------------- season ops

def get_season() -> Optional[dict[str, Any]]:
    s = _state().get("season")
    return _snapshot(s) if s else None


def join_season(agent_id: str) -> dict[str, Any]:
    """Queue a club for the next season (joining an open season is not allowed)."""
    with _lock:
        st = _state()
        cur = st.get("season")
        if cur and cur.get("status") == "open":
            raise ValueError("season already open — the join is queued for the next one")
        pending = list(st.get("pending_joins") or [])
        if agent_id not in pending:
            pending.append(agent_id)
        st["pending_joins"] = pending
        _save(st)
    return {"queued": True, "agent_id": agent_id, "pending_joins": pending}


def open_season(
    agent_ids: Optional[list[str]] = None,
    *,
    start_at: Optional[datetime] = None,
    season_no: Optional[int] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Open a season: collect USDC entries, build the schedule, zero standings."""
    with _lock:
        st = _state()
        cur = st.get("season")
        if cur and cur.get("status") == "open" and not force:
            raise ValueError("a season is already open — tick it or wait for it to finish")

        from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

        clubs = {c["agent_id"]: c for c in list_clubs()}
        if agent_ids is None:
            # queued joiners enter alongside any existing club
            agent_ids = sorted(set(st.get("pending_joins") or []) | set(clubs))
        ids = [a for a in sorted(set(agent_ids)) if a in clubs]
        if len(ids) < 2:
            raise ValueError("need at least two clubs with AFM rosters to open a season")

        no = season_no or ((int(cur["season_no"]) + 1) if cur else 1)
        pot = _pot_wallet(no)
        entries: dict[str, Any] = {}
        entered: list[str] = []
        for aid in ids:
            w = _wallet(aid)
            if not w:
                continue
            L.ensure_funded(w, DEMO_FAUCET_FLOOR)  # demo ledger faucet so the season can run
            try:
                L.debit(w, SEASON_ENTRY_USDC, reason="afm_season_entry", ref=f"s{no}")
                L.credit(pot, SEASON_ENTRY_USDC, reason="afm_season_pot", ref=f"s{no}")
                entries[aid] = {"paid": True, "entry_usdc": str(SEASON_ENTRY_USDC)}
                entered.append(aid)
            except ValueError:
                entries[aid] = {"paid": False, "entry_usdc": str(SEASON_ENTRY_USDC)}
        if len(entered) < 2:
            raise ValueError("fewer than two clubs could pay the season entry")

        ids = entered
        start = start_at or _now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        season: dict[str, Any] = {
            "season_no": no,
            "status": "open",
            "division": ids,
            "matchdays_total": len(schedule_season(ids)),
            "started_at": _iso(start),
            "current_matchday": 1,
            "cadence_hours": CADENCE_HOURS,
            "lock_hours": LOCK_HOURS,
            "entries": entries,
            "matchdays": {},
            "standings": {aid: _row_dict(r) for aid, r in new_standings(ids).items()},
            "pot_wallet": pot,
            "entry_usdc": str(SEASON_ENTRY_USDC),
            "stake_usdc": str(MATCH_STAKE_USDC),
            "wage_debt": {aid: "0" for aid in ids},
            "stake_debt": {aid: "0" for aid in ids},
            "champion": None,
            "finished_at": None,
            "created_at": _iso(_now()),
            "updated_at": _iso(_now()),
        }
        st["season"] = season
        st["pending_joins"] = []
        _save(st)
        return _snapshot(season)


def tick(now: Optional[datetime] = None) -> dict[str, Any]:
    """Advance the season clock: open due matchdays, resolve past deadlines."""
    now = now or _now()
    with _lock:
        st = _state()
        s = st.get("season")
        if not s or s.get("status") != "open":
            return {"action": "idle", "reason": "no open season", "season_status": s.get("status") if s else None}
        no = int(s["season_no"])
        total = int(s["matchdays_total"])
        md = int(s["current_matchday"])
        opened: list[int] = []
        resolved: list[int] = []
        while md <= total:
            if now < _open_at(s, md):
                break
            key = str(md)
            info = s.get("matchdays", {}).get(key)
            if info is None:
                s["matchdays"][key] = {
                    "status": "open",
                    "open_at": _iso(_open_at(s, md)),
                    "deadline_at": _iso(_deadline(s, md)),
                    "resolved_at": None,
                    "auto": [],
                    "results": [],
                }
                info = s["matchdays"][key]
                opened.append(md)
            # managers decide for this matchday once, at open — a human edit
            # after open (before the deadline) still wins for that matchday
            if not info.get("decided"):
                _agents_decide(s, md)
                info["decided"] = True
                info["decided_at"] = _iso(_now())
            if now < _deadline(s, md):
                break
            _resolve_matchday(s, md)
            s["current_matchday"] = md + 1
            resolved.append(md)
            md += 1
        if s["current_matchday"] > total:
            _finalize_season(s)
        s["updated_at"] = _iso(_now())
        _save(st)
        return {
            "action": "tick",
            "season_no": no,
            "opened": opened,
            "resolved": resolved,
            "current_matchday": int(s["current_matchday"]),
            "season_status": s["status"],
            "champion": s.get("champion"),
        }


def matchday_news_items(matchday: int) -> list[dict[str, Any]]:
    """Flatten a matchday's press-conference into quotable news-feed items.

    Each item is what a spectator dashboard can render directly: who said it,
    when (pre or post match), the question the House asked and the answer the
    manager gave — or "no reply" when the agent did not answer.
    """
    s = _state().get("season")
    if not s:
        return []
    info = s.get("matchdays", {}).get(str(matchday)) or {}
    items: list[dict[str, Any]] = []
    for pc in (info.get("press_conference") or []):
        phase = pc.get("phase") or "pre"
        agent_id = pc.get("agent_id")
        questions = pc.get("questions") or []
        answers = pc.get("answers") or {}
        source = pc.get("source") or "auto"
        error = pc.get("error")
        for q in questions:
            ans = answers.get(q, None)
            items.append(
                {
                    "matchday": matchday,
                    "agent_id": agent_id,
                    "club_name": _club_display(agent_id),
                    "phase": phase,
                    "question": q,
                    "answer": ans,
                    "source": source,
                    "error": error,
                }
            )
    return items


def press_conference_for(
    matchday: int,
    agent_id: str,
) -> list[dict[str, Any]]:
    """One agent's full press-conference transcript for a matchday.

    Returns the pre-match and post-match question/answer sets in chronological
    order so a renderer can show the manager's before/after quotes as a single
    thread.
    """
    s = _state().get("season")
    if not s:
        raise ValueError("no season running")
    info = s.get("matchdays", {}).get(str(matchday)) or {}
    out: list[dict[str, Any]] = []
    for pc in (info.get("press_conference") or []):
        if pc.get("agent_id") != agent_id:
            continue
        out.append(
            {
                "matchday": matchday,
                "agent_id": agent_id,
                "phase": pc.get("phase") or "pre",
                "questions": pc.get("questions") or [],
                "answers": pc.get("answers") or {},
                "source": pc.get("source") or "auto",
                "error": pc.get("error"),
            }
        )
    return out


def _is_home(s: dict[str, Any], matchday: int, agent_id: str) -> bool:
    fx = _fixture_for(s, matchday, agent_id)
    return bool(fx and fx.home_agent_id == agent_id)


def _opponent_for(s: dict[str, Any], matchday: int, agent_id: str) -> str:
    fx = _fixture_for(s, matchday, agent_id)
    if not fx:
        return agent_id
    return fx.away_agent_id if fx.home_agent_id == agent_id else fx.home_agent_id


def _fixture_for(s: dict[str, Any], matchday: int, agent_id: str):
    sched = _schedule_for(s)
    try:
        return next(f for f in sched[matchday - 1] if agent_id in (f.home_agent_id, f.away_agent_id))
    except StopIteration:
        return None


def clear_matchday_transcript(matchday: int) -> None:
    """Reset a matchday's press-conference transcript (dev/replay only).

    Used by tests and by the replay-rerun path so a re-simulated matchday
    starts with a clean transcript.
    """
    with _lock:
        st = _state()
        s = st.get("season")
        if not s:
            return
        info = s.get("matchdays", {}).get(str(matchday))
        if info:
            info["press_conference"] = []
            _save(st)


def replay_press_conference(matchday: int, home: str, away: str) -> dict[str, Any]:
    """A press-conference replay for one fixture — deterministic read path.

    When a spectator or the broadcast wants the manager quotes for a fixture
    without re-running the match, this is the read endpoint.
    """
    return {
        "matchday": matchday,
        "home_agent_id": home,
        "away_agent_id": away,
        "home_club": _club_display(home),
        "away_club": _club_display(away),
        "transcript": press_conference_for(matchday, home) + press_conference_for(matchday, away),
    }


# ---------------------------------------------------------------- internals

def _agents_decide(s: dict[str, Any], matchday: int) -> None:
    """Each manager sets its lineup + tactics for this matchday (once, at open).

    The House asks every manager for its plan (webhook ask → JSON reply,
    same shape as the chess move loop); a manager with no reachable webhook
    or an invalid reply falls back to the deterministic `decide_matchday`.
    A manager who fails to decide (no legal squad etc.) keeps its saved
    lineup — the auto-fallback in `_resolve_matchday` still guarantees a
    legal XI, so a club can never be defaulted for a bad decision.
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        set_ht_plans,
        set_lineup,
    )
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        ask_matchday_plan,
        build_press_conference_ask,
        request_press_conference_answer,
    )
    from gaming.src.stack.agentic.registry import get_registry

    decisions: dict[str, Any] = {}
    press_conference: list[dict[str, Any]] = []
    info = s["matchdays"][str(matchday)]
    reg = get_registry()
    for aid in s["division"]:
        try:
            agent = reg.get_agent(aid) or {}
            out = ask_matchday_plan(agent, s, matchday)
            plan = out.get("plan")
            if not plan:
                continue  # bye — nothing to decide
            set_lineup(
                aid,
                formation=plan["formation"],
                starters=plan["starters"],
                bench=plan["bench"],
                tactical_tags=plan["tags"],
            )
            # v1.4: persist half-time contingency plans so the lock can hand
            # them to the engine (webhook managers may supply their own)
            if plan.get("plans"):
                set_ht_plans(aid, plan["plans"])
            decisions[aid] = {
                "formation": plan["formation"],
                "tags": list(plan["tags"]),
                "starters": list(plan["starters"]),
                "xi": list(plan["starters"]),
                "bench": list(plan["bench"]),
                "source": out.get("source") or "auto",
                "instructions": out.get("instructions") or plan.get("instructions"),
                "asked": out.get("asked", False),
                "note": out.get("error"),
                # v1.4: the pre-committed HT plans ride along so the pre-match
                # board can show how the manager intends to react at half-time
                "plans": dict(plan.get("plans") or {}),
            }
        except Exception as exc:
            decisions[aid] = {"error": str(exc)}

    # pre-match press-conference: the House asks each manager for its plan
    # rationale before kickoff. The answers (or "no reply") are stored so the
    # spectator feed can quote the managers before the match.
    for aid in s["division"]:
        try:
            agent = reg.get_agent(aid) or {}
            opp = _opponent_for(s, matchday, aid)
            my_side = "home" if _is_home(s, matchday, aid) else "away"
            ask = build_press_conference_ask(aid, opp, my_side, "pre")
            answers = request_press_conference_answer(agent, ask)
            pc: dict[str, Any] = {
                "matchday": matchday,
                "agent_id": aid,
                "phase": "pre",
                "questions": ask["questions"],
                "answers": answers or {},
                "source": (agent.get("webhook") or "") and "webhook" or "auto",
            }
            # normalize missing answers to "no reply" so the feed can render them
            for q in ask["questions"]:
                if q not in pc["answers"]:
                    pc["answers"][q] = None
            press_conference.append(pc)
        except Exception as exc:
            press_conference.append(
                {
                    "matchday": matchday,
                    "agent_id": aid,
                    "phase": "pre",
                    "questions": PRESS_CONFERENCE_QUESTIONS["pre"],
                    "answers": {q: None for q in PRESS_CONFERENCE_QUESTIONS["pre"]},
                    "error": str(exc),
                    "source": "auto",
                }
            )
    info["press_conference"] = press_conference
    info["decisions"] = decisions


def _schedule_for(s: dict[str, Any]) -> list:
    from gaming.src.stack.agentic.games.football_managers.league import schedule_season

    return schedule_season(s["division"])


def get_matchday_transcript(
    matchday: int,
    home: str,
    away: str,
) -> dict[str, Any]:
    """Manager action + press-conference transcript for one fixture.

    This is the spectator-facing record of everything the managers *did* and
    *said* about a matchday, including:

      * the action log: who set the matchday (webhook vs auto), their
        formation, starters, bench, tactical tags, instructions and any note
        (e.g. a webhook rejection reason)
      * the press-conference transcript: pre-match + post-match questions the
        House asked, and the answers the agents gave (or "no reply")

    It is intentionally read-only and derived from the season state — the
    engine already ran the match. This is the raw material for the news feed
    and the broadcast "manager said..." pieces.
    """
    s = _state().get("season")
    if not s:
        raise ValueError("no season running")
    info = s.get("matchdays", {}).get(str(matchday)) or {}
    return {
        "matchday": matchday,
        "home_agent_id": home,
        "away_agent_id": away,
        "home_club": _club_display(home),
        "away_club": _club_display(away),
        "decisions": info.get("decisions") or {},
        "press_conference": info.get("press_conference") or [],
        "status": info.get("status") or "scheduled",
        "open_at": info.get("open_at") or _iso(_open_at(s, matchday)),
        "deadline_at": info.get("deadline_at") or _iso(_deadline(s, matchday)),
        "resolved_at": info.get("resolved_at"),
    }


def _resolve_matchday(s: dict[str, Any], matchday: int) -> None:
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_press_conference_ask,
        request_press_conference_answer,
    )
    from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        current_condition,
        decay_injuries,
        get_ht_plans,
        record_match_fatigue,
        record_match_injuries,
    )
    # v1.4: injuries from the previous matchday clear at this lock — a player
    # hurt on MD N sat out MD N+1 and is available again from MD N+2
    decay_injuries()

    no = int(s["season_no"])
    key = str(matchday)
    info = s["matchdays"][key]
    if info.get("status") == "played":
        return  # already resolved (keeper + API + humans can all tick — never double-count)
    info["status"] = "played"

    # lock XIs + tactics (what the agents set) with legal-XI fallback
    lineups: dict[str, dict[str, Any]] = {}
    auto: list[str] = []
    players: dict[str, dict[str, Any]] = {}
    from gaming.src.stack.agentic.games.football_managers.catalog import get_player

    for aid in s["division"]:
        club = get_club(aid) or {}
        starters = _ids(club.get("starters"))
        bench = _ids(club.get("bench"))
        squad = _ids(club.get("squad") or club.get("roster"))
        players.update({pid: get_player(pid) for pid in starters + bench + squad})
        club = {**club, "starters": starters, "bench": bench, "squad": squad, "roster": squad, "_players": players}
        xi, defaulted = _xi_for_club(club)
        # discipline carries across matchdays: anyone sent off in the club's
        # last fixture sits out this one (lineup lock enforces the ban)
        banned = _suspended_players(s, aid)
        if banned:
            xi, bench = _xi_without_suspended(xi, banned, bench, squad, players)
            defaulted = True
            auto.append(aid)
        lineups[aid] = {
            "xi": xi,
            "bench": list(bench),
            "banned": sorted(banned),
            "formation": club.get("formation") or "4-3-3",
            "tags": list(club.get("tactical_tags") or ["balanced"]),
            "plans": get_ht_plans(aid),
            "wage": _club_wage(club),
        }
    info["auto"] = sorted(set(auto))

    # wages come due at lock
    for aid in s["division"]:
        w = _wallet(aid)
        if not w:
            continue
        _paid, short = _debit_budget(w, lineups[aid]["wage"], reason=f"afm_wages_s{no}", ref=f"s{no}_md{matchday}")
        s["wage_debt"][aid] = str(_d(s["wage_debt"][aid]) + short)

    sched = schedule_season(s["division"])
    fixtures = sched[matchday - 1]
    table = _standings_from(s)
    results: list[dict[str, Any]] = []

    for fx in fixtures:
        h, a = fx.home_agent_id, fx.away_agent_id
        mid = f"afm_season_{no}_md{matchday}_{h}_{a}"
        res = simulate_match(
            mid,
            home_agent_id=h,
            away_agent_id=a,
            home_xi=lineups[h]["xi"],
            away_xi=lineups[a]["xi"],
            home_bench=lineups[h].get("bench") or [],
            away_bench=lineups[a].get("bench") or [],
            home_tactics={"formation": lineups[h]["formation"], "tags": lineups[h]["tags"]},
            away_tactics={"formation": lineups[a]["formation"], "tags": lineups[a]["tags"]},
            home_plans=lineups[h].get("plans") or None,
            away_plans=lineups[a].get("plans") or None,
            home_fatigue=current_condition(h),
            away_fatigue=current_condition(a),
        ).to_dict()
        # v1.4: an injury that forced a sub now costs the player the next
        # matchday — derived from the feed so the engine stays a pure function
        def _injured(feed: list[dict[str, Any]]) -> list[str]:
            seen: list[str] = []
            for ev in feed or []:
                if ev.get("type") == "substitution" and ev.get("kind") == "injury" and ev.get("off"):
                    if ev["off"] not in seen:
                        seen.append(str(ev["off"]))
            return seen

        injured_pids = _injured(res.get("feed") or [])
        if injured_pids:
            record_match_injuries(injured_pids)
        # tiredness carries: store the condition each squad leaves the match
        # with so the next matchday's lock (and the squad screen) sees it
        cond_home = (res.get("fatigue") or {}).get("home") or {}
        cond_away = (res.get("fatigue") or {}).get("away") or {}
        if cond_home:
            record_match_fatigue(h, cond_home)
        if cond_away:
            record_match_fatigue(a, cond_away)
        res["home_club"] = _club_display(h)
        res["away_club"] = _club_display(a)
        res["lineups"] = {
            h: {"xi": lineups[h]["xi"], "bench": lineups[h].get("bench") or [],
                "banned": list(lineups[h].get("banned") or []),
                "formation": lineups[h]["formation"], "tags": lineups[h]["tags"],
                "plans": lineups[h].get("plans") or {}},
            a: {"xi": lineups[a]["xi"], "bench": lineups[a].get("bench") or [],
                "banned": list(lineups[a].get("banned") or []),
                "formation": lineups[a]["formation"], "tags": lineups[a]["tags"],
                "plans": lineups[a].get("plans") or {}},
        }
        table = apply_result(table, fx, res["home_goals"], res["away_goals"])
        results.append(res)
        _settle_match(s, matchday, h, a, res["outcome"])
    s["standings"] = {aid: _row_dict(r) for aid, r in table.items()}
    info["results"] = results
    info["resolved_at"] = _iso(_now())

    # post-match press-conference: the House asks each manager for a reaction
    # after the whistle. Answers are stored alongside the pre-match ones so the
    # spectator feed can show the before/after quotes for the fixture.
    for aid in s["division"]:
        try:
            agent = _reg().get_agent(aid) or {}
            opp = _opponent_for(s, matchday, aid)
            my_side = "home" if _is_home(s, matchday, aid) else "away"
            result = next(
                (r for r in results if r.get("home_agent_id") == aid or r.get("away_agent_id") == aid),
                None,
            )
            score_before = None
            if result:
                score_before = {
                    "home": int(result.get("home_goals") or 0),
                    "away": int(result.get("away_goals") or 0),
                }
            ask = build_press_conference_ask(aid, opp, my_side, "post", score_before=score_before)
            answers = request_press_conference_answer(agent, ask)
            pc: dict[str, Any] = {
                "matchday": matchday,
                "agent_id": aid,
                "phase": "post",
                "questions": ask["questions"],
                "answers": answers or {},
                "source": "webhook" if agent.get("webhook") else "auto",
            }
            for q in ask["questions"]:
                if q not in pc["answers"]:
                    pc["answers"][q] = None
            info["press_conference"].append(pc)
        except Exception as exc:
            info["press_conference"].append(
                {
                    "matchday": matchday,
                    "agent_id": aid,
                    "phase": "post",
                    "questions": PRESS_CONFERENCE_QUESTIONS["post"],
                    "answers": {q: None for q in PRESS_CONFERENCE_QUESTIONS["post"]},
                    "error": str(exc),
                    "source": "auto",
                }
            )


def _settle_match(s: dict[str, Any], matchday: int, home: str, away: str, outcome: str) -> None:
    no = int(s["season_no"])
    mid = f"afm_season_{no}_md{matchday}_{home}_{away}"
    stake = MATCH_STAKE_USDC
    hw, aw = _wallet(home), _wallet(away)
    if not hw or not aw:
        return
    L.open_escrow(mid, agent_a_wallet=hw, agent_b_wallet=aw, stake_usdc=stake)
    locked: list[str] = []
    for w, side in ((hw, home), (aw, away)):
        bal = L.balance(w)
        if bal >= stake:
            try:
                L.lock(mid, w)
                locked.append(w)
            except ValueError:
                s["stake_debt"][side] = str(_d(s["stake_debt"][side]) + stake)
        else:
            s["stake_debt"][side] = str(_d(s["stake_debt"][side]) + (stake - bal))
    esc = L.get_escrow(mid)
    if esc and esc.get("status") == "locked":
        if outcome == "draw":
            L.settle(mid, hw, result="draw")
        else:
            winner = hw if outcome == "home_win" else aw
            L.settle(mid, winner, result="win")
    else:
        # partially locked: refund what actually went in; the short side owes
        for w in locked:
            L.credit(w, stake, reason="afm_stake_refund", ref=mid)


def _finalize_season(s: dict[str, Any]) -> None:
    if s.get("status") != "open":
        return  # already finalized (defensive — tick guards, but never pay twice)
    no = int(s["season_no"])
    order = season_outcome(_standings_from(s))
    if not order:
        s["status"] = "finished"
        s["finished_at"] = _iso(_now())
        return
    s["champion"] = order[0]
    pot = L.balance(s["pot_wallet"])
    shares = SEASON_POT_SHARES_2 if len(order) <= 2 else SEASON_POT_SHARES_N
    paid = Decimal("0")
    for i, aid in enumerate(order[: len(shares)]):
        w = _wallet(aid)
        if not w:
            continue
        amt = (pot * shares[i]).quantize(Decimal("0.000001"))
        if amt > 0:
            _debit_budget(s["pot_wallet"], amt, reason="afm_season_pot_payout", ref=f"s{no}")
            L.credit(w, amt, reason="afm_season_pot_payout", ref=f"s{no}")
            paid += amt
    # leftover dust goes to the champion
    dust = pot - paid
    cw = _wallet(order[0])
    if cw and dust > 0:
        _debit_budget(s["pot_wallet"], dust, reason="afm_season_pot_payout", ref=f"s{no}")
        L.credit(cw, dust, reason="afm_season_pot_dust", ref=f"s{no}")
    s["status"] = "finished"
    s["finished_at"] = _iso(_now())


def reset_season() -> dict[str, Any]:
    with _lock:
        st = _state()
        st["season"] = None
        _save(st)
    return {"reset": True}


# ---------------------------------------------------------------- replay

def get_replay(matchday: int, home: str, away: str) -> dict[str, Any]:
    """A recorded fixture, replayable end-to-end (feed + locked lineups).

    New matchdays store the full engine result (feed included). Older
    matchdays are reconstructed deterministically — the engine is seeded by
    match_id, so re-running with the locked lineups reproduces the exact
    match, feed and all.

    The replay also carries the matchday's press-conference transcript so a
    spectator or broadcast can render the managers' quotes beside the replay.
    """
    s = _state().get("season")
    if not s:
        raise ValueError("no season running")
    no = int(s["season_no"])
    info = s.get("matchdays", {}).get(str(matchday)) or {}
    mid = f"afm_season_{no}_md{matchday}_{home}_{away}"
    result = next(
        (r for r in (info.get("results") or []) if r.get("match_id") == mid and r.get("feed")),
        None,
    )
    if result is None:
        result = _reconstruct_replay(s, matchday, home, away, mid)
    if result is None:
        raise ValueError(f"no replay for MD {matchday}: {home} vs {away}")

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
        "match_id": mid,
        "matchday": matchday,
        "result": result,
        "home": side(home),
        "away": side(away),
        "decisions": info.get("decisions") or {},
        "press_conference": info.get("press_conference") or [],
        "transcript": press_conference_for(matchday, home) + press_conference_for(matchday, away),
    }


def transcript_for_fixture(matchday: int, home: str, away: str) -> dict[str, Any]:
    """The combined manager action + press-conference record for one fixture.

    This is the spectator-facing wrapper around `get_matchday_transcript` +
    `replay_press_conference`: action log, pre-match quotes, post-match quotes,
    and the match status the human reads before/after kickoff.
    """
    return {
        **get_matchday_transcript(matchday, home, away),
        **replay_press_conference(matchday, home, away),
    }


def prematch_view(matchday: int, home: str, away: str) -> dict[str, Any]:
    """The pre-match board for one upcoming or open fixture (spectator-safe).

    Everything a human reads before kickoff, and nothing the managers keep
    hidden: both clubs' locked formation, tactical tags and the named XI,
    the pre-committed half-time contingency plans (trailing/level/leading —
    formations and tags only, never numbers), the pre-match press-conference
    quotes, ban/injury news, and the window timestamps.

    Works from the day the matchday opens (managers decide at open, so the
    lineup exists from that moment) and stays available after resolution —
    a viewer landing on an old link reads the shape the match was actually
    played in.

    For an un-opened matchday the window is projected from the season
    schedule and both sides come back empty ("awaiting lineups"), so the
    fixture can be listed before its managers have decided.
    """
    s = _state().get("season")
    if not s:
        raise ValueError("no season running")
    sched = _schedule_for(s)
    if not 0 < matchday <= len(sched):
        raise ValueError(f"matchday {matchday} out of range")
    fx = next(
        (
            f
            for f in sched[matchday - 1]
            if {f.home_agent_id, f.away_agent_id} == {home, away}
        ),
        None,
    )
    if fx is None:
        raise ValueError(
            f"no fixture MD {matchday}: {home} vs {away}"
        )

    info = s.get("matchdays", {}).get(str(matchday)) or {}
    decisions = info.get("decisions") or {}
    from gaming.src.stack.agentic.games.football_managers.club_store import injuries_map

    injuries = injuries_map()

    def side(aid: str, opp_id: str) -> dict[str, Any]:
        from gaming.src.stack.agentic.games.football_managers.catalog import get_player
        from gaming.src.stack.agentic.games.football_managers.club_store import get_club

        d = decisions.get(aid) or {}
        xi_ids = list(d.get("xi") or d.get("starters") or [])
        formation = d.get("formation") or ""
        tags = list(d.get("tags") or [])
        if not xi_ids and info.get("status") == "played":
            # old replayed matchday with no stored decisions: read the shape
            # the match was actually played in from the club's held lineup
            club = get_club(aid) or {}
            xi_ids = [str(p.get("player_id") or "") for p in club.get("starters") or []]
            formation = formation or club.get("formation") or ""
            tags = tags or list(club.get("tactical_tags") or [])
        xi = []
        for pid in xi_ids:
            p = get_player(pid) or {}
            xi.append(
                {
                    "player_id": pid,
                    "name": p.get("name") or pid,
                    "slot": str(p.get("slot") or "").upper(),
                }
            )
        # news the broadcast can show beside the team sheet: who is banned
        # (red last matchday) and who is injured (sits this one out)
        banned = sorted(_suspended_players(s, aid))
        news = []
        for pid in banned:
            p = get_player(pid) or {}
            news.append(
                {
                    "type": "suspension",
                    "player_id": pid,
                    "name": p.get("name") or pid,
                    "detail": "Suspended — sent off last matchday",
                }
            )
        for pid, left in sorted(injuries.items()):
            if pid in xi_ids:
                continue  # on the sheet — not this player's news
            p = get_player(pid) or {}
            if not p:
                continue
            news.append(
                {
                    "type": "injury",
                    "player_id": pid,
                    "name": p.get("name") or pid,
                    "detail": f"Injured — out for {left} more matchday",
                }
            )
        return {
            "agent_id": aid,
            "club_name": _club_display(aid),
            "formation": formation,
            "tags": tags,
            "instructions": d.get("instructions"),
            "source": d.get("source"),
            "plans": dict(d.get("plans") or {}),
            "xi": xi,
            "news": news,
            "decided": bool(d),
        }

    return {
        "matchday": matchday,
        "season_no": int(s["season_no"]),
        "status": info.get("status") or "scheduled",
        "home": side(fx.home_agent_id, fx.away_agent_id),
        "away": side(fx.away_agent_id, fx.home_agent_id),
        "open_at": info.get("open_at") or _iso(_open_at(s, matchday)),
        "deadline_at": info.get("deadline_at") or _iso(_deadline(s, matchday)),
        "resolved_at": info.get("resolved_at"),
    }


def _reconstruct_replay(
    s: dict[str, Any],
    matchday: int,
    home: str,
    away: str,
    mid: str,
) -> Optional[dict[str, Any]]:
    """Re-run the deterministic engine for a pre-feed-storage matchday."""
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match

    info = s.get("matchdays", {}).get(str(matchday)) or {}
    lineups: dict[str, dict[str, Any]] = {}
    for r in info.get("results") or []:
        if r.get("match_id") == mid and r.get("lineups"):
            lineups = r["lineups"]
            break
    if not lineups:
        # oldest format: nothing stored — fall back to what the club holds.
        # HT plans live in the club store too; without them the replay would
        # skip half-time changes and diverge from the original result.
        from gaming.src.stack.agentic.games.football_managers.club_store import get_ht_plans

        for aid in (home, away):
            club = get_club(aid) or {}
            starters = _ids(club.get("starters"))
            if len(starters) != 11:
                starters = _ids(club.get("squad") or club.get("roster"))[:11]
            lineups[aid] = {
                "xi": starters,
                "bench": _ids(club.get("bench")),
                "formation": club.get("formation") or "4-3-3",
                "tags": list(club.get("tactical_tags") or ["balanced"]),
                "plans": get_ht_plans(aid),
            }
    if home not in lineups or away not in lineups:
        return None
    res = simulate_match(
        mid,
        home_agent_id=home,
        away_agent_id=away,
        home_xi=lineups[home]["xi"],
        away_xi=lineups[away]["xi"],
        home_bench=list(lineups[home].get("bench") or []),
        away_bench=list(lineups[away].get("bench") or []),
        home_tactics={"formation": lineups[home]["formation"], "tags": lineups[home]["tags"]},
        away_tactics={"formation": lineups[away]["formation"], "tags": lineups[away]["tags"]},
        home_plans=lineups[home].get("plans") or None,
        away_plans=lineups[away].get("plans") or None,
    ).to_dict()
    res["home_club"] = _club_display(home)
    res["away_club"] = _club_display(away)
    res["lineups"] = lineups
    return res