"""Connect Four — 7×6, connect 4."""
from __future__ import annotations

import random
from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult

ROWS, COLS, WIN = 6, 7, 4


class ConnectFour(GameModule):
    game_id = "agentic.connect4"
    display_name = "Connect Four"

    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "rows": ROWS,
            "cols": COLS,
            # board[row][col], row 0 = bottom
            "board": [["."] * COLS for _ in range(ROWS)],
            "to_move": "p1",
            "ply": 0,
            "marks": {"p1": "X", "p2": "O"},
        }

    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        board = state["board"]
        return [str(c) for c in range(COLS) if board[ROWS - 1][c] == "."]

    def apply_move(self, state: dict[str, Any], move: str) -> MoveResult:
        try:
            c = int(move.strip())
        except ValueError:
            return MoveResult(ok=False, error="column int 0-6")
        if c < 0 or c >= COLS:
            return MoveResult(ok=False, error="column out of range")
        board = [row[:] for row in state["board"]]
        if board[ROWS - 1][c] != ".":
            return MoveResult(ok=False, error="column full")
        r = 0
        for rr in range(ROWS):
            if board[rr][c] == ".":
                r = rr
                break
        side = state["to_move"]
        board[r][c] = state["marks"][side]
        new_state = {
            **state,
            "board": board,
            "to_move": "p2" if side == "p1" else "p1",
            "ply": state["ply"] + 1,
            "last_move": f"{c}@{r}",
        }
        return MoveResult(ok=True, move=str(c), state=new_state)

    def status(self, state: dict[str, Any]) -> GameResult:
        board = state["board"]
        marks = state["marks"]

        def winner_at(r: int, c: int) -> Optional[str]:
            ch = board[r][c]
            if ch == ".":
                return None
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cnt = 1
                rr, cc = r + dr, c + dc
                while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == ch:
                    cnt += 1
                    rr += dr
                    cc += dc
                rr, cc = r - dr, c - dc
                while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == ch:
                    cnt += 1
                    rr -= dr
                    cc -= dc
                if cnt >= WIN:
                    return "p1" if ch == marks["p1"] else "p2"
            return None

        for r in range(ROWS):
            for c in range(COLS):
                w = winner_at(r, c)
                if w:
                    return GameResult(True, f"{w}_win", w, "connect4")
        if not self.legal_moves(state):
            return GameResult(True, "draw", None, "full")
        return GameResult(False, "ongoing", None, "")

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        r = rng or random.Random()
        moves = self.legal_moves(state)
        # win
        for m in moves:
            res = self.apply_move(state, m)
            if res.ok and self.status(res.state).winner_side == state["to_move"]:
                return m
        # block
        for m in moves:
            res = self.apply_move(state, m)
            if not res.ok:
                continue
            opp = "p2" if state["to_move"] == "p1" else "p1"
            for m2 in self.legal_moves(res.state):
                res2 = self.apply_move(res.state, m2)
                if res2.ok and self.status(res2.state).winner_side == opp:
                    return m
        # prefer center
        order = sorted(moves, key=lambda x: abs(int(x) - 3))
        return order[0] if order else r.choice(moves)
