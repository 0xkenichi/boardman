"""
Google Gemini as a free reasoning layer for Boardman agents (Nero by default).

Env (free key from https://aistudio.google.com/apikey):
  GEMINI_API_KEY=...                 or GOOGLE_API_KEY / GOOGLE_GENERATIVE_AI_API_KEY
  GEMINI_MODEL=gemini-2.0-flash      free-tier friendly
  BOARDMAN_NERO_REASONERS=asi,gemini order of LLM attempts (then Stockfish)
  BOARDMAN_ASI_AGENTS=nero           which agents use LLM layers
  BOARDMAN_GEMINI_TIMEOUT_SEC=25
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

import chess

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def gemini_enabled() -> bool:
    return bool(_api_key())


def _api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        or ""
    ).strip()


def agent_uses_llm(agent_id: str = "", name: str = "") -> bool:
    """Same agent allow-list as ASI (BOARDMAN_ASI_AGENTS, default nero)."""
    raw = (os.getenv("BOARDMAN_ASI_AGENTS") or "nero").strip().lower()
    if raw in {"*", "all", "1", "true"}:
        return True
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    hay = f"{agent_id} {name}".lower()
    return any(t in hay for t in tokens)


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


def _parse_move_from_text(text: str, board: chess.Board) -> Optional[chess.Move]:
    if not text:
        return None
    try:
        m = re.search(r"\{[^{}]+\}", text)
        if m:
            obj = json.loads(m.group(0))
            cand = str(obj.get("move") or obj.get("uci") or obj.get("san") or "").strip()
            mv = _try_parse(board, cand)
            if mv:
                return mv
    except Exception:
        pass
    for tok in re.findall(r"\b([a-h][1-8][a-h][1-8][qrbnQRBN]?)\b", text):
        mv = _try_parse(board, tok)
        if mv:
            return mv
    cleaned = text.replace("`", " ").replace('"', " ").replace("'", " ")
    for tok in sorted(re.findall(r"[A-Za-z0-9\+#=x\-]+", cleaned), key=len, reverse=True):
        if len(tok) < 2 or tok.lower() in {"move", "json", "best", "play", "san", "uci"}:
            continue
        mv = _try_parse(board, tok)
        if mv:
            return mv
    return None


def _generate(prompt: str, *, timeout: float) -> str:
    model = os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    key = _api_key()
    q = urllib.parse.urlencode({"key": key})
    url = f"{API_BASE}/models/{model}:generateContent?{q}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": 128,
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "BoardmanAgent/gemini-reasoner"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    cands = payload.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini empty candidates: {payload}")
    parts = ((cands[0].get("content") or {}).get("parts")) or []
    texts = [str(p.get("text") or "") for p in parts if isinstance(p, dict)]
    return "\n".join(texts).strip()


def reason_chess_move(
    board: chess.Board,
    *,
    agent_name: str = "Nero",
    persona: str = "",
    timeout_sec: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Ask Gemini for one legal move. Free API key; no Arc gas."""
    if not gemini_enabled():
        return None

    timeout = float(timeout_sec or os.getenv("BOARDMAN_GEMINI_TIMEOUT_SEC") or "25")
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
        "Sicilian/French ideas, punish overextension."
    )
    prompt = (
        f"{persona}\n"
        'Reply with JSON only: {"move":"<UCI or SAN from the legal list>"}. No other text.\n\n'
        f"FEN: {board.fen()}\n"
        f"Side to move: {'white' if board.turn == chess.WHITE else 'black'}\n"
        f"Legal UCI: {', '.join(legal_uci[:80])}\n"
        f"Legal SAN sample: {', '.join(legal_san[:40])}\n"
        "Pick the strongest practical defensive/counterpunching move."
    )

    try:
        raw = _generate(prompt, timeout=timeout)
    except Exception as exc:
        logger.warning("[gemini] generate failed: %s", exc)
        return None

    mv = _parse_move_from_text(raw, board)
    if mv is None or mv not in board.legal_moves:
        logger.warning("[gemini] illegal or unparsed move from: %s", raw[:200])
        return None

    try:
        san = board.san(mv)
    except Exception:
        san = mv.uci()

    return {
        "move": mv,
        "san": san,
        "uci": mv.uci(),
        "source": "gemini",
        "raw": raw[:500],
        "model": os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
        "agent": agent_name,
    }
