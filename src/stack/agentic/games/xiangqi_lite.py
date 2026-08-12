"""
Xiangqi lite — 7×7 mini board for agents.

Pieces: General (G), Advisor (A), Chariot (R), Cannon (C), Soldier (S).
Win by capturing opponent general. Simplified palace (center files), river optional.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult

N = 7


class XiangqiLite(GameModule):
    game_id = "agentic.xiangqi_lite"
    display_name = "Xiangqi Lite (7×7)"

    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        board = [["."] * N for _ in range(N)]
        # p1 bottom (uppercase)
        board[0] = list("RACSGCA")
        board[2] = list("S.S.S.S")
        # p2 top (lowercase)
        board[6] = list("racsgca")
        board[4] = list("s.s.s.s")
        return {
            "game_id": self.game_id,
            "size": N,
            "board": board,
            "to_move": "p1",
            "ply": 0,
        }

    def _side(self, ch: str) -> Optional[str]:
        if ch == ".":
            return None
        return "p1" if ch.isupper() else "p2"

    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        side = state["to_move"]
        board = state["board"]
        moves = []
        for r in range(N):
            for c in range(N):
                ch = board[r][c]
                if self._side(ch) != side:
                    continue
                for rr, cc in self._dests(board, r, c, ch, side):
                    moves.append(f"{r},{c}-{rr},{cc}")
        return moves

    def _dests(self, board, r, c, ch, side):
        base = ch.upper()
        out = []

        def ok(rr, cc):
            if not (0 <= rr < N and 0 <= cc < N):
                return False
            o = self._side(board[rr][cc])
            return o is None or o != side

        if base == "G":
            # palace-ish center files 2-4, ranks 0-2 for p1, 4-6 for p2
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if ok(rr, cc) and 2 <= cc <= 4:
                    if side == "p1" and 0 <= rr <= 2:
                        out.append((rr, cc))
                    if side == "p2" and 4 <= rr <= 6:
                        out.append((rr, cc))
        elif base == "A":
            for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                rr, cc = r + dr, c + dc
                if ok(rr, cc) and 2 <= cc <= 4:
                    if side == "p1" and 0 <= rr <= 2:
                        out.append((rr, cc))
                    if side == "p2" and 4 <= rr <= 6:
                        out.append((rr, cc))
        elif base == "S":
            fwd = 1 if side == "p1" else -1
            if ok(r + fwd, c) and board[r + fwd][c] == ".":
                out.append((r + fwd, c))
            # after river (mid) can move sideways
            river = r >= 3 if side == "p1" else r <= 3
            if river:
                for dc in (-1, 1):
                    if ok(r, c + dc) and board[r][c + dc] != "." and self._side(board[r][c + dc]) != side:
                        out.append((r, c + dc))
                    elif ok(r, c + dc) and board[r][c + dc] == ".":
                        out.append((r, c + dc))
            if ok(r + fwd, c) and board[r + fwd][c] != "." and self._side(board[r + fwd][c]) != side:
                out.append((r + fwd, c))
        elif base == "R":
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                while 0 <= rr < N and 0 <= cc < N:
                    o = self._side(board[rr][cc])
                    if o is None:
                        out.append((rr, cc))
                    else:
                        if o != side:
                            out.append((rr, cc))
                        break
                    rr += dr
                    cc += dc
        elif base == "C":
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                jumped = False
                while 0 <= rr < N and 0 <= cc < N:
                    if board[rr][cc] == ".":
                        if not jumped:
                            out.append((rr, cc))
                    else:
                        if not jumped:
                            jumped = True
                        else:
                            if self._side(board[rr][cc]) != side:
                                out.append((rr, cc))
                            break
                    rr += dr
                    cc += dc
        return out

    def apply_move(self, state: dict[str, Any], move: str) -> MoveResult:
        if move not in self.legal_moves(state):
            return MoveResult(ok=False, error="illegal")
        a, b = move.split("-")
        r1, c1 = map(int, a.split(","))
        r2, c2 = map(int, b.split(","))
        board = [row[:] for row in state["board"]]
        board[r2][c2] = board[r1][c1]
        board[r1][c1] = "."
        side = state["to_move"]
        return MoveResult(
            ok=True,
            move=move,
            state={
                **state,
                "board": board,
                "to_move": "p2" if side == "p1" else "p1",
                "ply": state["ply"] + 1,
                "last_move": move,
            },
        )

    def status(self, state: dict[str, Any]) -> GameResult:
        flat = [c for row in state["board"] for c in row]
        if "G" not in flat:
            return GameResult(True, "p2_win", "p2", "general_captured")
        if "g" not in flat:
            return GameResult(True, "p1_win", "p1", "general_captured")
        if not self.legal_moves(state):
            w = "p2" if state["to_move"] == "p1" else "p1"
            return GameResult(True, f"{w}_win", w, "no_moves")
        if state["ply"] >= 100:
            return GameResult(True, "draw", None, "max_plies")
        return GameResult(False, "ongoing", None, "")

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        r = rng or random.Random()
        moves = self.legal_moves(state)
        for m in moves:
            res = self.apply_move(state, m)
            if res.ok and self.status(res.state).done:
                return m
        return r.choice(moves) if moves else "0,0-0,0"
