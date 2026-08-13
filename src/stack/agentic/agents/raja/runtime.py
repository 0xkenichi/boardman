"""Raja's brain — creator_raja_lab. Chess only. Does not import Nero."""
from __future__ import annotations

from typing import Any, Optional

import chess

from gaming.src.stack.agentic.agents.raja.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE
from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine, Mind
from gaming.src.stack.agentic.chess.openings import register_book

SHIPPED_GAMES = ("agentic.chess_standard",)

_books_ready = False


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
    **_: Any,
) -> str:
    if game_id and game_id not in SHIPPED_GAMES:
        raise ValueError("Raja is chess-only — creator_raja_lab has not shipped this game")
    if not fen:
        raise ValueError("missing fen")
    _ensure_books()
    board = chess.Board(fen)
    engine = HybridEngine(_mind(), agent_id="agent_raja_kia_alekhine", agent_name="Raja")
    mv = engine.choose_move(board)
    uci = mv.uci()
    legal = list(legal_moves or [])
    if legal and uci not in legal:
        san = board.san(mv)
        if san in legal:
            return san
        raise ValueError(f"Raja move {uci} not in legal_moves")
    return uci


def handle_webhook(body: dict[str, Any]) -> str:
    state = body.get("state") or {}
    return pick_move(
        game_id=str(body.get("game_id") or "agentic.chess_standard"),
        fen=str(state.get("fen") or body.get("fen") or ""),
        legal_moves=list(body.get("legal_moves") or state.get("legal_moves") or []),
    )
