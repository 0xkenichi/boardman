"""AFM post-match report — the FM "why we lost" file.

A pure read model over the stored season results (engine v1.3 already folds
`player_stats` — minutes, goals, xG, rating 0–99, errors — per actor in every
result dict). Two projections:

* `match_report(season_no, matchday, home, away)` — one fixture's report for
  **the agent** (FM surface): team xG vs goals, per-player ratings grouped
  best/worst, error attribution, the decision that produced it and the
  match stats. Agent-facing helper `latest_report_for_agent` picks the
  club's most recent fixture and reads only that side's rows.
* `dashboard_match_report(result, agent_id)` — a compact summary embedded in
  the **owner dashboard** result rows (top performer, rating, team xG, the
  one-line "why").

No writes: everything folds data `season.py` already stores.
"""
from __future__ import annotations

from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.season import _club_display

# thresholds for surfacing a performance in the compact dashboard view
_TOP_RATING = 80
_POOR_RATING = 60


def _name_of(pid: str, players: dict[str, dict[str, Any]]) -> str:
    return str((players.get(pid) or {}).get("name") or pid)


def _players_index() -> dict[str, dict[str, Any]]:
    from gaming.src.stack.agentic.games.football_managers.catalog import list_players

    return {p["player_id"]: p for p in list_players()}


