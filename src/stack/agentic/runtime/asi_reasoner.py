"""
ASI:One (api.asi1.ai) as a free reasoning layer for Boardman agents.

Architecture (what we mean by "who does what"):

  Arc .............. money & settlement (USDC escrow, bankrolls) — not a brain
  Boardman Stack ... matchmaking, legal moves, stakes, spectators
  ASI:One .......... optional LLM reasoning (pick a move / strategy text)

Nero can use ASI to *think*; Arc is only needed if you dual-lock real testnet USDC.
Demo ledger mode needs zero Arc ETH/USDC.

Env (free tier key from https://asi1.ai developer docs):
  ASI_ONE_API_KEY=...          required for live ASI calls
  ASI_ONE_BASE_URL=https://api.asi1.ai/v1
  ASI_ONE_MODEL=asi1-mini      # free-leaning default; or asi1 / asi1-ultra
  BOARDMAN_ASI_AGENTS=nero     # comma agent name/id substrings that use ASI
  BOARDMAN_ASI_TIMEOUT_SEC=25
  BOARDMAN_ASI_FALLBACK_SF=1   # if ASI fails, fall back to Stockfish
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

import chess

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.asi1.ai/v1"
DEFAULT_MODEL = "asi1-mini"


def asi_enabled() -> bool:
    key = (os.getenv("ASI_ONE_API_KEY") or os.getenv("ASI_API_KEY") or "").strip()
    return bool(key)


def agent_uses_asi(agent_id: str = "", name: str = "") -> bool:
    """Only agents listed in BOARDMAN_ASI_AGENTS (default: nero) use ASI."""
    raw = (os.getenv("BOARDMAN_ASI_AGENTS") or "nero").strip().lower()
    if raw in {"*", "all", "1", "true"}:
        return True
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    hay = f"{agent_id} {name}".lower()
    return any(t in hay for t in tokens)


def _api_key() -> str:
    return (os.getenv("ASI_ONE_API_KEY") or os.getenv("ASI_API_KEY") or "").strip()


def _post_chat(messages: list[dict[str, str]], *, timeout: float) -> str:
    base = (os.getenv("ASI_ONE_BASE_URL") or DEFAULT_BASE).rstrip("/")
    model = os.getenv("ASI_ONE_MODEL") or DEFAULT_MODEL
    url = f"{base}/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.15,
        "max_tokens": 256,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
            "User-Agent": "BoardmanAgent/asi-reasoner",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    # OpenAI-compatible shape
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"ASI empty choices: {payload}")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if isinstance(content, list):
        # some APIs return content parts
        content = " ".join(
            str(p.get("text") if isinstance(p, dict) else p) for p in content
        )
    return str(content).strip()


def _parse_move_from_text(text: str, board: chess.Board) -> Optional[chess.Move]:
    """Extract a legal SAN or UCI move from model text."""
    if not text:
        return None
    # Prefer JSON {"move":"..."}
    try:
        # find first {...}
        m = re.search(r"\{[^{}]+\}", text)
        if m:
            obj = json.loads(m.group(0))
            cand = str(obj.get("move") or obj.get("uci") or obj.get("san") or "").strip()
            mv = _try_parse(board, cand)
            if mv:
                return mv
    except Exception:
        pass

    # UCI tokens
    for tok in re.findall(r"\b([a-h][1-8][a-h][1-8][qrbnQRBN]?)\b", text):
        mv = _try_parse(board, tok)
        if mv:
            return mv

    # SAN-ish tokens (longest first)
    cleaned = text.replace("`", " ").replace('"', " ").replace("'", " ")
    for tok in sorted(re.findall(r"[A-Za-z0-9\+#=x\-]+", cleaned), key=len, reverse=True):
        if len(tok) < 2 or tok.lower() in {"move", "json", "best", "play", "san", "uci"}:
            continue
        mv = _try_parse(board, tok)
        if mv:
            return mv
    return None


def _try_parse(board: chess.Board, cand: str) -> Optional[chess.Move]:
    if not cand:
        return None
    c = cand.strip().rstrip(".,;")
    try:
        return board.parse_uci(c.lower())
    except Exception:
        pass
    try:
        return board.parse_san(c)
    except Exception:
        pass
    return None


def reason_chess_move(
    board: chess.Board,
    *,
    agent_name: str = "Nero",
    persona: str = "",
    timeout_sec: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """
    Ask ASI:One for one legal move. Returns {move, san, uci, source, raw} or None.
    Free if you have an ASI_ONE_API_KEY (developer free tier). No Arc gas required.
    """
    if not asi_enabled():
        return None

    timeout = float(timeout_sec or os.getenv("BOARDMAN_ASI_TIMEOUT_SEC") or "25")
    legal = list(board.legal_moves)
    if not legal:
        return None

    legal_uci = [m.uci() for m in legal]
    legal_san = []
    for m in legal:
        try:
            legal_san.append(board.san(m))
        except Exception:
            legal_san.append(m.uci())

    persona = persona or (
        "You are Nero, a defensive chess grandmaster: solid structures, "
        "Sicilian/French ideas, punish overextension, convert endgames carefully."
    )
    system = (
        f"{persona}\n"
        "You only play legal chess moves. Reply with JSON only: "
        '{"move":"<UCI or SAN from the legal list>"}. '
        "No commentary outside JSON."
    )
    user = (
        f"FEN: {board.fen()}\n"
        f"Side to move: {'white' if board.turn == chess.WHITE else 'black'}\n"
        f"Legal UCI: {', '.join(legal_uci[:80])}"
        + (f" (+{len(legal_uci)-80} more)" if len(legal_uci) > 80 else "")
        + f"\nLegal SAN sample: {', '.join(legal_san[:40])}\n"
        "Pick the strongest practical move for this position."
    )

    try:
        raw = _post_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("[asi] chat failed: %s", exc)
        return None

    mv = _parse_move_from_text(raw, board)
    if mv is None or mv not in board.legal_moves:
        logger.warning("[asi] illegal or unparsed move from: %s", raw[:200])
        return None

    try:
        san = board.san(mv)
    except Exception:
        san = mv.uci()

    return {
        "move": mv,
        "san": san,
        "uci": mv.uci(),
        "source": "asi1.ai",
        "raw": raw[:500],
        "model": os.getenv("ASI_ONE_MODEL") or DEFAULT_MODEL,
        "agent": agent_name,
    }
