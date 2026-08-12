"""English draughts / checkers — 8×8, men only + kings, simple rules for agents."""
from __future__ import annotations

import random
from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult

# Board: dark squares only playable. We use full 8x8; empty light ignored.
# p1 = dark pieces move up (increasing row), p2 move down.
# Notation: from-to as "c2-d3" or capture "c2-e4" (algebraic-ish files a-h ranks 1-8)


def _idx(r: int, c: int) -> bool:
    return 0 <= r < 8 and 0 <= c < 8


class Checkers(GameModule):
    game_id = "agentic.checkers"
    display_name = "Checkers / Draughts"

    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        board = [["."] * 8 for _ in range(8)]
        # p2 on top (rows 5-7), p1 bottom (rows 0-2) — dark squares only (r+c odd)
        for r in range(3):
            for c in range(8):
                if (r + c) % 2 == 1:
                    board[r][c] = "x"  # p1 man
        for r in range(5, 8):
            for c in range(8):
                if (r + c) % 2 == 1:
                    board[r][c] = "o"  # p2 man
        return {
            "game_id": self.game_id,
            "board": board,
            "to_move": "p1",
            "ply": 0,
            "marks": {"p1": "x", "p2": "o", "p1k": "X", "p2k": "O"},
        }

    def _pieces(self, side: str) -> set[str]:
        if side == "p1":
            return {"x", "X"}
        return {"o", "O"}

    def _is_king(self, ch: str) -> bool:
        return ch in {"X", "O"}

    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        side = state["to_move"]
        board = state["board"]
        captures: list[str] = []
        quiet: list[str] = []
        dirs_man = [(1, -1), (1, 1)] if side == "p1" else [(-1, -1), (-1, 1)]
        dirs_king = [(1, -1), (1, 1), (-1, -1), (-1, 1)]

        for r in range(8):
            for c in range(8):
                ch = board[r][c]
                if ch not in self._pieces(side):
                    continue
                dirs = dirs_king if self._is_king(ch) else dirs_man
                for dr, dc in dirs:
                    # quiet
                    rr, cc = r + dr, c + dc
                    if _idx(rr, cc) and board[rr][cc] == "." and (rr + cc) % 2 == 1:
                        quiet.append(self._fmt(r, c, rr, cc))
                    # capture
                    mr, mc = r + dr, c + dc
                    lr, lc = r + 2 * dr, c + 2 * dc
                    if (
                        _idx(mr, mc)
                        and _idx(lr, lc)
                        and board[mr][mc] not in {".", *self._pieces(side)}
                        and board[lr][lc] == "."
                        and (lr + lc) % 2 == 1
                    ):
                        captures.append(self._fmt(r, c, lr, lc))
        # must capture if available
        return captures if captures else quiet

    def _fmt(self, r1: int, c1: int, r2: int, c2: int) -> str:
        return f"{chr(97 + c1)}{r1 + 1}-{chr(97 + c2)}{r2 + 1}"

    def _parse(self, move: str) -> tuple[int, int, int, int]:
        a, b = move.lower().replace(" ", "").split("-")
        c1, r1 = ord(a[0]) - 97, int(a[1:]) - 1
        c2, r2 = ord(b[0]) - 97, int(b[1:]) - 1
        return r1, c1, r2, c2

    def apply_move(self, state: dict[str, Any], move: str) -> MoveResult:
        try:
            r1, c1, r2, c2 = self._parse(move)
        except Exception:
            return MoveResult(ok=False, error="move format a1-b2")
        if move not in self.legal_moves(state):
            return MoveResult(ok=False, error="illegal move")
        board = [row[:] for row in state["board"]]
        ch = board[r1][c1]
        board[r1][c1] = "."
        board[r2][c2] = ch
        # capture mid
        if abs(r2 - r1) == 2:
            board[(r1 + r2) // 2][(c1 + c2) // 2] = "."
        # promote
        if ch == "x" and r2 == 7:
            board[r2][c2] = "X"
        if ch == "o" and r2 == 0:
            board[r2][c2] = "O"
        side = state["to_move"]
        new_state = {
            **state,
            "board": board,
            "to_move": "p2" if side == "p1" else "p1",
            "ply": state["ply"] + 1,
            "last_move": move,
        }
        return MoveResult(ok=True, move=move, state=new_state)

    def status(self, state: dict[str, Any]) -> GameResult:
        p1 = sum(1 for row in state["board"] for c in row if c in {"x", "X"})
        p2 = sum(1 for row in state["board"] for c in row if c in {"o", "O"})
        if p1 == 0:
            return GameResult(True, "p2_win", "p2", "no_pieces")
        if p2 == 0:
            return GameResult(True, "p1_win", "p1", "no_pieces")
        if not self.legal_moves(state):
            # side to move loses
            loser = state["to_move"]
            winner = "p2" if loser == "p1" else "p1"
            return GameResult(True, f"{winner}_win", winner, "no_moves")
        if state["ply"] >= 150:
            if p1 > p2:
                return GameResult(True, "p1_win", "p1", "adjudicated")
            if p2 > p1:
                return GameResult(True, "p2_win", "p2", "adjudicated")
            return GameResult(True, "draw", None, "max_plies")
        return GameResult(False, "ongoing", None, "")

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        r = rng or random.Random()
        moves = self.legal_moves(state)
        # prefer captures
        caps = [m for m in moves if abs(self._parse(m)[0] - self._parse(m)[2]) == 2]
        pool = caps or moves
        return r.choice(pool)
