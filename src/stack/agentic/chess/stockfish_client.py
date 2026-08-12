"""
Remote Stockfish clients for Boardman agent demo.

Primary:  https://chess-api.com/v1  (POST, multipv-friendly)
Fallback: https://stockfish.online/api/s/v2.php  (GET)
"""
from __future__ import annotations

import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

CHESS_API_URL = os.getenv("BOARDMAN_CHESS_API_URL", "https://chess-api.com/v1")
STOCKFISH_ONLINE_URL = os.getenv(
    "BOARDMAN_STOCKFISH_ONLINE_URL",
    "https://stockfish.online/api/s/v2.php",
)
# Default depth ~ IM level on chess-api docs (depth 12 ≈ 2350)
DEFAULT_DEPTH = int(os.getenv("BOARDMAN_SF_DEPTH", "12"))
DEFAULT_THINK_MS = int(os.getenv("BOARDMAN_SF_THINK_MS", "80"))
REQUEST_TIMEOUT = float(os.getenv("BOARDMAN_SF_TIMEOUT", "25"))


@dataclass
class EngineLine:
    uci: str
    san: Optional[str] = None
    eval_pawns: Optional[float] = None
    mate: Optional[int] = None
    depth: int = 0
    source: str = ""
    rank: int = 1  # multipv rank


@dataclass
class EngineResult:
    best: EngineLine
    lines: list[EngineLine]
    raw: dict[str, Any]
    source: str


