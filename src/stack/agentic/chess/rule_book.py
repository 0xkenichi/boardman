"""
Boardman Chess Rule Book — FIDE Laws of Chess (Articles 1–5 core play rules).

Authority: FIDE Laws of Chess (effective 1 Jan 2023 handbook chapter E.01).
Stack enforcement: python-chess / chess.js legal-move generation is the
runtime gate. Agents and LLMs MUST only propose moves from legal_moves.
They must NEVER invent illegal moves, ignore check, or break special rules.

This module is both:
  1) Human/agent readable rule text (RULE_BOOK_FULL, RULE_BOOK_COMPACT)
  2) Prompt injection for ASI / Gemini / any reasoner
  3) Soft validation helpers (hard legality is always chess.Board.legal_moves)
"""
from __future__ import annotations

from typing import Any, Optional

import chess

RULE_BOOK_VERSION = "fide-2023-boardman-v1"

# ── Compact block injected into every LLM system prompt ─────────────────────

RULE_BOOK_COMPACT = """
=== BOARDMAN CHESS RULE BOOK (MANDATORY — NEVER BREAK) ===
Source: FIDE Laws of Chess (Articles 1–5). You are bound by these rules.

1. BOARD & SETUP
- 8×8 board, ranks 1–8, files a–h. White bottom (rank 1) for White's perspective.
- White moves first. Players alternate turns. One legal move per turn.
- Starting: White Ra1 Nb1 Bc1 Qd1 Ke1 Bf1 Ng1 Rh1 + pawns a2–h2;
  Black Ra8…Kh8 + pawns a7–h7. Queen on her own color (d1/d8).

2. HOW PIECES MOVE (empty path unless knight)
- King: one square any direction (not into check). Special: castling (below).
- Queen: any number of squares vertically, horizontally, or diagonally.
- Rook: any number of squares vertically or horizontally.
- Bishop: any number of squares diagonally (stays on same color).
- Knight: L-shape 2+1; jumps over pieces. Only piece that jumps.
- Pawn: forward 1 (or 2 from start rank) on empty file; captures one square
  diagonally forward. Special: en passant, promotion (below).

3. CAPTURES
- Move onto opponent piece square (except pawns: diagonal only) removes it.
- You may never capture your own pieces.
- King cannot be captured; if a king would be captured, the prior move was illegal.

4. CHECK & CHECKMATE (Article 3.9 / 5.1)
- Check: your king is attacked. You MUST resolve check on this move by:
  (a) moving the king to a safe square, OR (b) capturing the attacker, OR
  (c) interposing a piece (not vs knight/pawn checks that cannot be blocked).
- You may NEVER leave your own king in check after your move.
- Checkmate: king in check and no legal way out → side to move loses. Game over.
- Do not continue after checkmate.

5. CASTLING (Article 3.8.2) — king + rook, one move
- King moves two squares toward a rook; that rook jumps to the square the king crossed.
- Conditions (ALL required):
  * King and that rook have not previously moved.
  * Squares between king and rook are empty.
  * King is not currently in check.
  * King does not pass through a square attacked by the opponent.
  * King does not end on a square attacked by the opponent.
- Kingside (O-O): White Ke1→g1, Rh1→f1; Black Ke8→g8, Rh8→f8.
- Queenside (O-O-O): White Ke1→c1, Ra1→d1; Black Ke8→c8, Ra8→d8.

6. EN PASSANT (Article 3.7.3.1–2)
- If opponent advances a pawn two squares from start and it lands beside your
  pawn, you may capture it as if it moved only one square — ONLY on the
  immediately following move. Capture lands on the passed-over square.

7. PROMOTION (Article 3.7.3.3–5)
- Pawn reaching last rank (8 for White, 1 for Black) MUST promote same move
  to queen, rook, bishop, or knight of the same color (usually queen).
- Choice is free (not limited to previously captured pieces). Effect is immediate.

8. ILLEGAL MOVES — FORBIDDEN
- Moving through occupied squares (except knight).
- Moving into check / leaving king in check.
- Castling when any castling condition fails.
- En passant after the reply window expired.
- Two moves in a row; moving opponent's pieces; removing your own king.
- Any move not in the provided legal_moves list for this position.

9. END OF GAME (Articles 5, 9)
- Win: checkmate, opponent resignation, or opponent flag (clock) if time controls apply.
- Draw: stalemate (no legal move, king not in check); dead position / insufficient
  material; agreement; threefold repetition (claim) / fivefold (auto);
  50-move rule (claim) / 75-move (auto); mutual perpetual patterns by agreement.
- Stalemate is a DRAW, not a win.

10. AGENT OBLIGATIONS ON BOARDMAN
- Output exactly ONE move chosen from the legal list (UCI or SAN).
- If the position is checkmate or stalemate for the side to move, do not invent a move.
- Prefer strategy ONLY among legal moves. Strategy never overrides legality.
- Wallet identity does not change chess rules; rules are universal.
=== END RULE BOOK ===
""".strip()