def _side_rows(
    player_stats: dict[str, dict[str, Any]],
    xi: list[str],
    bench: list[str],
    players: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-player report rows for one side, best rating first."""
    involved = {pid: (player_stats or {}).get(pid) for pid in list(xi) + list(bench)}
    rows: list[dict[str, Any]] = []
    for pid, rec in involved.items():
        p = players.get(pid) or {}
        row: dict[str, Any] = {
            "player_id": pid,
            "name": str(p.get("name") or pid),
            "position": str(p.get("slot") or p.get("primary_pos") or "").upper(),
            "starter": pid in xi,
        }
        if not rec:
            # unused sub: on the bench, never came on
            row.update({
                "minutes": 0,
                "played": False,
                "rating": None,
                "goals": 0,
                "shots": 0,
                "shots_on_target": 0,
                "xG": 0.0,
                "tackles": 0,
                "interceptions": 0,
                "passes": 0,
                "cards": 0,
                "errors": [],
            })
            rows.append(row)
            continue
        row.update(
            {
                "played": bool(rec.get("minutes")),
                "minutes": int(rec.get("minutes") or 0),
                "goals": int(rec.get("goals") or 0),
                "shots": int(rec.get("shots") or 0),
                "shots_on_target": int(rec.get("shots_on_target") or 0),
                "xG": float(rec.get("xG") or 0.0),
                "rating": int(rec.get("rating") or 0),
                "tackles": int(rec.get("tackles") or 0),
                "interceptions": int(rec.get("interceptions") or 0),
                "passes": int(rec.get("passes") or 0),
                "cards": int(rec.get("cards") or 0),
                "errors": list(rec.get("errors") or []),
            }
        )
        rows.append(row)
    rows.sort(key=lambda r: (not r.get("played"), -(r.get("rating") or 0)))
    return rows


def _team_xg(player_stats: dict[str, dict[str, Any]], ids: list[str]) -> float:
    return round(sum(float((player_stats.get(pid) or {}).get("xG") or 0.0) for pid in ids), 3)


def match_report(
    season_no: int,
    matchday: int,
    home: str,
    away: str,
) -> dict[str, Any]:
    """The full FM post-match report for one recorded fixture.

    Raises ValueError when the fixture has not been played (replays of
    pre-feed-storage matchdays are not reported — nothing to fold).
    """
    from gaming.src.stack.agentic.games.football_managers.season import _state

    s = _state().get("season")
    if not s or int(s.get("season_no") or 0) != int(season_no):
        raise ValueError("no matching season running")
    info = (s.get("matchdays") or {}).get(str(matchday)) or {}
    result = next(
        (r for r in (info.get("results") or []) if r.get("home_agent_id") == home and r.get("away_agent_id") == away),
        None,
    )
    if not result:
        raise ValueError(f"matchday {matchday} has no result for {home} vs {away}")

    players = _players_index()
    ps = result.get("player_stats") or {}
    lineups = result.get("lineups") or {}

    sides: dict[str, dict[str, Any]] = {}
    for side_tag, aid in (("home", home), ("away", away)):
        lu = lineups.get(aid) or {}
        xi = list(lu.get("xi") or [])
        bench = list(lu.get("bench") or [])
        rows = _side_rows(ps, xi, bench, players)
        rated = [r for r in rows if r.get("rating") is not None]
        goals_fold = sum(r.get("goals") or 0 for r in rows)
        sides[side_tag] = {
            "agent_id": aid,
            "club_name": _club_display(aid),
            "formation": lu.get("formation") or "4-3-3",
            "tags": list(lu.get("tags") or []),
            "goals": int(result.get("home_goals") if side_tag == "home" else result.get("away_goals") or 0)
            if side_tag == "home"
            else int(result.get("away_goals") or 0),
            "xG": _team_xg(ps, xi + bench),
            "top": rated[0] if rated else None,
            "worst": rated[-1] if len(rated) > 1 else None,
            "goal_scorers": [r["name"] for r in rows if r.get("goals")],
            "errors": [e for r in rows for e in (r.get("errors") or [])],
            "players": rows,
        }

    return {
        "match_id": result.get("match_id"),
        "season_no": int(season_no),
        "matchday": int(matchday),
        "status": info.get("status") or "played",
        "resolved_at": info.get("resolved_at"),
        "score": result.get("score"),
        "home": sides["home"],
        "away": sides["away"],
        "why": _why_lines(sides["home"], sides["away"]),
    }


def _why_lines(home_side: dict[str, Any], away_side: dict[str, Any]) -> list[str]:
    """One-line "why we won/lost" attributions — the report's headline."""
    lines: list[str] = []
    for side, opp in ((home_side, away_side), (away_side, home_side)):
        club = side.get("club_name") or side.get("agent_id")
        opp_club = opp.get("club_name") or opp.get("agent_id")
        gx = float(side.get("xG") or 0.0)
        og = float(opp.get("xG") or 0.0)
        goals = int(side.get("goals") or 0)
        opp_goals = int(opp.get("goals") or 0)
        if goals > opp_goals:
            if gx >= og + 0.3:
                lines.append(f"{club} created the better chances ({gx:.2f} xG vs {og:.2f}).")
            top = side.get("top") or {}
            if top.get("goals"):
                lines.append(f"{top.get('name')} was the difference — {top['goals']} goal(s), rated {top.get('rating')}.")
        elif goals < opp_goals:
            errs = side.get("errors") or []
            if errs:
                first = errs[0]
                lines.append(f"{club}: {first.get('note') or 'a costly error'} proved expensive.")
            if og >= gx + 0.3:
                lines.append(f"{opp_club} out-created {club} ({og:.2f} xG vs {gx:.2f}).")
    # xG over/under-performance notes already carry the side tags in the text
    return lines[:4]


def latest_report_for_agent(agent_id: str) -> dict[str, Any]:
    """The club's most recent played fixture report, from that side's seat.

    Raises ValueError when the agent has no club or no played fixture yet.
    """
    from gaming.src.stack.agentic.games.football_managers.season import _state

    s = _state().get("season")
    if not s:
        raise ValueError("no season running")
    played: list[tuple[int, dict[str, Any]]] = []
    for md_key, info in (s.get("matchdays") or {}).items():
        for r in info.get("results") or []:
            if agent_id in (r.get("home_agent_id"), r.get("away_agent_id")):
                played.append((int(md_key), r))
    if not played:
        raise ValueError(f"no played fixtures for {agent_id}")
    played.sort(key=lambda t: t[0], reverse=True)
    md, r = played[0]
    home, away = r["home_agent_id"], r["away_agent_id"]
    rep = match_report(int(s["season_no"]), md, home, away)
    rep["my_side"] = "home" if home == agent_id else "away"
    rep["my"] = rep[rep["my_side"]]
    rep["opponent_side"] = "away" if home == agent_id else "home"
    return rep


def dashboard_match_report(result: dict[str, Any], info: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """The compact report embedded in one owner-dashboard result row.

    Pure fold over the stored result — same shape for both sides, keyed by
    the agent reading it (rows already name both clubs).
    """
    ps = result.get("player_stats") or {}
    if not ps:
        return {}
    players = _players_index()
    lineups = result.get("lineups") or {}
    is_home = result.get("home_agent_id") == agent_id
    opp_id = result.get("away_agent_id") if is_home else result.get("home_agent_id")

    def side_summary(aid: str) -> dict[str, Any]:
        lu = lineups.get(aid) or {}
        xi = list(lu.get("xi") or [])
        bench = list(lu.get("bench") or [])
        rows = _side_rows(ps, xi, bench, players)
        rated = [r for r in rows if r.get("rating") is not None]
        return {
            "xG": _team_xg(ps, xi + bench),
            "top": rated[0] if rated else None,
            "worst": rated[-1] if len(rated) > 1 else None,
            "errors": [e for r in rows for e in (r.get("errors") or [])],
            "players": rows,
        }

    mine = side_summary(agent_id)
    theirs = side_summary(opp_id)
    dec = (info.get("decisions") or {}).get(agent_id) or {}

    # the one-line "why": best performer, or the costliest error, or the xG gap
    why: Optional[str] = None
    top = mine.get("top") or {}
    errors = mine.get("errors") or []
    our_xg = float(mine.get("xG") or 0.0)
    their_xg = float(theirs.get("xG") or 0.0)
    if top and int(top.get("rating") or 0) >= _TOP_RATING:
        why = f"{top.get('name')} starred — rated {top.get('rating')}"
    elif errors:
        why = str((errors[0] or {}).get("note") or "costly error")
    elif our_xg and their_xg and abs(our_xg - their_xg) >= 0.25:
        better = "us" if our_xg > their_xg else "them"
        why = f"{better and ('the chances were ' + better + 's')} ({our_xg:.2f} vs {their_xg:.2f} xG)"

    return {
        "my_xg": our_xg,
        "their_xg": their_xg,
        "top": top if top and top.get("played") else None,
        "poor": (mine.get("worst") or {}) if (mine.get("worst") or {}).get("rating", 99) <= _POOR_RATING else None,
        "errors": errors,
        "why": why,
        "formation": dec.get("formation") or lineups.get(agent_id, {}).get("formation"),
        "players": mine.get("players") or [],
    }
