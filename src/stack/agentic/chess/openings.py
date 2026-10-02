"""
Opening book lookup — loads siloed per-agent books at runtime.

Shared infrastructure only. Raja and Nero books live in agents/*/mind.py
and are registered here without cross-importing agent strategy code at
module top-level beyond book tables.
"""
from __future__ import annotations

import random
from typing import Optional

import chess

from gaming.src.stack.agentic.chess.opening_stats import line_weight

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
    # Self-heal: a swallowed first build (import-order edge during registry
    # init) can leave _LOADED=True with empty books — rebuild on next use.
    if _LOADED and _BOOKS:
        return
    _LOADED = False
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
    rng: Optional[random.Random] = None,
    agent_id: str = "",
) -> Optional[chess.Move]:
    """Pick a repertoire move at a book position.

    Variety + learning: choose among ALL legal book moves at this position
    (multiple authored lines share theory squares), weighted by the agent's
    learned line results — not always the first authored hit. Deterministic
    engines otherwise replay the same opener every table.
    """
    ensure_books_loaded()
    if board.ply() >= ply_limit:
        return None
    k = _key(board)
    replay = board.copy()
    replay.reset()
    sans_prefix = []
    for m in board.move_stack:
        sans_prefix.append(replay.san(m))
        replay.push(m)
    candidates: list[tuple[str, chess.Move, float]] = []
    seen: set[str] = set()
    for bid in book_ids:
        for san in _BOOKS.get(bid, {}).get(k) or []:
            if san in seen:
                continue
            seen.add(san)
            try:
                mv = board.parse_san(san)
            except ValueError:
                continue
            if mv in board.legal_moves:
                w = line_weight(agent_id, sans_prefix, san) if agent_id else 1.0
                candidates.append((san, mv, w))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][1]
    r = rng or random
    weights = [max(0.05, w) for _, _, w in candidates]
    picked = r.choices(candidates, weights=weights, k=1)[0]
    return picked[1]


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
