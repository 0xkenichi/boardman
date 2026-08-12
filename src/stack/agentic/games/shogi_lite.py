"""
Shogi lite — 5×5 mini-shogi inspired rules for agents.

Pieces: King (K), Gold (G), Silver (S), Rook (R), Pawn (P).
No drops for v1. Promote S/P/R on last two ranks. Win by capturing the king.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult

N = 5


class ShogiLite(GameModule):
    game_id = "agentic.shogi_lite"
    display_name = "Shogi Lite (5×5)"

    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        board = [["."] * N for _ in range(N)]
        board[0] = list("RGSKP")
        board[1] = list("P....")
        board[3] = list("....p")
        board[4] = list("pksgr")
        return {
            "game_id": self.game_id,
            "size": N,
            "board": board,
            "to_move": "p1",
            "ply": 0,
        }

    def _side_of(self, ch: str) -> Optional[str]:
        if ch == ".":
            return None
        return "p1" if ch[-1].isupper() or (ch.startswith("+") and ch[1].isupper()) else "p2"

    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        side = state["to_move"]
        board = state["board"]
        moves: list[str] = []
        for r in range(N):
            for c in range(N):
                ch = board[r][c]
                if self._side_of(ch) != side:
                    continue
                for rr, cc in self._dests(board, r, c, ch, side):
                    moves.append(f"{r},{c}-{rr},{cc}")
        return moves

    def _dests(
        self, board: list[list[str]], r: int, c: int, ch: str, side: str
    ) -> list[tuple[int, int]]:
        # Normalize piece type
        promo = ch.startswith("+")
        base = ch.replace("+", "").upper()
        if promo and base in {"S", "P"}:
            base = "G"
        fwd = 1 if side == "p1" else -1
        out: list[tuple[int, int]] = []

        def empty_or_enemy(rr: int, cc: int) -> bool:
            if not (0 <= rr < N and 0 <= cc < N):
                return False
            o = self._side_of(board[rr][cc])
            return o is None or o != side

        if base == "K":
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if empty_or_enemy(rr, cc):
                        out.append((rr, cc))
        elif base == "G":
            for dr, dc in [
                (fwd, 0),
                (fwd, -1),
                (fwd, 1),
                (0, -1),
                (0, 1),
                (-fwd, 0),
            ]:
                rr, cc = r + dr, c + dc
                if empty_or_enemy(rr, cc):
                    out.append((rr, cc))
        elif base == "S":
            for dr, dc in [
                (fwd, 0),
                (fwd, -1),
                (fwd, 1),
                (-fwd, -1),
                (-fwd, 1),
            ]:
                rr, cc = r + dr, c + dc
                if empty_or_enemy(rr, cc):
                    out.append((rr, cc))
        elif base == "P":
            rr, cc = r + fwd, c
            if 0 <= rr < N and board[rr][cc] == ".":
                out.append((rr, cc))
        elif base == "R":
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                while 0 <= rr < N and 0 <= cc < N:
                    o = self._side_of(board[rr][cc])
                    if o is None:
                        out.append((rr, cc))
                    else:
                        if o != side:
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
        ch = board[r1][c1]
        board[r1][c1] = "."
        side = state["to_move"]
        # promote
        if not ch.startswith("+"):
            if side == "p1" and r2 >= 3 and ch in {"P", "S", "R"}:
                ch = "+" + ch
            if side == "p2" and r2 <= 1 and ch in {"p", "s", "r"}:
                ch = "+" + ch
        board[r2][c2] = ch
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
        has_k = any(c.replace("+", "") == "K" for c in flat)
        has_k2 = any(c.replace("+", "") == "k" for c in flat)
        if not has_k:
            return GameResult(True, "p2_win", "p2", "king_captured")
        if not has_k2:
            return GameResult(True, "p1_win", "p1", "king_captured")
        if not self.legal_moves(state):
            w = "p2" if state["to_move"] == "p1" else "p1"
            return GameResult(True, f"{w}_win", w, "no_moves")
        if state["ply"] >= 80:
            return GameResult(True, "draw", None, "max_plies")
        return GameResult(False, "ongoing", None, "")

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        r = rng or random.Random()
        moves = self.legal_moves(state)
        for m in moves:
            res = self.apply_move(state, m)
            if res.ok and self.status(res.state).done:
                return m
        scored = []
        for m in moves:
            a, b = m.split("-")
            r2, c2 = map(int, b.split(","))
            victim = state["board"][r2][c2]
            scored.append((0 if victim == "." else 5 + r.random(), m))
        scored.sort(reverse=True)
        return scored[0][1] if scored else r.choice(moves)
