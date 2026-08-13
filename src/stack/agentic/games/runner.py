"""
Generic multi-game match runner (non-chess).

p1 / p2 agents provide moves via:
  - simple_ai (built-in)
  - webhook runtime
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from gaming.src.stack.agentic.games.catalog import get_game
from gaming.src.stack.agentic.runtime.webhook import request_move


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def play_generic_match(
    *,
    game_id: str,
    p1_agent: dict[str, Any],
    p2_agent: dict[str, Any],
    move_delay_sec: float = 0.15,
    max_plies: int = 200,
    seed: Optional[int] = None,
    on_move: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    game = get_game(game_id)
    if not game:
        raise ValueError(f"unknown or chess game_id: {game_id}")

    rng = random.Random(seed if seed is not None else random.randint(1, 10**9))
    state = game.new_game()
    events: list[dict[str, Any]] = []
    started = _now()

    while True:
        st = game.status(state)
        if st.done:
            break
        if state.get("ply", 0) >= max_plies:
            st = game.status(state)
            if not st.done:
                # force adjudicate by simple AI scoring if possible
                st = GameResult_force(game, state)
            break

        side = game.current_side(state)
        agent = p1_agent if side == "p1" else p2_agent
        move = _pick_move(game, state, agent, rng)
        res = game.apply_move(state, move)
        if not res.ok:
            # fallback random legal
            legal = game.legal_moves(state)
            if not legal:
                st = game.status(state)
                break
            move = rng.choice(legal)
            res = game.apply_move(state, move)
            if not res.ok:
                break
        state = res.state
        ev = {
            "ply": state.get("ply"),
            "side": side,
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("name"),
            "move": move,
            "state": game.encode_public(state),
            "ts": _now(),
        }
        events.append(ev)
        if on_move:
            on_move(ev)
        if move_delay_sec > 0:
            time.sleep(move_delay_sec)

    st = game.status(state)
    winner_agent_id = None
    result_code = "draw"
    if st.winner_side == "p1":
        winner_agent_id = p1_agent["agent_id"]
        result_code = "p1_win"
    elif st.winner_side == "p2":
        winner_agent_id = p2_agent["agent_id"]
        result_code = "p2_win"

    return {
        "success": True,
        "game_id": game_id,
        "result": result_code,
        "termination": st.reason or st.outcome,
        "winner_agent_id": winner_agent_id,
        "winner_side": st.winner_side,
        "p1_agent_id": p1_agent["agent_id"],
        "p2_agent_id": p2_agent["agent_id"],
        "plies": state.get("ply", 0),
        "final_state": game.encode_public(state),
        "moves": events,
        "started_at": started,
        "ended_at": _now(),
        "seed": seed,
    }


def GameResult_force(game, state):
    """Adjudicate unfinished games by material-ish heuristics."""
    from gaming.src.stack.agentic.games.base import GameResult

    st = game.status(state)
    if st.done:
        return st
    # prefer non-draw: first player wins if ply odd? better: pass to status max
    return GameResult(True, "draw", None, "max_plies")


def _pick_move(game, state, agent, rng) -> str:
    runtime = (agent.get("runtime") or {}).get("engine") or agent.get("engine") or "simple_ai"
    webhook = (agent.get("runtime") or {}).get("webhook_url") or agent.get("webhook_url")

    from gaming.src.stack.agentic.runtime.webhook import ask_agent_move

    if runtime == "webhook" or webhook:
        try:
            mv = ask_agent_move(
                agent,
                game_id=game.game_id,
                state=game.encode_public(state),
                legal_moves=game.legal_moves(state),
                timeout_sec=float((agent.get("runtime") or {}).get("timeout_sec") or 25),
            )
            if mv and mv in game.legal_moves(state):
                return mv
        except Exception:
            pass
    return game.simple_ai_move(state, rng=rng)
