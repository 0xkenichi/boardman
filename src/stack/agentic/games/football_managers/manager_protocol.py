"""AFM manager protocol — the House asks a manager for its matchday plan.

Same shape as the chess move loop (`runtime/webhook.py`): before a matchday
locks, the House POSTs the *observable* context to the manager's webhook and
the manager replies JSON. Unlike chess there is no hidden information: the
ask carries the opponent's full lineup + record, but never the opponent's
hidden mind sliders.

  House → agent webhook (POST)
  {
    "protocol": "boardman.agent.football_managers.matchday.v1",
    "game_id": "agentic.football_managers",
    "agent_id": "...",
    "season_no": 1, "matchday": 3,
    "fixture": { "home": "...", "away": "...", "my_side": "home", "opponent": "..." },
    "my_club": { "club_name", "formation", "tactical_tags", "squad": [...],
                 "unavailable": [...], "record": {...}, "wallet_usdc" },
    "opposition": { "club_name", "formation", "tactical_tags",
                    "lineup": [...], "record": {...} },
    "legal": { "formations", "starters", "max_bench", "tactical_tags", "deadline" }
  }

  Agent → House (JSON reply)
  { "formation": "3-4-3", "xi": [11 ids], "bench": [≤5 ids],
    "tactical_tags": ["high_press"], "instructions": "..." }

Any reply that is missing, malformed or breaks the hard rules (illegal XI,
unknown formation/tag, bench overlap) is rejected and the manager falls back
to the deterministic `decide_matchday` — a club can never be defaulted.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

PROTOCOL = "boardman.agent.football_managers.matchday.v1"
GAME_ID = "agentic.football_managers"
DEFAULT_TIMEOUT_SEC = 8.0

MAX_STARTERS = 11


# ---------------------------------------------------------------- press conference

# The House's standard pre-match and post-match questions for a manager.
# These are deterministic and opinion-free: they exist so the spectator feed
# can render "the manager was asked… and replied…" without inventing quotes.

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


def build_press_conference_ask(
    agent_id: str,
    opponent_id: str,
    my_side: str,
    phase: str,
    *,
    score_before: dict[str, int] | None = None,
) -> dict[str, Any]:
    """The press-conference ask the House sends a manager for one phase.

    `phase` is "pre" or "post". For the post-match ask the House may pass
    the scoreline so the question set stays the same but the agent can tailor
    its reply (the House never invents the reply).
    """
    return {
        "protocol": PROTOCOL,
        "game_id": GAME_ID,
        "agent_id": agent_id,
        "phase": phase,
        "opponent_id": opponent_id,
        "my_side": my_side,
        "questions": PRESS_CONFERENCE_QUESTIONS.get(phase, []),
        "score_before": score_before,
    }


def request_press_conference_answer(
    agent: dict[str, Any],
    ask: dict[str, Any],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any] | None:
    """POST a press-conference ask to the agent's webhook and read its reply.

    Returns the agent's JSON answer (or None on any transport/parse failure).
    The answer is expected to be a flat object mapping each question string to
    the manager's reply string (the House never invents the reply).
    """
    from gaming.src.stack.agentic.runtime.webhook import webhook_url_for

    url = webhook_url_for(agent)
    if not url:
        return None
    data = json.dumps(ask).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BoardmanAgentRuntime/1.0",
            "X-Boardman-Agent": str(agent.get("agent_id") or ""),
            "X-Boardman-Protocol": PROTOCOL,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("[afm-pc] press-conference ask failed for %s: %s", url, exc)
        return None
    if not isinstance(body, dict):
        return None
    # accept both {"answers": {...}} envelopes and a bare {question: reply} map
    answers = body.get("answers")
    if isinstance(answers, dict):
        return answers
    if all(isinstance(k, str) for k in body):
        return dict(body)
    return None


# ---------------------------------------------------------------- the ask

def _record(row: dict[str, Any]) -> dict[str, int]:
    return {
        "played": int(row.get("played") or 0),
        "wins": int(row.get("wins") or 0),
        "draws": int(row.get("draws") or 0),
        "losses": int(row.get("losses") or 0),
        "points": int(row.get("points") or 0),
    }


def _player_entries(
    players: list[dict[str, Any]],
    condition: Optional[dict[str, float]] = None,
) -> list[dict[str, Any]]:
    """Observable squad rows for the ask payload.

    `condition` (0..1) is the tiredness carried from the last fixture — the
    agent's own squad rows carry it so a manager can rest heavy legs; the
    opposition's lineup rows never do (it is not observable to them).
    """
    cond = condition or {}
    return [
        {
            "player_id": str(p.get("player_id") or ""),
            "name": str(p.get("name") or ""),
            "position": str(p.get("slot") or p.get("primary_pos") or "MID").upper(),
            "rating": float(p.get("base_rating") or 70),
            **({"condition": round(float(cond[p["player_id"]]), 2)}
               if p.get("player_id") in cond else {}),
        }
        for p in players
    ]


def _unavailable(club: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for p in club.get("squad") or []:
        if not isinstance(p, dict):
            continue
        if p.get("injury"):
            out.append(
                {
                    "player_id": str(p.get("player_id") or ""),
                    "name": str(p.get("name") or ""),
                    "reason": "injury",
                }
            )
        elif int(p.get("suspension_matches") or 0) > 0:
            out.append(
                {
                    "player_id": str(p.get("player_id") or ""),
                    "name": str(p.get("name") or ""),
                    "reason": "suspended",
                }
            )
    return out


def _wallet_usdc(agent_id: str) -> str:
    try:
        from gaming.src.stack.agentic.games.football_managers.season import _wallet
        from gaming.src.stack.agentic.ledger import L

        w = _wallet(agent_id)
        return str(L.balance(w)) if w else "0"
    except Exception:
        return "0"


def build_matchday_ask(
    agent_id: str,
    season: dict[str, Any],
    matchday: int,
) -> Optional[dict[str, Any]]:
    """The observable context the House sends a manager before it decides.

    Returns None on a bye or missing squad — the caller then skips the ask.
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        FORMATIONS,
        MAX_BENCH,
        TACTICAL_TAGS,
        current_condition,
    )
    from gaming.src.stack.agentic.games.football_managers.decide import matchday_context

    ctx = matchday_context(agent_id, season, matchday)
    if not ctx:
        return None

    club = ctx["club"] or {}
    opp = ctx["opp_club"] or {}
    standings = season.get("standings") or {}
    info = (season.get("matchdays") or {}).get(str(matchday)) or {}

    my_side = "home" if ctx["home_agent"] == agent_id else "away"
    return {
        "protocol": PROTOCOL,
        "game_id": GAME_ID,
        "agent_id": agent_id,
        "season_no": int(season.get("season_no") or 0),
        "matchday": matchday,
        "fixture": {
            "home": str(ctx["home_agent"]),
            "away": str(ctx["away_agent"]),
            "my_side": my_side,
            "opponent": str(ctx["opponent_id"]),
        },
        "my_club": {
            "club_name": str(club.get("club_name") or ""),
            "formation": str(club.get("formation") or "4-3-3"),
            "tactical_tags": list(club.get("tactical_tags") or ["balanced"]),
            "squad": _player_entries(
                ctx["players"],
                condition=current_condition(agent_id),
            ),
            "unavailable": _unavailable(club),
            "record": _record(standings.get(agent_id) or {}),
            "wallet_usdc": _wallet_usdc(agent_id),
        },
        "opposition": {
            "agent_id": str(ctx["opponent_id"]),
            "club_name": str(opp.get("club_name") or ""),
            "formation": str(opp.get("formation") or "4-3-3"),
            "tactical_tags": list(opp.get("tactical_tags") or ["balanced"]),
            "lineup": _player_entries(ctx["opp_players"]),
            "record": _record(standings.get(ctx["opponent_id"]) or {}),
        },
        "legal": {
            "formations": list(FORMATIONS),
            "starters": MAX_STARTERS,
            "max_bench": int(MAX_BENCH),
            "tactical_tags": list(TACTICAL_TAGS),
            "deadline": str(info.get("deadline_at") or ""),
        },
    }


