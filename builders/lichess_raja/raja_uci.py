#!/usr/bin/env python3
"""UCI adapter for Raja. Point lichess-bot at this file (protocol: uci).

This file speaks the public UCI protocol. It does not copy
https://github.com/lichess-bot-devs/lichess-bot (AGPL).

  engine:
    dir: "/path/to/boardman/builders/lichess_raja"
    name: "raja_uci.py"
    protocol: uci
    interpreter: python3
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pick(
    fen: str,
    *,
    wtime: int | None = None,
    btime: int | None = None,
    winc: int | None = None,
    binc: int | None = None,
    movetime: int | None = None,
) -> str:
    try:
        from gaming.src.stack.agentic.agents.raja.runtime import pick_move

        return pick_move(
            fen=fen,
            wtime_ms=wtime,
            btime_ms=btime,
            winc_ms=winc,
            binc_ms=binc,
            movetime_ms=movetime,
        )
    except Exception:
        pass
    try:
        from gaming.src.stack.agentic.chess import lichess_uci

        mv = lichess_uci.best_move(
            fen,
            wtime_ms=wtime,
            btime_ms=btime,
            winc_ms=winc,
            binc_ms=binc,
            movetime_ms=movetime,
        )
        if mv:
            return mv
    except Exception:
        pass
    import chess

    board = chess.Board(fen)
    legal = list(board.legal_moves)
    if not legal:
        return "(none)"
    return legal[0].uci()


def _int_after(parts: list[str], key: str) -> int | None:
    if key not in parts:
        return None
    i = parts.index(key)
    if i + 1 >= len(parts):
        return None
    try:
        return int(parts[i + 1])
    except ValueError:
        return None


def main() -> None:
    board_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    moves: list[str] = []
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        cmd = line.strip()
        if not cmd:
            continue
        if cmd == "uci":
            sys.stdout.write("id name Raja\n")
            sys.stdout.write("id author creator_raja_lab / Boardman\n")
            sys.stdout.write("uciok\n")
            sys.stdout.flush()
        elif cmd == "isready":
            sys.stdout.write("readyok\n")
            sys.stdout.flush()
        elif cmd == "ucinewgame":
            board_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
            moves = []
        elif cmd.startswith("position"):
            parts = cmd.split()
            if "fen" in parts:
                i = parts.index("fen")
                fen_bits = []
                j = i + 1
                while j < len(parts) and parts[j] != "moves":
                    fen_bits.append(parts[j])
                    j += 1
                board_fen = " ".join(fen_bits)
                moves = parts[parts.index("moves") + 1 :] if "moves" in parts else []
            elif "startpos" in parts:
                board_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
                moves = parts[parts.index("moves") + 1 :] if "moves" in parts else []
            else:
                moves = []
        elif cmd.startswith("go"):
            import chess

            board = chess.Board(board_fen)
            for mv in moves:
                board.push_uci(mv)
            parts = cmd.split()
            best = _pick(
                board.fen(),
                wtime=_int_after(parts, "wtime"),
                btime=_int_after(parts, "btime"),
                winc=_int_after(parts, "winc"),
                binc=_int_after(parts, "binc"),
                movetime=_int_after(parts, "movetime"),
            )
            sys.stdout.write(f"bestmove {best}\n")
            sys.stdout.flush()
        elif cmd.startswith("setoption"):
            continue
        elif cmd == "quit":
            try:
                from gaming.src.stack.agentic.chess import lichess_uci

                lichess_uci.close()
            except Exception:
                pass
            return
        elif cmd == "stop":
            continue


if __name__ == "__main__":
    os.environ.setdefault("RAJA_UCI_MOVETIME_MS", "400")
    main()
