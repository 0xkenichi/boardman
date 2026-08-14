"""lichess-bot-style UCI engine for Boardman agents.

Same stack lichess-bot uses: a long-lived Stockfish process via python-chess.
Raja (and any agent) can call `best_move(fen, ...)` without talking to Lichess.

Do not vendor https://github.com/lichess-bot-devs/lichess-bot (AGPL). Clone
that repo separately and point it at this process or at builders/lichess_raja.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

import chess
import chess.engine

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_session: Optional[chess.engine.SimpleEngine] = None
_session_path: str = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def find_stockfish() -> str:
    env = (os.getenv("STOCKFISH_PATH") or os.getenv("RAJA_STOCKFISH") or "").strip()
    if env and Path(env).is_file() and os.access(env, os.X_OK):
        return env
    named = [
        _repo_root() / "engines" / "stockfish",
        _repo_root() / "third_party" / "lichess-bot" / "engines" / "stockfish",
    ]
    for p in named:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return shutil.which("stockfish") or ""


def engine_ready() -> bool:
    return bool(find_stockfish())


def _open(path: str) -> chess.engine.SimpleEngine:
    eng = chess.engine.SimpleEngine.popen_uci(path)
    threads = int(os.getenv("RAJA_UCI_THREADS") or "2")
    hash_mb = int(os.getenv("RAJA_UCI_HASH") or "128")
    try:
        eng.configure({"Threads": threads, "Hash": hash_mb})
    except chess.engine.EngineError:
        pass
    return eng


def _get_engine() -> Optional[chess.engine.SimpleEngine]:
    global _session, _session_path
    path = find_stockfish()
    if not path:
        return None
    with _lock:
        if _session is not None and _session_path == path:
            return _session
        if _session is not None:
            try:
                _session.quit()
            except Exception:
                pass
            _session = None
        try:
            _session = _open(path)
            _session_path = path
            logger.info("[lichess-uci] Stockfish %s", path)
            return _session
        except Exception:
            logger.exception("[lichess-uci] failed to start %s", path)
            _session = None
            _session_path = ""
            return None


def _clocks_from(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def clocks_from_webhook(body: dict[str, Any]) -> dict[str, Optional[int]]:
    """Pull wtime/btime/inc out of a boardman.agent.move.v1 body."""
    state = body.get("state") if isinstance(body.get("state"), dict) else {}
    clocks: dict[str, Any] = {}
    for src in (body.get("clocks"), state.get("clocks"), body, state):
        if isinstance(src, dict):
            clocks.update(src)
    white = clocks.get("white") if isinstance(clocks.get("white"), dict) else {}
    black = clocks.get("black") if isinstance(clocks.get("black"), dict) else {}
    return {
        "wtime_ms": _clocks_from(
            clocks.get("wtime_ms") or clocks.get("wtime") or white.get("remaining_ms")
        ),
        "btime_ms": _clocks_from(
            clocks.get("btime_ms") or clocks.get("btime") or black.get("remaining_ms")
        ),
        "winc_ms": _clocks_from(clocks.get("winc_ms") or clocks.get("winc") or clocks.get("inc_ms")),
        "binc_ms": _clocks_from(clocks.get("binc_ms") or clocks.get("binc") or clocks.get("inc_ms")),
        "movetime_ms": _clocks_from(clocks.get("movetime_ms") or body.get("movetime_ms")),
    }


def best_move(
    fen: str,
    *,
    legal_moves: Optional[list[str]] = None,
    movetime_ms: Optional[int] = None,
    wtime_ms: Optional[int] = None,
    btime_ms: Optional[int] = None,
    winc_ms: Optional[int] = None,
    binc_ms: Optional[int] = None,
) -> Optional[str]:
    """Return a legal UCI move, or None if the engine is missing/fails."""
    eng = _get_engine()
    if eng is None:
        return None
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    think = int(movetime_ms or os.getenv("RAJA_UCI_MOVETIME_MS") or "400")
    think = max(50, min(think, 8000))
    wtime = _clocks_from(wtime_ms)
    btime = _clocks_from(btime_ms)
    limit_kw: dict[str, float] = {}
    if wtime and btime:
        limit_kw["white_clock"] = wtime / 1000.0
        limit_kw["black_clock"] = btime / 1000.0
        winc = _clocks_from(winc_ms)
        binc = _clocks_from(binc_ms)
        if winc:
            limit_kw["white_inc"] = winc / 1000.0
        if binc:
            limit_kw["black_inc"] = binc / 1000.0
        # Webhook budget is ~8s. Never let a 3+ minute clock become a long think.
        cap_s = float(os.getenv("RAJA_UCI_MAX_CLOCK_S") or "2")
        cap_s = max(0.1, min(cap_s, 6.0))
        remaining = (wtime if board.turn == chess.WHITE else btime) / 1000.0
        limit_kw["time"] = min(cap_s, max(0.1, remaining * 0.08))
    else:
        limit_kw["time"] = think / 1000.0
    try:
        with _lock:
            result = eng.play(board, chess.engine.Limit(**limit_kw))
        if not result.move:
            return None
        uci = result.move.uci()
        legal = list(legal_moves or [])
        if legal and uci not in legal:
            san = board.san(result.move)
            if san in legal:
                return san
            return None
        return uci
    except Exception:
        logger.exception("[lichess-uci] play failed")
        return None


def close() -> None:
    global _session, _session_path
    with _lock:
        if _session is not None:
            try:
                _session.quit()
            except Exception:
                pass
        _session = None
        _session_path = ""