RULE_BOOK_FULL = """
# Boardman Chess Rule Book
## Based on the FIDE Laws of Chess (effective 1 January 2023)

**Version:** {version}
**Binding:** Every Boardman chess agent (Raja, Nero, third-party) must obey
these rules on every move. Runtime legality is enforced by the Stack using
standard chess libraries; LLM/engine suggestions that violate this book are
rejected.

---

## Article 1 — The nature and objectives of the game

1.1 Chess is played between two opponents who move their pieces alternately
    on a square board called a ‘chessboard’. The player with the white pieces
    commences the game. A player is said to ‘have the move’ when it is their
    turn to play.
1.2 The objective is to checkmate the opponent’s king. The player who
    checkmates wins. Leaving one’s own king in check, or moving into check,
    is illegal.
1.3 If the position is such that neither player can possibly checkmate, the
    game is drawn (dead position).

---

## Article 2 — The initial position

2.1 The chessboard is composed of an 8×8 grid of 64 equal squares alternately
    light and dark. The board is placed so that the nearest right-hand corner
    square is light (h1 for White).
2.2 At the beginning of the game White has: king e1, queen d1, rooks a1/h1,
    knights b1/g1, bishops c1/f1, pawns a2–h2.
    Black has: king e8, queen d8, rooks a8/h8, knights b8/g8, bishops c8/f8,
    pawns a7–h7.
2.3 The pieces are: king, queen, rook, bishop, knight, pawn.
2.4 The queen is placed on her own colour (white queen on light d1, black
    queen on dark d8).

---

## Article 3 — The moves of the pieces

### 3.1 General
It is not permitted to move a piece to a square occupied by a piece of the
same colour. If a piece moves to a square occupied by an opponent’s piece,
the latter is captured and removed from the chessboard as part of the same
move. A piece is said to attack an opponent’s piece if the piece could make
a capture on that square. A piece is considered to attack a square even if
that piece is pinned and cannot actually move to the square because it would
leave or place its own king in check.

### 3.2 Bishop
The bishop may move to any square along a diagonal on which it stands. It
may not leap over occupied squares.

### 3.3 Rook
The rook may move to any square along the file or the rank on which it
stands. It may not leap over occupied squares.

### 3.4 Queen
The queen may move to any square along the file, the rank or a diagonal on
which it stands. It may not leap over occupied squares.

### 3.5 Knight
The knight moves to one of the squares nearest to that on which it stands
but not on the same rank, file or diagonal (the familiar “L” shape: two
squares in one cardinal direction then one perpendicular). The knight is the
only piece that may leap over other pieces.

### 3.6 King (ordinary move)
The king may move to any adjoining square not attacked by one or more of the
opponent’s pieces.

### 3.8.2 Castling
Castling is a move of the king and either rook of the same colour along the
player’s first rank, counting as a single move of the king:
- The king is transferred two squares toward the rook; then that rook is
  transferred to the square the king has just crossed.
Castling is illegal if:
- the king has already moved, or
- the rook with which castling is to be effected has already moved, or
- there is any piece between the king and that rook, or
- the king is in check, or
- the king passes through a square attacked by an opponent’s piece, or
- the king would end in check.

Kingside castling: White O-O (e1–g1), Black O-O (e8–g8).
Queenside castling: White O-O-O (e1–c1), Black O-O-O (e8–c8).

### 3.7 Pawn
a) The pawn may move forward to the unoccupied square immediately in front
   of it on the same file.
b) On its first move the pawn may advance two squares along the same file
   provided both squares are unoccupied.
c) The pawn may move to a square occupied by an opponent’s piece diagonally
   in front of it on an adjacent file, capturing that piece.
d) En passant: A pawn attacking a square crossed by an opponent’s pawn which
   has advanced two squares in one move from its original square may capture
   this opponent’s pawn as though the latter had been moved only one square.
   This capture is only legal on the move following this advance.
e) Promotion: When a player, having the move, plays a pawn to the rank
   furthest from its starting position, they must exchange that pawn as part
   of the same move for a new queen, rook, bishop or knight of the same
   colour on the intended square of arrival. The choice is not restricted to
   pieces previously captured. The effect of the new piece is immediate.

### 3.9 Check
The king is said to be ‘in check’ if it is attacked by one or more of the
opponent’s pieces, even if such pieces are constrained from moving to the
king’s square because they would then leave or place their own king in check.
No piece can be moved that will expose its own king to check or leave its
own king in check.

---

## Article 4 — The act of moving the pieces (OTB / touch-move summary)

In over-the-board FIDE play, deliberately touching a piece may oblige a
player to move it (touch-move). On Boardman digital agents, the analogue is:
once a legal move is submitted and accepted by the Stack, it is final for
that turn. Agents must not retract legal moves after acceptance.

---

## Article 5 — Completion of the game

5.1.1 The game is won by the player who has checkmated the opponent’s king.
      This immediately ends the game.
5.1.2 The game is won by the player whose opponent declares they resign.
5.2.1 The game is drawn when the player to move has no legal move and their
      king is not in check (stalemate). This immediately ends the game.
5.2.2 The game is drawn when a position has arisen in which neither player
      can checkmate the opponent’s king with any series of legal moves (dead
      position).
5.2.3 The game may be drawn by agreement between the two players.
Additional draw rules commonly applied (Articles 9.2–9.6):
- Threefold repetition of position (claim) / fivefold (automatic draw)
- 50 moves by each side without capture or pawn move (claim) /
  75 moves (automatic draw)

---

## Time controls (Boardman agent matches)

Agents may play under negotiated clocks (bullet, blitz, rapid). Flagging
(running out of time) loses if the opponent has mating material under the
event’s time rules. Clock rules do not legalize an otherwise illegal move.

---

## Boardman Stack hard guarantees

1. Only moves in `board.legal_moves` / chess.js legal moves may be played.
2. LLM (Gemini, ASI:One, etc.) and Stockfish suggestions are filtered;
   illegal output is discarded and a legal fallback is used.
3. Checkmate and stalemate end the match; no further moves are accepted.
4. Each agent plays under its **wallet address** for stakes and settlement;
   chess legality is independent of wallets.
5. Strategy, openings, and personality may only choose among legal moves.

**Agents must never, ever break these rules.**
""".format(
    version=RULE_BOOK_VERSION
)


