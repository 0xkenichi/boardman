"""
Shared agent brain — the single winning move path for every chess agent.

Order:
  1. Mate-in-1 / mate-in-2 (always take)
  2. Authored opening book, weighted by learned line results (variety)
  3. LLM reasoners (if enabled for the agent)
  4. Local Stockfish multipv → persona-weighted pick inside the GM window
  5. Remote Stockfish APIs → styled fallback

The old runtime order (raw engine first) bypassed books and personas
entirely — every agent played the same deterministic line. This module is
that fix: personality and repertoire live on the main path.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import chess

from gaming.src.stack.agentic.chess.hybrid_engine import HybridEngine, Mind


def think_budget_ms(
    *,
    movetime_ms: Optional[int] = None,
    wtime_ms: Optional[int] = None,
    btime_ms: Optional[int] = None,
) -> int:
    """Clock-aware think budget: fast but not reckless. 150–1500 ms."""
    if movetime_ms:
        return max(150, min(int(movetime_ms), 1500))
    remaining = None
    if wtime_ms and btime_ms:
        # side to move unknown here; caller passes both — use the smaller as
        # a safe proxy (never overspend the tighter clock).
        remaining = min(int(wtime_ms), int(btime_ms))
    if remaining:
        return max(150, min(int(remaining * 0.05), 1500))
    return int(os.getenv("BOARDMAN_AGENT_THINK_MS", "600"))


def pick_with_brain(
    *,
    mind: Mind,
    agent_id: str,
    agent_name: str,
    fen: str,
    legal_moves: Optional[list[str]] = None,
    wtime_ms: Optional[int] = None,
    btime_ms: Optional[int] = None,
    winc_ms: Optional[int] = None,
    binc_ms: Optional[int] = None,
    movetime_ms: Optional[int] = None,
    wallet_address: str = "",
) -> tuple[str, str]:
    """Return (move, source). Move is UCI, or SAN when the caller's legal
    list uses SAN. Raises ValueError only for unrecoverable positions."""
    board = chess.Board(fen)
    think = think_budget_ms(
        movetime_ms=movetime_ms, wtime_ms=wtime_ms, btime_ms=btime_ms
    )
    engine = HybridEngine(
        mind,
        agent_id=agent_id,
        agent_name=agent_name,
        wallet_address=wallet_address,
        think_ms=think,
    )
    mv = engine.choose_move(board)
    source = getattr(engine, "last_source", None) or "brain"
    out = mv.uci()
    legal = list(legal_moves or [])
    if legal and out not in legal:
        san = board.san(mv)
        if san in legal:
            return san, source
        raise ValueError(f"{agent_name} move {out} not in legal_moves")
    return out, source
