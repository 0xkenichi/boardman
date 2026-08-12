"""Go 9×9 — simplified Chinese scoring, multi-stone capture, no superko (simple ko)."""
from __future__ import annotations

import random
from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule, GameResult, MoveResult

N = 9


class Go9(GameModule):
    game_id = "agentic.go9"
    display_name = "Go 9×9"

    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "size": N,
            "board": [["."] * N for _ in range(N)],
            "to_move": "p1",  # p1 black
            "ply": 0,
            "passes": 0,
            "marks": {"p1": "B", "p2": "W"},
            "ko": None,  # forbidden single point after capture
            "captured": {"p1": 0, "p2": 0},
        }

    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        moves = ["pass"]
        side = state["to_move"]
        for r in range(N):
            for c in range(N):
                if state["board"][r][c] != ".":
                    continue
                mv = f"{r},{c}"
                if state.get("ko") == mv:
                    continue
                res = self.apply_move(state, mv, _probe=True)
                if res.ok:
                    moves.append(mv)
        return moves

    def _neighbors(self, r: int, c: int):
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < N and 0 <= cc < N:
                yield rr, cc

    def _group(self, board: list[list[str]], r: int, c: int) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        color = board[r][c]
        stack = [(r, c)]
        seen = {(r, c)}
        libs: set[tuple[int, int]] = set()
        while stack:
            cr, cc = stack.pop()
            for nr, nc in self._neighbors(cr, cc):
                if board[nr][nc] == ".":
                    libs.add((nr, nc))
                elif board[nr][nc] == color and (nr, nc) not in seen:
                    seen.add((nr, nc))
                    stack.append((nr, nc))
        return seen, libs

    def apply_move(self, state: dict[str, Any], move: str, _probe: bool = False) -> MoveResult:
        if move.strip().lower() == "pass":
            new_state = {
                **state,
                "to_move": "p2" if state["to_move"] == "p1" else "p1",
                "ply": state["ply"] + 1,
                "passes": state["passes"] + 1,
                "last_move": "pass",
                "ko": None,
                "board": [row[:] for row in state["board"]],
            }
            return MoveResult(ok=True, move="pass", state=new_state)

        try:
            r_s, c_s = move.replace(" ", "").split(",")
            r, c = int(r_s), int(c_s)
        except Exception:
            return MoveResult(ok=False, error="move row,col or pass")
        if not (0 <= r < N and 0 <= c < N):
            return MoveResult(ok=False, error="oob")
        if state["board"][r][c] != ".":
            return MoveResult(ok=False, error="occupied")
        if state.get("ko") == f"{r},{c}":
            return MoveResult(ok=False, error="ko")

        board = [row[:] for row in state["board"]]
        side = state["to_move"]
        stone = state["marks"][side]
        opp = state["marks"]["p2" if side == "p1" else "p1"]
        board[r][c] = stone
        captured_pts: list[tuple[int, int]] = []
        for nr, nc in self._neighbors(r, c):
            if board[nr][nc] == opp:
                grp, libs = self._group(board, nr, nc)
                if not libs:
                    for gr, gc in grp:
                        board[gr][gc] = "."
                        captured_pts.append((gr, gc))
        # suicide?
        grp, libs = self._group(board, r, c)
        if not libs:
            return MoveResult(ok=False, error="suicide")

        capt = dict(state["captured"])
        capt[side] = capt.get(side, 0) + len(captured_pts)
        ko = None
        if len(captured_pts) == 1 and len(grp) == 1:
            ko = f"{captured_pts[0][0]},{captured_pts[0][1]}"

        new_state = {
            **state,
            "board": board,
            "to_move": "p2" if side == "p1" else "p1",
            "ply": state["ply"] + 1,
            "passes": 0,
            "last_move": move,
            "ko": ko,
            "captured": capt,
        }
        return MoveResult(ok=True, move=move, state=new_state)

    def _area_score(self, state: dict[str, Any]) -> tuple[float, float]:
        board = state["board"]
        b_score = float(state["captured"].get("p1", 0))
        w_score = float(state["captured"].get("p2", 0)) + 6.5  # komi
        seen: set[tuple[int, int]] = set()
        for r in range(N):
            for c in range(N):
                if board[r][c] == "B":
                    b_score += 1
                elif board[r][c] == "W":
                    w_score += 1
                elif board[r][c] == "." and (r, c) not in seen:
                    # flood fill empty
                    stack = [(r, c)]
                    region = {(r, c)}
                    borders: set[str] = set()
                    while stack:
                        cr, cc = stack.pop()
                        for nr, nc in self._neighbors(cr, cc):
                            if board[nr][nc] == "." and (nr, nc) not in region:
                                region.add((nr, nc))
                                stack.append((nr, nc))
                            elif board[nr][nc] in {"B", "W"}:
                                borders.add(board[nr][nc])
                    seen |= region
                    if borders == {"B"}:
                        b_score += len(region)
                    elif borders == {"W"}:
                        w_score += len(region)
        return b_score, w_score

    def status(self, state: dict[str, Any]) -> GameResult:
        if state["passes"] >= 2 or state["ply"] >= 120:
            b, w = self._area_score(state)
            if b > w:
                return GameResult(True, "p1_win", "p1", f"score B{b:.1f}-W{w:.1f}")
            if w > b:
                return GameResult(True, "p2_win", "p2", f"score B{b:.1f}-W{w:.1f}")
            return GameResult(True, "draw", None, "score_equal")
        return GameResult(False, "ongoing", None, "")

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        r = rng or random.Random()
        moves = [m for m in self.legal_moves(state) if m != "pass"]
        if not moves:
            return "pass"
        # prefer center-ish + captures (probe capture count)
        def score(m: str) -> float:
            res = self.apply_move(state, m)
            if not res.ok:
                return -999
            cap = res.state["captured"][state["to_move"]] - state["captured"][state["to_move"]]
            rr, cc = map(int, m.split(","))
            center = -((rr - 4) ** 2 + (cc - 4) ** 2) * 0.1
            return cap * 10 + center + r.random()

        return max(moves, key=score)
