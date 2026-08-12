"""
Opening book lookup — loads siloed per-agent books at runtime.

Shared infrastructure only. Raja and Nero books live in agents/*/mind.py
and are registered here without cross-importing agent strategy code at
module top-level beyond book tables.
"""
from __future__ import annotations

from typing import Optional

import chess

_BOOKS: dict[str, dict[str, list[str]]] = {}
_LOADED = False


def _key(board: chess.Board) -> str:
    parts = board.fen().split(" ")
    return f"{parts[0]} {parts[1]}"


def _build(lines: list[list[str]]) -> dict[str, list[str]]:
    book: dict[str, list[str]] = {}
    for sans in lines:
        board = chess.Board()
        for san in sans:
            k = _key(board)
            book.setdefault(k, [])
            if san not in book[k]:
                book[k].append(san)
            try:
                board.push_san(san)
            except ValueError:
                break
    return book


def ensure_books_loaded() -> None:
    global _LOADED, _BOOKS
    if _LOADED:
        return
    # Import siloed packages separately — they never import each other
    from gaming.src.stack.agentic.agents.raja.mind import (
        OPENINGS_WHITE as RW,
        OPENINGS_BLACK as RB,
    )
    from gaming.src.stack.agentic.agents.nero.mind import (
        OPENINGS_WHITE as NW,
        OPENINGS_BLACK as NB,
    )

    _BOOKS = {
        "raja_white": _build(RW),
        "raja_black": _build(RB),
        "nero_white": _build(NW),
        "nero_black": _build(NB),
        # legacy aliases
        "kia_white": _build(RW),
        "alekhine_black": _build(RB),
        "nero_white_legacy": _build(NW),
        "sicilian_black": _build(NB),
        "french_black": _build(NB),
    }
    _LOADED = True


def register_book(book_id: str, lines: list[list[str]]) -> None:
    """Third-party deploy: register private opening lines under a book id."""
    ensure_books_loaded()
    _BOOKS[book_id] = _build(lines)


def book_move(
    board: chess.Board,
    book_ids: list[str],
    *,
    ply_limit: int = 24,
) -> Optional[chess.Move]:
    ensure_books_loaded()
    if board.ply() >= ply_limit:
        return None
    k = _key(board)
    for bid in book_ids:
        sans = _BOOKS.get(bid, {}).get(k) or []
        for san in sans:
            try:
                mv = board.parse_san(san)
            except ValueError:
                continue
            if mv in board.legal_moves:
                return mv
    return None


def pick_black_books(primary: str, secondary: str, board: chess.Board) -> list[str]:
    if board.move_stack:
        tmp = board.root()
        first_black: Optional[str] = None
        for i, mv in enumerate(board.move_stack):
            if i % 2 == 1:
                first_black = tmp.san(mv)
                break
            tmp.push(mv)
        if first_black in {"c5", "e6", "c6", "Nf6", "d5", "e5", "g6"}:
            return [primary]
    return [primary, secondary] if secondary != primary else [primary]
