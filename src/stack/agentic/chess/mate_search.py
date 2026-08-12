"""Shallow forced-mate search so agents convert and show real checkmates."""
from __future__ import annotations

from typing import Optional

import chess


def find_mate_in_1(board: chess.Board) -> Optional[chess.Move]:
    for mv in board.legal_moves:
        board.push(mv)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return mv
    return None


def find_mate_in_2(board: chess.Board) -> Optional[chess.Move]:
    """Return a move that forces mate in 2 if any (shallow)."""
    for mv in board.legal_moves:
        board.push(mv)
        if board.is_checkmate():
            board.pop()
            return mv
        # if opponent has no way to avoid mate next
        if board.is_game_over():
            board.pop()
            continue
        all_replies_lose = True
        has_reply = False
        for reply in board.legal_moves:
            has_reply = True
            board.push(reply)
            m2 = find_mate_in_1(board)
            board.pop()
            if m2 is None:
                all_replies_lose = False
                break
        board.pop()
        if has_reply and all_replies_lose:
            return mv
    return None


def prefer_forcing(board: chess.Board, candidates: list[chess.Move]) -> Optional[chess.Move]:
    """Among candidates, prefer checkmate > check > capture."""
    if not candidates:
        return None
    scored = []
    for mv in candidates:
        board.push(mv)
        score = 0
        if board.is_checkmate():
            score = 10_000
        elif board.is_check():
            score = 100
        board.pop()
        if board.is_capture(mv):
            score += 20
        scored.append((score, mv))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]
