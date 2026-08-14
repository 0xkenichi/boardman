"""
Real-time agent vs agent chess until terminal result.

Uses HybridEngine (opening book + Stockfish APIs + local fallback).
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

import chess
import chess.pgn

from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine, mind_from_agent
from gaming.src.stack.agentic.runtime.webhook import ask_agent_move


@dataclass
class MoveEvent:
    ply: int
    move_number: int
    side: str
    agent_id: str
    agent_name: str
    san: str
    uci: str
    fen: str
    is_check: bool
    is_capture: bool
    board_unicode: str
    engine_source: str
    eval_pawns: Optional[float]
    ts: str
    clock: Optional[dict[str, Any]] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _material(board: chess.Board, color: chess.Color) -> int:
    values = {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
    }
    return sum(
        values.get(p.piece_type, 0)
        for p in board.piece_map().values()
        if p.color == color
    )


def _classify(
    board: chess.Board,
    *,
    eval_history: Optional[list[float]] = None,
) -> tuple[str, str, Optional[str], str]:
    """
    Prefer real checkmates. Else resign/adjudicate from engine eval (white POV).
    Avoid 'everything is a draw' when max plies hits equal material.
    """
    outcome = board.outcome()
    if outcome is not None:
        result_str = outcome.result()
        termination = outcome.termination.name if outcome.termination else "unknown"
        if outcome.winner is chess.WHITE:
            return "white_win", result_str, "white", termination
        if outcome.winner is chess.BLACK:
            return "black_win", result_str, "black", termination
        # Stalemate / formal draw — still try eval if we have a clear edge
        if eval_history:
            avg = sum(eval_history[-5:]) / max(1, len(eval_history[-5:]))
            if avg >= 0.9:
                return "white_win", "1-0", "white", "adjudicated_eval_over_draw"
            if avg <= -0.9:
                return "black_win", "0-1", "black", "adjudicated_eval_over_draw"
        return "draw", result_str, None, termination

    # No terminal rule yet — use eval then material
    if eval_history:
        recent = [e for e in eval_history[-6:] if e is not None]
        if recent:
            avg = sum(recent) / len(recent)
            # Clear advantage → award the win (demo / agent arena)
            if avg >= 1.0:
                return "white_win", "1-0", "white", "adjudicated_eval"
            if avg <= -1.0:
                return "black_win", "0-1", "black", "adjudicated_eval"
            # Slight edge still counts when game is long
            if board.ply() >= 60:
                if avg >= 0.45:
                    return "white_win", "1-0", "white", "adjudicated_eval_soft"
                if avg <= -0.45:
                    return "black_win", "0-1", "black", "adjudicated_eval_soft"

    wm, bm = _material(board, chess.WHITE), _material(board, chess.BLACK)
    if wm > bm:  # any material plus
        return "white_win", "1-0", "white", "adjudicated_material"
    if bm > wm:
        return "black_win", "0-1", "black", "adjudicated_material"
    # Dead equal — last non-zero eval or coin from seed later
    if eval_history:
        for e in reversed(eval_history):
            if e is not None and abs(e) >= 0.25:
                if e > 0:
                    return "white_win", "1-0", "white", "adjudicated_eval_tiebreak"
                return "black_win", "0-1", "black", "adjudicated_eval_tiebreak"
    return "draw", "1/2-1/2", None, "max_plies_equal"


def _default_max_plies() -> int:
    # Longer games → more checkmates / conversions
    return int(os.getenv("BOARDMAN_MAX_PLIES", "200"))


def _ask_builder_or_engine(agent: dict[str, Any], engine: HybridEngine, board: chess.Board, *, game_id: str) -> chess.Move:
    """Ask the builder webhook (or that silo only). Engine is last-resort fallback."""
    legal = [m.uci() for m in board.legal_moves]
    raw = ask_agent_move(
        agent,
        game_id=game_id,
        state={"fen": board.fen(), "to_move": "w" if board.turn == chess.WHITE else "b"},
        legal_moves=legal,
    )
    if raw:
        try:
            mv = chess.Move.from_uci(raw)
            if mv in board.legal_moves:
                engine.last_source = "builder_webhook"
                return mv
        except ValueError:
            pass
        try:
            mv = board.parse_san(raw)
            if mv in board.legal_moves:
                engine.last_source = "builder_webhook"
                return mv
        except ValueError:
            pass
    return engine.choose_move(board)


def play_match(
    *,
    white_agent: dict[str, Any],
    black_agent: dict[str, Any],
    move_delay_sec: float = 0.0,
    max_plies: Optional[int] = None,
    seed: Optional[int] = None,
    time_control_id: Optional[str] = None,
    use_agent_think_delay: bool = True,
    on_move: Optional[Callable[[MoveEvent], None]] = None,
) -> dict[str, Any]:
    from gaming.src.stack.agentic.clock import (
        MatchClock,
        negotiate_time_control,
        reasoning_delay_sec,
    )

    rng_seed = seed if seed is not None else random.randint(1, 10**9)
    max_plies = max_plies if max_plies is not None else _default_max_plies()
    board = chess.Board()
    rng_w = random.Random(rng_seed + 1)
    rng_b = random.Random(rng_seed + 2)

    # Both agents GM-strength (same max free SF depth). No intentional Nero nerf.
    default_d = int(os.getenv("BOARDMAN_SF_DEPTH", "18"))
    default_w = int(os.getenv("BOARDMAN_SF_DEPTH_WHITE", str(default_d)))
    default_b = int(os.getenv("BOARDMAN_SF_DEPTH_BLACK", str(default_d)))
    w_mind = mind_from_agent(white_agent)
    b_mind = mind_from_agent(black_agent)
    w_depth = default_w + int(getattr(w_mind, "depth_bonus", 0) or 0)
    b_depth = default_b + int(getattr(b_mind, "depth_bonus", 0) or 0)
    white_engine = HybridEngine(
        w_mind,
        agent_id=white_agent["agent_id"],
        agent_name=str(white_agent.get("name") or ""),
        wallet_address=str(white_agent.get("wallet_address") or ""),
        rng=rng_w,
        depth=w_depth,
    )
    black_engine = HybridEngine(
        b_mind,
        agent_id=black_agent["agent_id"],
        agent_name=str(black_agent.get("name") or ""),
        wallet_address=str(black_agent.get("wallet_address") or ""),
        rng=rng_b,
        depth=b_depth,
    )
    eval_history: list[float] = []
    # Only resign when completely lost — give room for mating attacks on camera
    resign_threshold = float(os.getenv("BOARDMAN_RESIGN_EVAL", "5.5"))

    # Negotiate clock from agent prefs (siloed identities, different tastes)
    prefs_w = white_agent.get("preferred_time_controls") or (
        (white_agent.get("economy") or {}).get("preferred_time_controls")
    ) or ["blitz_3|2"]
    prefs_b = black_agent.get("preferred_time_controls") or (
        (black_agent.get("economy") or {}).get("preferred_time_controls")
    ) or ["blitz_3|2"]
    tc_id = time_control_id or negotiate_time_control(list(prefs_w), list(prefs_b))
    match_clock = MatchClock.from_control(tc_id)

    events: list[dict[str, Any]] = []
    game = chess.pgn.Game()
    game.headers["Event"] = "Boardman Agent Arena"
    game.headers["Site"] = "boardman.playingsidequest.fun"
    game.headers["Date"] = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    game.headers["White"] = white_agent.get("name") or white_agent["agent_id"]
    game.headers["Black"] = black_agent.get("name") or black_agent["agent_id"]
    game.headers["WhiteAgent"] = white_agent["agent_id"]
    game.headers["BlackAgent"] = black_agent["agent_id"]
    game.headers["TimeControl"] = tc_id
    game.headers["Annotator"] = "Boardman HybridEngine (siloed minds + Stockfish)"
    node = game

    started = _now()
    flagged: Optional[str] = None
    resigned: Optional[str] = None  # side that resigned
    while not board.is_game_over() and board.ply() < max_plies:
        is_white = board.turn == chess.WHITE
        agent = white_agent if is_white else black_agent
        engine = white_engine if is_white else black_engine
        side = "white" if is_white else "black"
        mind = agent.get("mind") or {}
        rng = rng_w if is_white else rng_b

        match_clock.begin_turn(is_white)

        delay = 0.0
        if use_agent_think_delay:
            delay = reasoning_delay_sec(mind, rng=rng)
        if move_delay_sec > 0:
            delay = max(delay, move_delay_sec)
        if delay > 0:
            time.sleep(delay)

        mv = _ask_builder_or_engine(agent, engine, board, game_id="agentic.chess_standard")
        san = board.san(mv)
        is_cap = board.is_capture(mv)
        src = engine.last_source
        ev_eval = engine.last_eval
        # chess-api / SF eval is white-POV
        if ev_eval is not None:
            eval_history.append(float(ev_eval))
            # Resign if this side is clearly lost
            if is_white and ev_eval <= -resign_threshold:
                resigned = "white"
                node_comment = f"resign (eval {ev_eval:+.2f})"
                break
            if (not is_white) and ev_eval >= resign_threshold:
                resigned = "black"
                node_comment = f"resign (eval {ev_eval:+.2f})"
                break

        board.push(mv)
        node = node.add_variation(mv)

        clock_ev = match_clock.end_turn(is_white, san=san)
        if clock_ev.get("flag"):
            flagged = side
            node.comment = f"{src} · FLAG"
            break

        comment_bits = [src, f"clk {clock_ev['remaining_ms']}ms"]
        if ev_eval is not None:
            comment_bits.append(f"eval {ev_eval:+.2f}")
        node.comment = " · ".join(comment_bits)

        ev = MoveEvent(
            ply=board.ply(),
            move_number=(board.ply() + 1) // 2,
            side=side,
            agent_id=agent["agent_id"],
            agent_name=agent.get("name") or agent["agent_id"],
            san=san,
            uci=mv.uci(),
            fen=board.fen(),
            is_check=board.is_check(),
            is_capture=is_cap,
            board_unicode=board.unicode(borders=True),
            engine_source=src,
            eval_pawns=ev_eval,
            ts=_now(),
            clock=clock_ev,
        )
        payload = {**ev.__dict__, "think_delay_sec": delay}
        events.append(payload)
        if on_move:
            on_move(ev)

    if resigned:
        if resigned == "white":
            result_code, result_str, winner_color, termination = (
                "black_win",
                "0-1",
                "black",
                "resign",
            )
        else:
            result_code, result_str, winner_color, termination = (
                "white_win",
                "1-0",
                "white",
                "resign",
            )
    elif flagged:
        if flagged == "white":
            result_code, result_str, winner_color, termination = (
                "black_win",
                "0-1",
                "black",
                "timeout",
            )
        else:
            result_code, result_str, winner_color, termination = (
                "white_win",
                "1-0",
                "white",
                "timeout",
            )
    else:
        result_code, result_str, winner_color, termination = _classify(
            board, eval_history=eval_history
        )

    game.headers["Result"] = result_str
    pgn = str(game)

    winner_agent_id = None
    if winner_color == "white":
        winner_agent_id = white_agent["agent_id"]
    elif winner_color == "black":
        winner_agent_id = black_agent["agent_id"]

    return {
        "success": True,
        "game_id": "agentic.chess_standard",
        "result": result_code,
        "result_pgn": result_str,
        "termination": termination,
        "winner_agent_id": winner_agent_id,
        "winner_color": winner_color,
        "white_agent_id": white_agent["agent_id"],
        "black_agent_id": black_agent["agent_id"],
        "plies": board.ply(),
        "final_fen": board.fen(),
        "pgn": pgn,
        "moves": events,
        "started_at": started,
        "ended_at": _now(),
        "seed": rng_seed,
        "time_control_id": tc_id,
        "clock": match_clock.to_dict(),
        "engines": {
            "white": "hybrid+stockfish",
            "black": "hybrid+stockfish",
            "providers": ["chess-api.com", "stockfish.online", "local"],
            "siloed": True,
        },
    }


def iter_match(
    *,
    white_agent: dict[str, Any],
    black_agent: dict[str, Any],
    move_delay_sec: float = 0.0,
    max_plies: Optional[int] = None,
    seed: Optional[int] = None,
) -> Iterator[dict[str, Any]]:
    """Generator: move events then final (single game)."""
    box: dict[str, Any] = {"final": None}

    def on_move(ev: MoveEvent) -> None:
        box["last"] = {"type": "move", **ev.__dict__}

    # Stream by reimplementing loop so we don't double-play
    rng_seed = seed if seed is not None else random.randint(1, 10**9)
    max_plies = max_plies if max_plies is not None else _default_max_plies()
    board = chess.Board()
    white_engine = HybridEngine(
        mind_from_agent(white_agent),
        agent_id=white_agent["agent_id"],
        agent_name=str(white_agent.get("name") or ""),
        wallet_address=str(white_agent.get("wallet_address") or ""),
        rng=random.Random(rng_seed + 1),
    )
    black_engine = HybridEngine(
        mind_from_agent(black_agent),
        agent_id=black_agent["agent_id"],
        agent_name=str(black_agent.get("name") or ""),
        wallet_address=str(black_agent.get("wallet_address") or ""),
        rng=random.Random(rng_seed + 2),
    )
    events: list[dict[str, Any]] = []
    game = chess.pgn.Game()
    game.headers["White"] = white_agent.get("name") or white_agent["agent_id"]
    game.headers["Black"] = black_agent.get("name") or black_agent["agent_id"]
    node = game

    while not board.is_game_over() and board.ply() < max_plies:
        agent = white_agent if board.turn == chess.WHITE else black_agent
        engine = white_engine if board.turn == chess.WHITE else black_engine
        side = "white" if board.turn == chess.WHITE else "black"
        mv = _ask_builder_or_engine(agent, engine, board, game_id="agentic.chess_standard")
        san = board.san(mv)
        is_cap = board.is_capture(mv)
        src = engine.last_source
        ev_eval = engine.last_eval
        board.push(mv)
        node = node.add_variation(mv)
        payload = {
            "type": "move",
            "ply": board.ply(),
            "move_number": (board.ply() + 1) // 2,
            "side": side,
            "agent_id": agent["agent_id"],
            "agent_name": agent.get("name") or agent["agent_id"],
            "san": san,
            "uci": mv.uci(),
            "fen": board.fen(),
            "is_check": board.is_check(),
            "is_capture": is_cap,
            "board_unicode": board.unicode(borders=True),
            "engine_source": src,
            "eval_pawns": ev_eval,
            "ts": _now(),
        }
        events.append({k: v for k, v in payload.items() if k != "type"})
        yield payload
        if move_delay_sec > 0:
            time.sleep(move_delay_sec)

    result_code, result_str, winner_color, termination = _classify(board)
    game.headers["Result"] = result_str
    winner_agent_id = None
    if winner_color == "white":
        winner_agent_id = white_agent["agent_id"]
    elif winner_color == "black":
        winner_agent_id = black_agent["agent_id"]

    yield {
        "type": "final",
        "result": result_code,
        "result_pgn": result_str,
        "termination": termination,
        "winner_agent_id": winner_agent_id,
        "winner_color": winner_color,
        "plies": board.ply(),
        "final_fen": board.fen(),
        "pgn": str(game),
        "moves": events,
        "seed": rng_seed,
        "white_agent_id": white_agent["agent_id"],
        "black_agent_id": black_agent["agent_id"],
    }
