"""Raja's brain — creator_raja_lab. Chess only. Does not import Nero.

Move order: local UCI Stockfish (lichess-bot stack via python-chess) → HybridEngine.
"""
from __future__ import annotations

from typing import Any, Optional

import chess

from gaming.src.stack.agentic.agents.raja.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE
from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine, Mind
from gaming.src.stack.agentic.chess import lichess_uci
from gaming.src.stack.agentic.chess.openings import register_book

SHIPPED_GAMES = ("agentic.chess_standard",)

_books_ready = False
LAST_SOURCE = "none"


def _ensure_books() -> None:
    global _books_ready
    if _books_ready:
        return
    register_book("raja_white", OPENINGS_WHITE)
    register_book("raja_black", OPENINGS_BLACK)
    _books_ready = True


def _mind() -> Mind:
    raw = dict(MIND)
    raw.setdefault("name", "Raja")
    raw.setdefault("strategy_id", "raja_mate_hunter_v3")
    raw["book_ids_white"] = ["raja_white"]
    raw["book_ids_black"] = ["raja_black"]
    return Mind.from_dict(raw)


def pick_move(
    *,
    game_id: str = "agentic.chess_standard",
    fen: str,
    legal_moves: Optional[list[str]] = None,
    wtime_ms: Optional[int] = None,
    btime_ms: Optional[int] = None,
    winc_ms: Optional[int] = None,
    binc_ms: Optional[int] = None,
    movetime_ms: Optional[int] = None,
    **_: Any,
) -> str:
    global LAST_SOURCE
    if game_id and game_id not in SHIPPED_GAMES:
        raise ValueError("Raja is chess-only — creator_raja_lab has not shipped this game")
    if not fen:
        raise ValueError("missing fen")
    uci = lichess_uci.best_move(
        fen,
        legal_moves=legal_moves,
        movetime_ms=movetime_ms,
        wtime_ms=wtime_ms,
        btime_ms=btime_ms,
        winc_ms=winc_ms,
        binc_ms=binc_ms,
    )
    if uci:
        LAST_SOURCE = "lichess_uci"
        return uci
    _ensure_books()
    board = chess.Board(fen)
    engine = HybridEngine(_mind(), agent_id="agent_raja_kia_alekhine", agent_name="Raja")
    mv = engine.choose_move(board)
    LAST_SOURCE = getattr(engine, "last_source", None) or "hybrid"
    out = mv.uci()
    legal = list(legal_moves or [])
    if legal and out not in legal:
        san = board.san(mv)
        if san in legal:
            return san
        raise ValueError(f"Raja move {out} not in legal_moves")
    return out


def handle_webhook(body: dict[str, Any]) -> str:
    state = body.get("state") or {}
    clocks = lichess_uci.clocks_from_webhook(body)
    return pick_move(
        game_id=str(body.get("game_id") or "agentic.chess_standard"),
        fen=str(state.get("fen") or body.get("fen") or ""),
        legal_moves=list(body.get("legal_moves") or state.get("legal_moves") or []),
        **clocks,
    )