# ---------------------------------------------------------------- the reply

def request_matchday_plan(
    agent: dict[str, Any],
    ask: dict[str, Any],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Optional[dict[str, Any]]:
    """POST the ask to the agent's webhook and read its plan reply.

    Accepts the builder-server envelope `{"move": {plan}}` (the same shape
    `serve_builder_webhook` produces for chess) plus flat `{plan}` / bare
    plan replies. Returns None on any transport failure — the caller falls
    back to the deterministic decision.
    """
    from gaming.src.stack.agentic.runtime.webhook import webhook_url_for

    url = webhook_url_for(agent)
    if not url:
        return None
    data = json.dumps(ask).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BoardmanAgentRuntime/1.0",
            "X-Boardman-Agent": str(agent.get("agent_id") or ""),
            "X-Boardman-Protocol": PROTOCOL,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("[afm-proto] %s ask failed: %s", url, exc)
        return None
    if not isinstance(body, dict):
        return None
    for key in ("move", "plan"):
        val = body.get(key)
        if isinstance(val, dict):
            return val
    if "formation" in body and "xi" in body:
        return body  # bare plan reply
    return None


def validate_matchday_plan(
    plan: Any,
    squad_players: list[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], str]:
    """Enforce the hard rules on a manager's reply.

    Returns (cleaned_plan, "") on success or (None, reason) on rejection.
    Only squad members may start; exactly 11 starters with a GK; bench ≤
    MAX_BENCH, no overlaps or repeats; formation + tags from the whitelists.
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        FORMATIONS,
        MAX_BENCH,
        TACTICAL_TAGS,
    )

    if not isinstance(plan, dict):
        return None, "reply was not a plan object"

    formation = str(plan.get("formation") or "")
    if formation not in FORMATIONS:
        return None, f"unknown formation {formation!r}"

    squad_ids = {str(p.get("player_id") or "") for p in squad_players}
    by_id = {str(p.get("player_id") or ""): p for p in squad_players}

    xi = plan.get("xi") or plan.get("starters")
    if not isinstance(xi, list) or len(xi) != MAX_STARTERS:
        return None, f"xi must list exactly {MAX_STARTERS} players"
    xi_ids = [str(pid) for pid in xi]
    if len(set(xi_ids)) != len(xi_ids):
        return None, "xi contains duplicate players"
    missing = [pid for pid in xi_ids if pid not in squad_ids]
    if missing:
        return None, f"xi references players not in the squad: {missing[:3]}"
    if not any(str(by_id[pid].get("slot") or by_id[pid].get("primary_pos") or "").upper() == "GK" for pid in xi_ids):
        return None, "xi has no goalkeeper"

    bench = plan.get("bench") or []
    if not isinstance(bench, list) or len(bench) > int(MAX_BENCH):
        return None, f"bench must list at most {MAX_BENCH} players"
    bench_ids = [str(pid) for pid in bench]
    if len(set(bench_ids)) != len(bench_ids) or any(pid in set(xi_ids) for pid in bench_ids):
        return None, "bench overlaps the xi or repeats players"
    missing_b = [pid for pid in bench_ids if pid not in squad_ids]
    if missing_b:
        return None, f"bench references players not in the squad: {missing_b[:3]}"

    tags = plan.get("tactical_tags") or plan.get("tags")
    if not isinstance(tags, list) or not tags or any(t not in TACTICAL_TAGS for t in tags):
        return None, f"tactical_tags must be non-empty, one of {sorted(TACTICAL_TAGS)}"

    return {
        "formation": formation,
        "starters": xi_ids,
        "bench": bench_ids,
        "tags": [str(t) for t in tags],
        "instructions": str(plan.get("instructions") or "").strip() or None,
    }, ""


# ---------------------------------------------------------------- the hook

def ask_matchday_plan(
    agent: dict[str, Any],
    season: dict[str, Any],
    matchday: int,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """One manager's plan for a matchday: webhook first, deterministic fallback.

    Returns {plan, source, error, instructions, asked}. `source` is
    "webhook" when the agent answered a valid plan itself, else "auto" for
    the deterministic `decide_matchday` fallback (a dead/malformed webhook
    never defaults a club — the fallback guarantees a legal XI).
    """
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.decide import decide_matchday

    agent_id = str(agent.get("agent_id") or "")
    club = get_club(agent_id) or {}
    squad_players = [p for p in (club.get("squad") or []) if isinstance(p, dict)]

    plan: Optional[dict[str, Any]] = None
    source = "auto"
    error: Optional[str] = None
    instructions: Optional[str] = None
    asked = False

    ask = build_matchday_ask(agent_id, season, matchday)
    if ask:
        asked = True
        reply = request_matchday_plan(agent, ask, timeout_sec=timeout_sec)
        if reply:
            valid, err = validate_matchday_plan(reply, squad_players)
            if valid:
                instructions = valid.pop("instructions", None)
                plan = valid
                source = "webhook"
            else:
                error = err
        else:
            error = "no reply from webhook"

    if plan is None:
        try:
            fb = decide_matchday(agent_id, season, matchday)
            if fb:
                plan = {
                    "formation": fb["formation"],
                    "starters": list(fb["starters"]),
                    "bench": list(fb["bench"]),
                    "tags": list(fb["tags"]),
                }
                source = "auto"
        except Exception as exc:
            error = f"deterministic fallback failed: {exc}"

    return {
        "plan": plan,
        "source": source,
        "error": error,
        "instructions": instructions,
        "asked": asked,
    }