def _http_json(method: str, url: str, body: Optional[dict] = None) -> dict[str, Any]:
    import json

    data = None
    headers = {"Accept": "application/json", "User-Agent": "BoardmanAgentArena/1.0"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _parse_uci(move: str) -> Optional[str]:
    if not move:
        return None
    m = move.strip().lower()
    # "bestmove e2e4 ponder c7c5"
    if m.startswith("bestmove"):
        parts = m.split()
        if len(parts) >= 2 and parts[1] != "(none)":
            return parts[1]
        return None
    if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", m):
        return m
    return None


def analyze_chess_api(
    fen: str,
    *,
    depth: int = DEFAULT_DEPTH,
    think_ms: int = DEFAULT_THINK_MS,
    variants: int = 1,
    searchmoves: Optional[str] = None,
) -> EngineResult:
    payload: dict[str, Any] = {
        "fen": fen,
        "depth": max(1, min(int(depth), 18)),
        "maxThinkingTime": max(10, min(int(think_ms), 100)),
        "variants": max(1, min(int(variants), 5)),
    }
    if searchmoves:
        payload["searchmoves"] = searchmoves

    data = _http_json("POST", CHESS_API_URL, payload)
    # Response may be a single object or list (progressive dumps) — normalize
    if isinstance(data, list):
        # Prefer last bestmove
        best_obj = None
        for item in data:
            if isinstance(item, dict) and item.get("type") in {"bestmove", "move"}:
                best_obj = item
        data = best_obj or (data[-1] if data else {})

    if not isinstance(data, dict):
        raise RuntimeError(f"chess-api unexpected response: {type(data)}")

    uci = _parse_uci(str(data.get("move") or data.get("lan") or ""))
    if not uci:
        raise RuntimeError(f"chess-api no move: {data}")

    eval_p = data.get("eval")
    try:
        eval_pawns = float(eval_p) if eval_p is not None else None
    except (TypeError, ValueError):
        eval_pawns = None

    mate = data.get("mate")
    try:
        mate_i = int(mate) if mate is not None else None
    except (TypeError, ValueError):
        mate_i = None

    line = EngineLine(
        uci=uci,
        san=data.get("san"),
        eval_pawns=eval_pawns,
        mate=mate_i,
        depth=int(data.get("depth") or depth),
        source="chess-api.com",
        rank=1,
    )
    lines = [line]

    # continuationArr first ply sometimes offers alternate ideas — keep as rank hints only
    cont = data.get("continuationArr") or []
    if cont and isinstance(cont, list):
        # not alternatives for current position; skip
        pass

    return EngineResult(best=line, lines=lines, raw=data, source="chess-api.com")


def analyze_stockfish_online(
    fen: str,
    *,
    depth: int = DEFAULT_DEPTH,
) -> EngineResult:
    # depth max 15 on stockfish.online docs
    d = max(1, min(int(depth), 15))
    q = urllib.parse.urlencode({"fen": fen, "depth": str(d)})
    url = f"{STOCKFISH_ONLINE_URL}?{q}"
    data = _http_json("GET", url)
    if not data.get("success"):
        raise RuntimeError(f"stockfish.online error: {data}")

    uci = _parse_uci(str(data.get("bestmove") or ""))
    if not uci:
        # sometimes bestmove is bare uci
        raw_bm = str(data.get("bestmove") or "")
        uci = _parse_uci(raw_bm.split()[-1] if raw_bm else "")
    if not uci:
        raise RuntimeError(f"stockfish.online no move: {data}")

    eval_pawns = None
    if data.get("evaluation") is not None:
        try:
            eval_pawns = float(data["evaluation"])
        except (TypeError, ValueError):
            pass

    mate = data.get("mate")
    mate_i = int(mate) if mate is not None else None

    line = EngineLine(
        uci=uci,
        eval_pawns=eval_pawns,
        mate=mate_i,
        depth=d,
        source="stockfish.online",
        rank=1,
    )
    return EngineResult(best=line, lines=[line], raw=data, source="stockfish.online")


def analyze(
    fen: str,
    *,
    depth: int = DEFAULT_DEPTH,
    think_ms: int = DEFAULT_THINK_MS,
    variants: int = 1,
    searchmoves: Optional[str] = None,
    prefer: Optional[str] = None,
) -> EngineResult:
    """
    Analyze position. prefer: 'chess-api' | 'stockfish-online' | None (auto).
    """
    order = []
    prefer = (prefer or os.getenv("BOARDMAN_SF_PROVIDER") or "chess-api").lower()
    if prefer in {"stockfish-online", "online", "stockfish.online"}:
        order = ["stockfish-online", "chess-api"]
    else:
        order = ["chess-api", "stockfish-online"]

    errors: list[str] = []
    for src in order:
        try:
            if src == "chess-api":
                return analyze_chess_api(
                    fen,
                    depth=depth,
                    think_ms=think_ms,
                    variants=variants,
                    searchmoves=searchmoves,
                )
            return analyze_stockfish_online(fen, depth=depth)
        except Exception as exc:
            errors.append(f"{src}: {exc}")
            logger.warning("[stockfish] %s failed: %s", src, exc)
            time.sleep(0.15)
    raise RuntimeError("all stockfish providers failed: " + " | ".join(errors))


def multipv_candidates(
    fen: str,
    candidate_ucis: list[str],
    *,
    depth: int = 10,
    think_ms: int = 60,
) -> list[EngineLine]:
    """
    Score specific UCI moves via chess-api searchmoves (one call per batch).
    Falls back to single best if batch fails.
    """
    cleaned = []
    seen = set()
    for u in candidate_ucis:
        u = (u or "").lower()
        if u and u not in seen:
            seen.add(u)
            cleaned.append(u)
    if not cleaned:
        return []

    try:
        # chess-api accepts space-separated searchmoves
        res = analyze_chess_api(
            fen,
            depth=depth,
            think_ms=think_ms,
            variants=1,
            searchmoves=" ".join(cleaned[:5]),
        )
        # API returns best among searchmoves
        return res.lines
    except Exception as exc:
        logger.warning("[stockfish] multipv batch failed: %s", exc)
        lines: list[EngineLine] = []
        for i, u in enumerate(cleaned[:3]):
            try:
                r = analyze_chess_api(
                    fen, depth=max(8, depth - 2), think_ms=think_ms, searchmoves=u
                )
                line = r.best
                line.rank = i + 1
                lines.append(line)
            except Exception:
                continue
        return lines
