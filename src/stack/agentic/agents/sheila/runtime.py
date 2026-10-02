"""Sheila's brain — creator_sheila_lab. Chess only. Does not import Raja or Nero.

Move order (shared brain): opening book → mate hunt → LLM (if enabled) →
local UCI Ethereal multipv persona blend → remote Stockfish APIs → styled
fallback. Her builder process sets BOARDMAN_UCI_ENGINE to the Ethereal
binary, so "the engine" for Sheila is Ethereal, not Stockfish.
"""
from __future__ import annotations

from typing import Any, Optional

import chess

from gaming.src.stack.agentic.agents.sheila.mind import MIND, OPENINGS_BLACK, OPENINGS_WHITE
from gaming.src.stack.agentic.chess.agent_brain import pick_with_brain
from gaming.src.stack.agentic.chess.hybrid_engine import Mind
from gaming.src.stack.agentic.chess import lichess_uci
from gaming.src.stack.agentic.chess.openings import register_book

SHIPPED_GAMES = ("agentic.chess_standard",)

_books_ready = False
LAST_SOURCE = "none"


def _ensure_books() -> None:
    global _books_ready
    if _books_ready:
        return
    register_book("sheila_white", OPENINGS_WHITE)
    register_book("sheila_black", OPENINGS_BLACK)
    _books_ready = True


def _mind() -> Mind:
    raw = dict(MIND)
    raw.setdefault("name", "Sheila")
    raw.setdefault("strategy_id", "sheila_anaconda_v1")
    raw["book_ids_white"] = ["sheila_white"]
    raw["book_ids_black"] = ["sheila_black"]
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
        raise ValueError("Sheila is chess-only — creator_sheila_lab has not shipped this game")
    if not fen:
        raise ValueError("missing fen")
    LAST_SOURCE = "thinking"  # reset per request — only report what THIS move used
    _ensure_books()
    out, source = pick_with_brain(
        mind=_mind(),
        agent_id="agent_sheila_anaconda",
        agent_name="Sheila",
        fen=fen,
        legal_moves=legal_moves,
        wtime_ms=wtime_ms,
        btime_ms=btime_ms,
        winc_ms=winc_ms,
        binc_ms=binc_ms,
        movetime_ms=movetime_ms,
    )
    LAST_SOURCE = source
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
