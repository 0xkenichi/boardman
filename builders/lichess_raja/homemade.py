"""Drop-in homemade engine for lichess-bot — Raja.

Copy this file over `homemade.py` in a clone of
https://github.com/lichess-bot-devs/lichess-bot (or append the Raja class).

  engine:
    protocol: homemade
    name: Raja

This file is Boardman's adapter. It does not vendor lichess-bot (AGPL).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import chess

logger = logging.getLogger(__name__)

_BOARDMAN = Path(os.getenv("BOARDMAN_ROOT") or Path(__file__).resolve().parents[2])
if _BOARDMAN.is_dir() and str(_BOARDMAN) not in sys.path:
    sys.path.insert(0, str(_BOARDMAN))


def raja_search(
    board: chess.Board,
    *,
    wtime_ms: int | None = None,
    btime_ms: int | None = None,
    winc_ms: int | None = None,
    binc_ms: int | None = None,
    movetime_ms: int | None = None,
    root_moves: list[chess.Move] | None = None,
) -> chess.Move:
    legal = list(root_moves) if root_moves else list(board.legal_moves)
    legal_uci = [m.uci() for m in legal]
    try:
        from gaming.src.stack.agentic.agents.raja.runtime import pick_move

        raw = pick_move(
            fen=board.fen(),
            legal_moves=legal_uci,
            wtime_ms=wtime_ms,
            btime_ms=btime_ms,
            winc_ms=winc_ms,
            binc_ms=binc_ms,
            movetime_ms=movetime_ms,
        )
        mv = chess.Move.from_uci(raw)
        if mv in legal:
            return mv
    except Exception:
        logger.exception("Raja pick_move failed; trying local UCI")
    try:
        from gaming.src.stack.agentic.chess import lichess_uci

        raw = lichess_uci.best_move(
            board.fen(),
            legal_moves=legal_uci,
            wtime_ms=wtime_ms,
            btime_ms=btime_ms,
            winc_ms=winc_ms,
            binc_ms=binc_ms,
            movetime_ms=movetime_ms,
        )
        if raw:
            mv = chess.Move.from_uci(raw)
            if mv in legal:
                return mv
    except Exception:
        logger.exception("lichess_uci failed")
    if not legal:
        raise ValueError("no legal moves")
    return legal[0]


def _clocks_from_limit(board: chess.Board, time_limit: Any) -> dict[str, int | None]:
    movetime = None
    wtime = btime = winc = binc = None
    if time_limit is not None:
        if getattr(time_limit, "time", None):
            movetime = int(float(time_limit.time) * 1000)
        if getattr(time_limit, "white_clock", None):
            wtime = int(float(time_limit.white_clock) * 1000)
        if getattr(time_limit, "black_clock", None):
            btime = int(float(time_limit.black_clock) * 1000)
        if getattr(time_limit, "white_inc", None):
            winc = int(float(time_limit.white_inc) * 1000)
        if getattr(time_limit, "black_inc", None):
            binc = int(float(time_limit.black_inc) * 1000)
    return {
        "wtime_ms": wtime,
        "btime_ms": btime,
        "winc_ms": winc,
        "binc_ms": binc,
        "movetime_ms": movetime,
    }


try:
    from chess.engine import PlayResult
    from lib.engine_wrapper import MinimalEngine
    from lib.lichess_types import HOMEMADE_ARGS_TYPE, MOVE

    class Raja(MinimalEngine):
        """Homemade engine name referenced by config.yml `engine.name`."""

        def search(self, board: chess.Board, *args: HOMEMADE_ARGS_TYPE) -> PlayResult:
            time_limit = args[0] if args else None
            root_moves = args[3] if len(args) >= 4 else None
            roots = root_moves if isinstance(root_moves, list) else None
            mv = raja_search(board, root_moves=roots, **_clocks_from_limit(board, time_limit))
            return PlayResult(mv, None)

except ImportError:
    class Raja:  # type: ignore[no-redef]
        """Standalone stand-in when lichess-bot is not on PYTHONPATH."""

        def search(self, board: chess.Board, *args: Any) -> chess.Move:
            time_limit = args[0] if args else None
            root_moves = args[3] if len(args) >= 4 else None
            roots = root_moves if isinstance(root_moves, list) else None
            return raja_search(board, root_moves=roots, **_clocks_from_limit(board, time_limit))
