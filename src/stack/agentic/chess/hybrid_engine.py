"""
Hybrid agent brain: opening repertoire → Stockfish → style pick → local fallback.

Designed so recorded demos look like real chess while agents keep distinct minds.
"""
from __future__ import annotations

import logging
import os
import random
from typing import Any, Optional

import chess

from gaming.src.stack.agentic.chess.engine import Mind, StyledEngine
from gaming.src.stack.agentic.chess.openings import book_move, pick_black_books
from gaming.src.stack.agentic.chess import stockfish_client as sf

logger = logging.getLogger(__name__)


def use_stockfish() -> bool:
    return os.getenv("BOARDMAN_USE_STOCKFISH", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class HybridEngine:
    """Persona-aware engine backed by remote Stockfish when available."""

    def __init__(
        self,
        mind: Mind,
        *,
        agent_id: str = "",
        rng: Optional[random.Random] = None,
        depth: Optional[int] = None,
        think_ms: Optional[int] = None,
    ) -> None:
        self.mind = mind
        self.agent_id = agent_id
        self.rng = rng or random.Random()
        base = depth if depth is not None else int(os.getenv("BOARDMAN_SF_DEPTH", "12"))
        # Mate-hungry attackers get real depth advantage (Raja beats solid peers)
        base += int(getattr(mind, "depth_bonus", 0) or 0)
        if getattr(mind, "mate_hunger", 1.0) >= 1.5:
            base = max(base, 14)
        if getattr(mind, "aggression", 1.0) >= 1.6:
            base = max(base, 13)
        # Defenders stay a step weaker so attack converts
        if getattr(mind, "archetype", "") == "defender_counter" or (
            getattr(mind, "counterpunch", 0) >= 1.3 and getattr(mind, "aggression", 1) < 1.1
        ):
            base = min(base, 10)
        self.depth = min(base, 16)  # API free tier soft-cap
        default_think = 110 if getattr(mind, "mate_hunger", 1.0) >= 1.5 else 80
        self.think_ms = think_ms if think_ms is not None else int(
            os.getenv("BOARDMAN_SF_THINK_MS", str(default_think))
        )
        self.local = StyledEngine(mind, rng=self.rng)
        self.last_source = "none"
        self.last_eval: Optional[float] = None
        self.is_attacker = (
            getattr(mind, "mate_hunger", 1.0) >= 1.4
            or getattr(mind, "aggression", 1.0) >= 1.5
            or "raja" in (agent_id or "").lower()
        )

    def choose_move(self, board: chess.Board) -> chess.Move:
        from gaming.src.stack.agentic.chess.mate_search import find_mate_in_1, find_mate_in_2

        # 0) Always take forced mate — viewers must see checkmates
        m1 = find_mate_in_1(board)
        if m1 is not None:
            self.last_source = "mate_in_1"
            self.last_eval = 99.0 if board.turn == chess.WHITE else -99.0
            return m1
        m2 = find_mate_in_2(board)
        if m2 is not None:
            self.last_source = "mate_in_2"
            self.last_eval = 90.0 if board.turn == chess.WHITE else -90.0
            return m2

        # 1) Opening book — short (identity only); SF fights the middlegame
        books = self._books_for(board)
        book_plies = int(os.getenv("BOARDMAN_BOOK_PLIES", "8"))
        bm = book_move(board, books, ply_limit=book_plies)
        if bm is not None:
            self.last_source = "opening_book"
            self.last_eval = None
            return bm

        # 2) Stockfish hybrid (aggressive conversion when winning)
        if use_stockfish():
            try:
                mv = self._stockfish_style_move(board)
                if mv is not None:
                    return mv
            except Exception as exc:
                logger.warning("[%s] stockfish path failed: %s", self.agent_id, exc)

        # 3) Local fallback — aggression-biased
        self.last_source = "local_styled"
        self.last_eval = None
        return self.local.choose_move(board)

    def _books_for(self, board: chess.Board) -> list[str]:
        if board.turn == chess.WHITE:
            return list(self.mind.book_ids_white or [])
        if self.mind.black_book_primary and self.mind.black_book_secondary:
            return pick_black_books(
                self.mind.black_book_primary,
                self.mind.black_book_secondary,
                board,
            )
        return list(self.mind.book_ids_black or [])

    def _stockfish_style_move(self, board: chess.Board) -> Optional[chess.Move]:
        from gaming.src.stack.agentic.chess.mate_search import prefer_forcing

        depth = self.depth
        # Attack is best defence: when under pressure, still hunt counterplay with depth
        fen = board.fen()
        think = max(self.think_ms, 120 if self.is_attacker else 90)
        result = sf.analyze(fen, depth=depth, think_ms=think, variants=1)
        self.last_eval = result.best.eval_pawns

        # API mate score
        if result.best.mate is not None:
            mate_n = int(result.best.mate)
            # positive mate → side to move mates if white POV convention varies; trust move
            best_mv = self._parse_legal(board, result.best.uci)
            if best_mv is not None:
                self.last_source = f"{result.source}+mate_{mate_n}"
                self.last_eval = 50.0 if mate_n > 0 else -50.0
                if board.turn == chess.BLACK:
                    self.last_eval = -self.last_eval
                return best_mv

        best_uci = result.best.uci
        best_mv = self._parse_legal(board, best_uci)
        if best_mv is None:
            self.last_source = result.source + ":invalid"
            return None

        ev = result.best.eval_pawns
        hunger = float(getattr(self.mind, "mate_hunger", 1.0) or 1.0)
        agg = float(getattr(self.mind, "aggression", 1.0) or 1.0)

        # Raja / attackers: force checks & captures more often
        # - when ahead: convert hard
        # - when equal/slightly worse: still attack (best defence)
        if self.is_attacker or agg >= 1.4:
            my_edge = 0.0
            if ev is not None:
                my_edge = ev if board.turn == chess.WHITE else -ev
            # threshold: attackers attack from -0.6 up; pure best when crushing
            if my_edge >= -0.6 or hunger >= 1.6:
                forcing: list[chess.Move] = []
                for mv in board.legal_moves:
                    if board.gives_check(mv) or board.is_capture(mv):
                        forcing.append(mv)
                # rank checks first
                forcing.sort(
                    key=lambda m: (2 if board.gives_check(m) else 0)
                    + (1 if board.is_capture(m) else 0),
                    reverse=True,
                )
                pick = prefer_forcing(board, forcing[:12]) if forcing else None
                if pick is not None and pick != best_mv:
                    tol = 1.15 if hunger >= 1.6 else 0.75  # how much eval to give for attack
                    try:
                        alt_res = sf.analyze(
                            fen,
                            depth=max(9, depth - 1),
                            think_ms=60,
                            searchmoves=pick.uci(),
                        )
                        alt_ev = alt_res.best.eval_pawns
                        if alt_ev is not None and ev is not None:
                            alt_edge = alt_ev if board.turn == chess.WHITE else -alt_ev
                            best_edge = ev if board.turn == chess.WHITE else -ev
                            if alt_edge >= best_edge - tol:
                                self.last_source = f"{result.source}+raja_attack"
                                self.last_eval = alt_ev
                                return pick
                        # checks always get a second look for mate_hunger
                        if board.gives_check(pick) and hunger >= 1.5:
                            self.last_source = f"{result.source}+check_hunt"
                            return pick
                    except Exception:
                        if board.gives_check(pick):
                            self.last_source = f"{result.source}+check"
                            return pick

        # Avoid repetition / soft draws when not losing
        if ev is not None:
            my_edge = ev if board.turn == chess.WHITE else -ev
            if my_edge >= -0.3 or getattr(self.mind, "draw_aversion", 1.0) >= 1.4:
                board.push(best_mv)
                rep = board.is_repetition(2) or board.can_claim_threefold_repetition()
                board.pop()
                if rep:
                    for mv in board.legal_moves:
                        if mv == best_mv:
                            continue
                        board.push(mv)
                        bad = board.is_repetition(2)
                        chk = board.is_check()
                        board.pop()
                        if not bad and (chk or board.is_capture(mv)):
                            self.last_source = f"{result.source}+anti_draw"
                            return mv

        self.last_source = result.source
        return best_mv

    def _thematic_alternative(
        self, board: chess.Board, best: chess.Move
    ) -> Optional[chess.Move]:
        """Pick a persona-flavored alternative when several sensible moves exist."""
        # Mostly play pure Stockfish after book — better for recorded demos
        p = 0.10 + 0.05 * float(self.mind.randomness or 0)
        if self.rng.random() > p:
            return None

        scored: list[tuple[float, chess.Move]] = []
        for mv in board.legal_moves:
            s = self._theme_score(board, mv)
            if s <= 0:
                continue
            scored.append((s, mv))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        # Top thematic that isn't the SF best
        for s, mv in scored[:6]:
            if mv != best:
                return mv
        return None

    def _theme_score(self, board: chess.Board, mv: chess.Move) -> float:
        piece = board.piece_at(mv.from_square)
        if not piece:
            return 0.0
        score = 0.0
        m = self.mind

        if board.is_castling(mv):
            score += 8 * m.development
        if m.fianchetto and piece.piece_type == chess.BISHOP:
            if piece.color == chess.WHITE and mv.to_square in (chess.G2, chess.B2):
                score += 10 * m.fianchetto
            if piece.color == chess.BLACK and mv.to_square in (chess.G7, chess.B7):
                score += 10 * m.fianchetto
        if m.hypermodern:
            if piece.piece_type == chess.KNIGHT and mv.to_square in (
                chess.F3,
                chess.C3,
                chess.F6,
                chess.C6,
            ):
                score += 4 * m.hypermodern
            if piece.piece_type == chess.PAWN and mv.to_square in (
                chess.D3,
                chess.E4,
                chess.C3,
            ):
                score += 3 * m.hypermodern
        if m.counterpunch and piece.color == chess.BLACK:
            if piece.piece_type == chess.PAWN and mv.to_square in (
                chess.C5,
                chess.E6,
                chess.D5,
                chess.E5,
                chess.C4,
            ):
                score += 6 * m.counterpunch
        if m.aggression and board.is_capture(mv):
            score += 2 * m.aggression
        board.push(mv)
        if board.is_check():
            score += 3 * m.aggression
        board.pop()

        # Discourage early queen thrashing / king walks
        if piece.piece_type == chess.QUEEN and board.fullmove_number <= 10:
            score -= 5
        if piece.piece_type == chess.KING and not board.is_castling(mv):
            score -= 12
        return score

    def _accept_alternative(
        self, board: chess.Board, best: chess.Move, alt: chess.Move
    ) -> bool:
        """Reject style alts that hang heavy material on a shallow local peek."""
        try:
            board.push(best)
            # opponent replies with capture-heavy local
            opp_best = self.local.choose_move(board)
            board.push(opp_best)
            mat_best = self._material_balance(board)
            board.pop()
            board.pop()

            board.push(alt)
            opp_alt = self.local.choose_move(board)
            board.push(opp_alt)
            mat_alt = self._material_balance(board)
            board.pop()
            board.pop()

            # From side-to-move before push perspective: higher is better for us after 1 move each
            # material_balance is white-centric; convert
            turn = board.turn
            if turn == chess.BLACK:
                mat_best, mat_alt = -mat_best, -mat_alt
            # Allow alt if within ~1.5 pawns of best line material
            return mat_alt >= mat_best - 80
        except Exception:
            return False

    def _material_balance(self, board: chess.Board) -> int:
        vals = {
            chess.PAWN: 100,
            chess.KNIGHT: 320,
            chess.BISHOP: 330,
            chess.ROOK: 500,
            chess.QUEEN: 900,
        }
        s = 0
        for p in board.piece_map().values():
            v = vals.get(p.piece_type, 0)
            s += v if p.color == chess.WHITE else -v
        return s

    def _parse_legal(self, board: chess.Board, uci: str) -> Optional[chess.Move]:
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            return None
        if mv in board.legal_moves:
            return mv
        # Try promotion default queen
        if len(uci) == 4:
            try:
                mv = chess.Move.from_uci(uci + "q")
                if mv in board.legal_moves:
                    return mv
            except ValueError:
                pass
        return None


def mind_from_agent(agent: dict[str, Any]) -> Mind:
    return Mind.from_dict(agent.get("mind") or {})
