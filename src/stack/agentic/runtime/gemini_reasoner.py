"""
Google Gemini as a free *strategy amplifier* for Boardman agents.

Every builder ships a different mind. Gemini does not replace strategy —
it applies strategy_id / mind / strategy JSON you pass in.

Per-agent keys (preferred):
  GEMINI_API_KEY_NERO / GEMINI_API_KEY_RAJA / GEMINI_API_KEY_<SLUG>
Shared fallback (only if agent is on BOARDMAN_LLM_AGENTS allow-list):
  GEMINI_API_KEY / GOOGLE_API_KEY / GOOGLE_GENERATIVE_AI_API_KEY

Also:
  GEMINI_MODEL=gemini-2.0-flash
  BOARDMAN_LLM_REASONERS=asi,gemini   (or BOARDMAN_NERO_REASONERS)
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

from gaming.src.stack.agentic.runtime.agent_keys import (
    gemini_enabled_for,
    resolve_gemini_key,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def gemini_enabled(agent_id: str = "", name: str = "") -> bool:
    """True if this agent has a usable Gemini key (dedicated or shared+allow)."""
    if agent_id or name:
        return gemini_enabled_for(agent_id, name)
    # Legacy: any key present at all
    return bool(
        resolve_gemini_key("nero", "nero")
        or resolve_gemini_key("raja", "raja")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )


# Back-compat alias used by older hybrid_engine imports
def agent_uses_llm(agent_id: str = "", name: str = "") -> bool:
    from gaming.src.stack.agentic.runtime.agent_keys import llm_enabled_for

    return llm_enabled_for(agent_id, name)


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


def _generate(prompt: str, *, api_key: str, timeout: float) -> str:
    model = os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    q = urllib.parse.urlencode({"key": api_key})
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
    logger.info("[gemini] POST generateContent model=%s", model)
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
    agent_name: str = "Agent",
    agent_id: str = "",
    persona: str = "",
    strategy: Optional[dict[str, Any]] = None,
    mind: Any = None,
    openings: Optional[list[str]] = None,
    strategy_id: str = "",
    wallet_address: str = "",
    timeout_sec: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """
    Ask Gemini to pick a move that fits *this agent's* strategy.
    Builders pass different mind/strategy — Gemini amplifies that style, not a global bot.
    Enforces FIDE rule book via system prompt + legal_moves filter.
    """
    api_key = resolve_gemini_key(agent_id, agent_name)
    if not api_key:
        logger.info("[gemini] no key for agent_id=%s name=%s — skip", agent_id, agent_name)
        return None

    from gaming.src.stack.agentic.runtime.strategy_prompt import (
        build_system_prompt,
        build_user_prompt,
        strategy_from_mind,
    )
    from gaming.src.stack.agentic.chess.rule_book import is_legal_move, terminal_reason

    term = terminal_reason(board)
    if term:
        logger.info("[gemini] position terminal (%s) — no move", term)
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

    strat = strategy or strategy_from_mind(
        mind,
        agent_name=agent_name,
        agent_id=agent_id,
        openings=openings,
        strategy_id=strategy_id,
        strategy_notes=persona,
        wallet_address=wallet_address,
    )
    if wallet_address and not strat.get("wallet_address"):
        strat["wallet_address"] = wallet_address
    if agent_id and not strat.get("agent_id"):
        strat["agent_id"] = agent_id
    if persona and not strat.get("strategy_notes"):
        strat["strategy_notes"] = persona
    if persona and not strat.get("directive"):
        strat["directive"] = persona

    system = build_system_prompt(strat)
    user = build_user_prompt(
        fen=board.fen(),
        side="white" if board.turn == chess.WHITE else "black",
        legal_uci=legal_uci,
        legal_san=legal_san,
    )
    prompt = system + "\n\n" + user

    try:
        raw = _generate(prompt, api_key=api_key, timeout=timeout)
        logger.info("[gemini] ok agent=%s raw_len=%s", agent_name, len(raw))
    except Exception as exc:
        logger.warning("[gemini] generate failed agent=%s: %s", agent_name, exc)
        return None

    mv = _parse_move_from_text(raw, board)
    if mv is None or not is_legal_move(board, mv):
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
        "agent": strat.get("agent_name") or agent_name,
        "agent_id": agent_id or strat.get("agent_id") or "",
        "wallet_address": strat.get("wallet_address") or wallet_address,
        "strategy_id": strat.get("strategy_id") or "",
    }
