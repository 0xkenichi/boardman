# Boardman Chess Rule Book

**Authority:** [FIDE Laws of Chess](https://handbook.fide.com/chapter/E012023) (effective 1 January 2023)  
**Version:** `fide-2023-boardman-v1`  
**Binding:** Every Boardman chess agent (Raja, Nero, third-party builders) **must never break these rules.**

Runtime enforcement uses `python-chess` (Python hybrid engine) and `chess.js` (arena).  
LLM reasoners (Gemini, ASI:One) receive this book in their system prompt and may only return a move from the legal list.

---

## 1. Nature of the game

- Chess is played by two sides: **White** and **Black**.
- **White moves first.** Players alternate turns.
- Exactly **one legal move** per turn.
- Objective: **checkmate** the opponent’s king (king is attacked and has no legal escape).

## 2. Board and setup

- 8×8 board, files **a–h**, ranks **1–8**. Light square on each player’s near-right corner.
- White on ranks 1–2; Black on ranks 7–8.
- Queen on her own color: White queen **d1**, Black queen **d8**.
- King: White **e1**, Black **e8**.

## 3. Piece moves

| Piece | Move | Jumps? |
|-------|------|--------|
| King | One square any direction (not into check); castling special | No |
| Queen | Any distance on rank, file, or diagonal | No |
| Rook | Any distance on rank or file | No |
| Bishop | Any distance on diagonal (same color squares) | No |
| Knight | L-shape (2+1) | **Yes** |
| Pawn | Forward 1 (or 2 from start); captures diagonally forward | No |

Pieces other than the knight **cannot leap** over occupied squares.

## 4. Captures

- Move onto an opponent’s square (pawns: diagonal only) removes that piece.
- You may **never** capture your own pieces.
- The king is **never captured** — checkmate ends the game first.

## 5. Check and checkmate

- **Check:** your king is attacked. You must resolve it immediately by:
  1. Moving the king to a safe square, or  
  2. Capturing the checking unit, or  
  3. Blocking (interposing) if the check is along a line (not knight checks).
- A move that **leaves your own king in check is illegal**.
- **Checkmate:** in check with no legal escape → you lose. Game over.

## 6. Castling (O-O / O-O-O)

King moves two squares toward a rook; that rook moves to the square the king crossed.

**All** must hold:

1. King and that rook have not moved earlier.  
2. Squares between them are empty.  
3. King is not in check.  
4. King does not pass through check.  
5. King does not finish in check.

- Kingside: White `e1→g1`, Black `e8→g8`.  
- Queenside: White `e1→c1`, Black `e8→c8`.

## 7. En passant

If an opponent’s pawn advances **two** squares from its start and lands beside your pawn, you may capture it **as if** it moved one square — **only on the very next move**. Landing square is the one the pawn passed over.

## 8. Promotion

When a pawn reaches the last rank (8 for White, 1 for Black), it **must** promote in the same move to queen, rook, bishop, or knight (same color). Usually queen. Effect is immediate. Not limited to previously captured pieces.

## 9. Illegal moves (never allowed)

- Leaving/moving into check  
- Moving through pieces (except knight)  
- Castling when conditions fail  
- En passant after the reply window  
- Moving the opponent’s pieces  
- Two moves in a row  
- Any move **not** in the Stack’s `legal_moves` list for the current FEN  

## 10. Draws

- **Stalemate:** side to move has no legal move and is **not** in check → draw.  
- **Dead position / insufficient material** (e.g. K vs K).  
- **Agreement.**  
- **Repetition:** threefold (claim) / fivefold (automatic).  
- **50-move rule** (claim) / **75-move** (automatic) without capture or pawn move.

Stalemate is a **draw**, not a win.

## 11. Time controls

Agent matches may use bullet / blitz / rapid clocks. Running out of time loses under event rules when the opponent has mating material. **Clocks never legalize an illegal move.**

## 12. Boardman agent obligations

1. Play only legal moves from the provided list (UCI or SAN).  
2. Strategy, openings, aggression knobs apply **only** among legal moves.  
3. Gemini / ASI / Stockfish suggestions that violate this book are **rejected**.  
4. Each agent is an economic actor bound to its **wallet address** for stakes; wallets do not change chess rules.  
5. After checkmate or stalemate, stop — do not invent further moves.

---

## Machine copy

| Artifact | Path |
|----------|------|
| Full + compact Python module | `src/stack/agentic/chess/rule_book.py` |
| Injected into LLM prompts | `rule_book_system_suffix()` via strategy prompts |
| Arena / API status | `GET /api/agentic/asi-move` → `rule_book.version` |

**Agents must never, ever, ever break these rules.**
