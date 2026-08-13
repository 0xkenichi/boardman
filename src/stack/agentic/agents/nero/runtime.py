"""Nero's brain — creator_nero_forge. Chess only. Does not import Raja."""
from __future__ import annotations

from typing import Any, Optional

import chess

from gaming.src.stack.agentic.agents.nero.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE
from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine, Mind
from gaming.src.stack.agentic.chess.openings import register_book

SHIPPED_GAMES = ("agentic.chess_standard",)

_books_ready = False


def _ensure_books() -> None:
    global _books_ready
    if _books_ready:
        return
    register_book("nero_white", OPENINGS_WHITE)
    register_book("nero_black", OPENINGS_BLACK)
    _books_ready = True


def _mind() -> Mind:
    raw = dict(MIND)
    raw.setdefault("name", "Nero")
    raw.setdefault("strategy_id", "nero_defense_v2")
    raw["book_ids_white"] = ["nero_white"]
    raw["book_ids_black"] = ["nero_black"]
    return Mind.from_dict(raw)


def pick_move(
    *,
    game_id: str = "agentic.chess_standard",
    fen: str,
    legal_moves: Optional[list[str]] = None,
    **_: Any,
) -> str:
    if game_id and game_id not in SHIPPED_GAMES:
        raise ValueError("Nero is chess-only — creator_nero_forge has not shipped this game")
    if not fen:
        raise ValueError("missing fen")
    _ensure_books()
    board = chess.Board(fen)
    engine = HybridEngine(_mind(), agent_id="agent_nero_sicilian_french", agent_name="Nero")
    mv = engine.choose_move(board)
    uci = mv.uci()
    legal = list(legal_moves or [])
    if legal and uci not in legal:
        san = board.san(mv)
        if san in legal:
            return san
        raise ValueError(f"Nero move {uci} not in legal_moves")
    return uci


def handle_webhook(body: dict[str, Any]) -> str:
    state = body.get("state") or {}
    return pick_move(
        game_id=str(body.get("game_id") or "agentic.chess_standard"),
        fen=str(state.get("fen") or body.get("fen") or ""),
        legal_moves=list(body.get("legal_moves") or state.get("legal_moves") or []),
    )
