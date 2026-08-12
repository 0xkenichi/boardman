"""Tic-tac-toe and variants (3x3 classic, 4x4 optional)."""
from __future__ import annotations

import random
from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult


class TicTacToe(GameModule):
    game_id = "agentic.tictactoe"
    display_name = "Tic-Tac-Toe"

    def __init__(self, size: int = 3, win_len: Optional[int] = None) -> None:
        self.size = size
        self.win_len = win_len or size

    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        n = int(kwargs.get("size", self.size))
        win = int(kwargs.get("win_len", self.win_len if n == self.size else n))
        return {
            "game_id": self.game_id if n == 3 else f"agentic.tictactoe_{n}",
            "size": n,
            "win_len": win,
            "board": ["."] * (n * n),
            "to_move": "p1",
            "ply": 0,
            "marks": {"p1": "X", "p2": "O"},
        }

    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        n = state["size"]
        out = []
        for i, c in enumerate(state["board"]):
            if c == ".":
                r, col = divmod(i, n)
                out.append(f"{r},{col}")
        return out

    def apply_move(self, state: dict[str, Any], move: str) -> MoveResult:
        try:
            r_s, c_s = move.replace(" ", "").split(",")
            r, c = int(r_s), int(c_s)
        except Exception:
            return MoveResult(ok=False, error="move must be row,col")
        n = state["size"]
        if not (0 <= r < n and 0 <= c < n):
            return MoveResult(ok=False, error="out of bounds")
        i = r * n + c
        board = list(state["board"])
        if board[i] != ".":
            return MoveResult(ok=False, error="occupied")
        side = state["to_move"]
        board[i] = state["marks"][side]
        nxt = "p2" if side == "p1" else "p1"
        new_state = {
            **state,
            "board": board,
            "to_move": nxt,
            "ply": state["ply"] + 1,
            "last_move": move,
        }
        return MoveResult(ok=True, move=move, state=new_state)

    def status(self, state: dict[str, Any]) -> GameResult:
        n, w = state["size"], state["win_len"]
        board = state["board"]

        def cell(r: int, c: int) -> str:
            return board[r * n + c]

        def line_win(cells: list[str]) -> Optional[str]:
            if len(cells) < w:
                return None
            for i in range(len(cells) - w + 1):
                chunk = cells[i : i + w]
                if chunk[0] != "." and all(x == chunk[0] for x in chunk):
                    return "p1" if chunk[0] == state["marks"]["p1"] else "p2"
            return None

        for r in range(n):
            winner = line_win([cell(r, c) for c in range(n)])
            if winner:
                return GameResult(True, f"{winner}_win", winner, "line")
        for c in range(n):
            winner = line_win([cell(r, c) for r in range(n)])
            if winner:
                return GameResult(True, f"{winner}_win", winner, "line")
        # diags
        for r in range(n):
            for c in range(n):
                for dr, dc in ((1, 1), (1, -1)):
                    cells = []
                    rr, cc = r, c
                    while 0 <= rr < n and 0 <= cc < n:
                        cells.append(cell(rr, cc))
                        rr += dr
                        cc += dc
                    winner = line_win(cells)
                    if winner:
                        return GameResult(True, f"{winner}_win", winner, "diag")
        if "." not in board:
            return GameResult(True, "draw", None, "full_board")
        return GameResult(False, "ongoing", None, "")

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        r = rng or random.Random()
        moves = self.legal_moves(state)
        # win if possible
        for m in moves:
            res = self.apply_move(state, m)
            if res.ok and self.status(res.state).winner_side == state["to_move"]:
                return m
        # block opponent
        opp = "p2" if state["to_move"] == "p1" else "p1"
        for m in moves:
            res = self.apply_move(state, m)
            if not res.ok:
                continue
            # if opponent would win next from each reply? simpler: try block
            for m2 in self.legal_moves(res.state):
                res2 = self.apply_move(res.state, m2)
                if res2.ok and self.status(res2.state).winner_side == opp:
                    return m  # occupy threat square by playing m first if m is the threat
        # center / corner bias
        n = state["size"]
        center = f"{n // 2},{n // 2}"
        if center in moves:
            return center
        return r.choice(moves)


class TicTacToe4(TicTacToe):
    game_id = "agentic.tictactoe_4"
    display_name = "Tic-Tac-Toe 4×4 (4-in-a-row)"

    def __init__(self) -> None:
        super().__init__(size=4, win_len=4)
