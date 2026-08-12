"""
Style-aware pure-Python chess engine for Boardman agents.

Priorities: opening book → development phase → short styled search.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional

import chess

from gaming.src.stack.agentic.chess.openings import book_move, pick_black_books


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# White-perspective PST (mirrored for black)
PST = {
    chess.PAWN: [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 27, 27, 10, 5, 5,
        0, 0, 0, 26, 26, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -25, -25, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    chess.KNIGHT: [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ],
    chess.BISHOP: [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ],
    chess.ROOK: [
        0, 0, 0, 5, 5, 0, 0, 0,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        5, 10, 10, 10, 10, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    chess.QUEEN: [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ],
    chess.KING: [
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        20, 20, 0, 0, 0, 0, 20, 20,
        20, 30, 10, 0, 0, 10, 30, 20,
    ],
}


def _pst(pt: chess.PieceType, sq: int, color: chess.Color) -> int:
    table = PST.get(pt)
    if not table:
        return 0
    idx = sq if color == chess.WHITE else chess.square_mirror(sq)
    return table[idx]


@dataclass
class Mind:
    depth: int = 2
    aggression: float = 1.0
    king_attack: float = 1.0
    fianchetto: float = 0.0
    hypermodern: float = 0.0
    counterpunch: float = 0.0
    central_pawns: float = 1.0
    mobility: float = 1.0
    development: float = 1.2
    randomness: float = 0.03
    mate_hunger: float = 1.0
    sacrifice_bias: float = 1.0
    draw_aversion: float = 1.0
    depth_bonus: int = 0
    book_ids_white: list[str] | None = None
    book_ids_black: list[str] | None = None
    black_book_primary: Optional[str] = None
    black_book_secondary: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Mind":
        return cls(
            depth=int(d.get("depth", 2)),
            aggression=float(d.get("aggression", 1.0)),
            king_attack=float(d.get("king_attack", 1.0)),
            fianchetto=float(d.get("fianchetto", 0.0)),
            hypermodern=float(d.get("hypermodern", 0.0)),
            counterpunch=float(d.get("counterpunch", 0.0)),
            central_pawns=float(d.get("central_pawns", 1.0)),
            mobility=float(d.get("mobility", 1.0)),
            development=float(d.get("development", 1.2)),
            randomness=float(d.get("randomness", 0.03)),
            mate_hunger=float(d.get("mate_hunger", 1.0)),
            sacrifice_bias=float(d.get("sacrifice_bias", 1.0)),
            draw_aversion=float(d.get("draw_aversion", 1.0)),
            depth_bonus=int(d.get("depth_bonus", 0)),
            book_ids_white=list(d.get("book_ids_white") or []),
            book_ids_black=list(d.get("book_ids_black") or []),
            black_book_primary=d.get("black_book_primary"),
            black_book_secondary=d.get("black_book_secondary"),
        )


class StyledEngine:
    def __init__(self, mind: Mind, *, rng: Optional[random.Random] = None) -> None:
        self.mind = mind
        self.rng = rng or random.Random()

    def choose_move(self, board: chess.Board) -> chess.Move:
        books = self._books_for(board)
        bm = book_move(board, books)
        if bm is not None:
            return bm

        # Opening phase: force sensible developing candidates
        if board.fullmove_number <= 14:
            dev = self._development_candidates(board)
            if dev:
                return self._best_among(board, dev, depth=1)

        moves = list(board.legal_moves)
        # Filter out suicidal king walks in middlegame
        filtered = [m for m in moves if not self._is_bad_king_walk(board, m)]
        if not filtered:
            filtered = moves
        return self._best_among(board, filtered, depth=max(1, min(self.mind.depth, 2)))

    def _is_bad_king_walk(self, board: chess.Board, mv: chess.Move) -> bool:
        piece = board.piece_at(mv.from_square)
        if not piece or piece.piece_type != chess.KING:
            return False
        if board.is_castling(mv):
            return False
        # Don't walk king before move 20 unless in check
        if board.fullmove_number <= 20 and not board.is_check():
            return True
        return False

    def _development_candidates(self, board: chess.Board) -> list[chess.Move]:
        color = board.turn
        back = 0 if color == chess.WHITE else 7
        cands: list[chess.Move] = []
        for mv in board.legal_moves:
            if board.is_castling(mv):
                cands.append(mv)
                continue
            piece = board.piece_at(mv.from_square)
            if not piece:
                continue
            # Develop N/B from back rank
            if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
                if chess.square_rank(mv.from_square) == back:
                    if chess.square_rank(mv.to_square) != back:
                        cands.append(mv)
            # Central pawn pushes
            if piece.piece_type == chess.PAWN:
                to_file = chess.square_file(mv.to_square)
                if to_file in (3, 4) and not board.is_capture(mv):
                    cands.append(mv)
            # Recaptures / captures of hanging pieces
            if board.is_capture(mv):
                cands.append(mv)
            # Style: fianchetto for Raja
            if self.mind.fianchetto > 0.8 and piece.piece_type == chess.BISHOP:
                home = chess.G2 if color == chess.WHITE else chess.G7
                if mv.to_square == home:
                    cands.append(mv)
            # Style: ...c5 / ...e6 breaks for Nero
            if self.mind.counterpunch > 0.8 and piece.piece_type == chess.PAWN:
                if color == chess.BLACK and mv.to_square in (chess.C5, chess.E5, chess.D5):
                    cands.append(mv)

        # Unique
        seen = set()
        out = []
        for m in cands:
            if m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def _best_among(self, board: chess.Board, moves: list[chess.Move], depth: int) -> chess.Move:
        best = moves[0]
        best_score = -1e18
        alpha, beta = -1e18, 1e18
        moves = sorted(moves, key=lambda m: self._order_key(board, m), reverse=True)
        for mv in moves[:28]:
            board.push(mv)
            score = -self._search(board, depth - 1, -beta, -alpha)
            board.pop()
            score += self._pre_move_bonus(board, mv)
            score += self.rng.uniform(-self.mind.randomness, self.mind.randomness) * 12
            if score > best_score:
                best_score = score
                best = mv
            alpha = max(alpha, score)
        return best

    def _pre_move_bonus(self, board: chess.Board, mv: chess.Move) -> float:
        bonus = 0.0
        piece = board.piece_at(mv.from_square)
        if not piece:
            return 0.0
        if board.is_castling(mv):
            bonus += 120 * self.mind.development
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            back = 0 if piece.color == chess.WHITE else 7
            if chess.square_rank(mv.from_square) == back and board.fullmove_number <= 12:
                bonus += 45 * self.mind.development
        if piece.piece_type == chess.QUEEN and board.fullmove_number <= 8:
            bonus -= 40
        if piece.piece_type == chess.ROOK and board.fullmove_number <= 12 and not board.is_capture(mv):
            bonus -= 30
        if piece.piece_type == chess.KING and not board.is_castling(mv) and board.fullmove_number <= 20:
            bonus -= 80
        # Fianchetto landing
        if self.mind.fianchetto and piece.piece_type == chess.BISHOP:
            if piece.color == chess.WHITE and mv.to_square == chess.G2:
                bonus += 40 * self.mind.fianchetto
            if piece.color == chess.BLACK and mv.to_square == chess.G7:
                bonus += 40 * self.mind.fianchetto
        # Hypermodern: Nf3/g3 patterns
        if self.mind.hypermodern and piece.piece_type == chess.KNIGHT:
            if mv.to_square in (chess.F3, chess.C3, chess.F6, chess.C6):
                bonus += 15 * self.mind.hypermodern
        if self.mind.counterpunch and piece.piece_type == chess.PAWN and piece.color == chess.BLACK:
            if mv.to_square in (chess.C5, chess.E6, chess.D5, chess.E5):
                bonus += 20 * self.mind.counterpunch
        return bonus

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

    def _order_key(self, board: chess.Board, mv: chess.Move) -> int:
        score = 0
        if board.is_capture(mv):
            victim = board.piece_at(mv.to_square)
            attacker = board.piece_at(mv.from_square)
            if victim and attacker:
                score += 10 * PIECE_VALUES.get(victim.piece_type, 0) - PIECE_VALUES.get(
                    attacker.piece_type, 0
                ) // 10
            score += 100
        if board.is_castling(mv):
            score += 95
        board.push(mv)
        if board.is_check():
            score += 80
        board.pop()
        return score

    def _search(self, board: chess.Board, depth: int, alpha: float, beta: float) -> float:
        if board.is_game_over() or depth <= 0:
            return self._evaluate(board)
        moves = list(board.legal_moves)
        moves.sort(key=lambda m: self._order_key(board, m), reverse=True)
        if len(moves) > 22:
            moves = moves[:22]
        for mv in moves:
            board.push(mv)
            score = -self._search(board, depth - 1, -beta, -alpha)
            board.pop()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _evaluate(self, board: chess.Board) -> float:
        if board.is_checkmate():
            return -50_000 + board.ply()
        if (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_fifty_moves()
            or board.is_repetition(3)
        ):
            return 0.0

        m = self.mind
        score = 0.0
        for sq, piece in board.piece_map().items():
            val = PIECE_VALUES[piece.piece_type] + _pst(piece.piece_type, sq, piece.color)
            score += val if piece.color == chess.WHITE else -val

            if m.fianchetto and piece.piece_type == chess.BISHOP:
                if piece.color == chess.WHITE and sq in (chess.G2, chess.B2):
                    score += 30 * m.fianchetto
                if piece.color == chess.BLACK and sq in (chess.G7, chess.B7):
                    score -= 30 * m.fianchetto

        score += self._dev_term(board, chess.WHITE) * m.development
        score -= self._dev_term(board, chess.BLACK) * m.development

        # King safety simple
        for color, sign in ((chess.WHITE, 1), (chess.BLACK, -1)):
            k = board.king(color)
            if k is None:
                continue
            if color == chess.WHITE and k in (chess.G1, chess.C1):
                score += 35 * sign
            if color == chess.BLACK and k in (chess.G8, chess.C8):
                score += 35 * sign
            if board.fullmove_number > 8:
                if color == chess.WHITE and k == chess.E1:
                    score -= 25 * sign
                if color == chess.BLACK and k == chess.E8:
                    score -= 25 * sign

        if m.counterpunch:
            for sq in board.pieces(chess.PAWN, chess.BLACK):
                if sq in (chess.C5, chess.E5, chess.D5):
                    score -= 14 * m.counterpunch

        return score if board.turn == chess.WHITE else -score

    def _dev_term(self, board: chess.Board, color: chess.Color) -> float:
        s = 0.0
        back = 0 if color == chess.WHITE else 7
        for pt in (chess.KNIGHT, chess.BISHOP):
            for sq in board.pieces(pt, color):
                if chess.square_rank(sq) != back:
                    s += 14
                else:
                    s -= 8
        return s