def rule_book_system_suffix() -> str:
    """Appended to every agent LLM system prompt."""
    return (
        "\n\n"
        + RULE_BOOK_COMPACT
        + "\n\nCRITICAL: Reply with one legal move only from the legal list. "
        "Never invent coordinates or SAN not in the list. Never break the rule book."
    )


def is_legal_move(board: chess.Board, move: chess.Move) -> bool:
    return move in board.legal_moves


def validate_uci(board: chess.Board, uci: str) -> Optional[chess.Move]:
    try:
        mv = chess.Move.from_uci((uci or "").strip().lower())
    except ValueError:
        return None
    if mv in board.legal_moves:
        return mv
    if len(uci) == 4:
        try:
            mv_q = chess.Move.from_uci(uci.lower() + "q")
            if mv_q in board.legal_moves:
                return mv_q
        except ValueError:
            pass
    return None


def terminal_reason(board: chess.Board) -> Optional[str]:
    """Return a short end reason if the game is over, else None."""
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient_material"
    if board.can_claim_fifty_moves() or board.is_fifty_moves():
        return "fifty_move"
    if board.is_repetition(5) or board.can_claim_threefold_repetition():
        return "repetition"
    if board.is_game_over():
        return "game_over"
    return None


def rule_book_meta() -> dict[str, Any]:
    return {
        "version": RULE_BOOK_VERSION,
        "authority": "FIDE Laws of Chess (2023)",
        "binding": "all Boardman chess agents",
        "enforcement": "python-chess / chess.js legal_moves + prompt injection",
        "compact_chars": len(RULE_BOOK_COMPACT),
    }
