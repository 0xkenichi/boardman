"""
Webhook agent runtime — bring your own brain (OpenAI, Claude, custom server).

POST {webhook_url}
{
  "game_id": "agentic.connect4",
  "agent_id": "...",
  "state": { ... public state ... },
  "legal_moves": ["0","1",...],
  "to_move": "p1"
}

Response JSON:
  { "move": "3" }
  or { "move": "0,1-0,2" }
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)


def request_move(
    *,
    webhook_url: str,
    game_id: str,
    state: dict[str, Any],
    legal_moves: list[str],
    agent: dict[str, Any],
    timeout_sec: float = 8.0,
) -> Optional[str]:
    payload = {
        "game_id": game_id,
        "agent_id": agent.get("agent_id"),
        "name": agent.get("name"),
        "state": state,
        "legal_moves": legal_moves,
        "to_move": state.get("to_move"),
        "protocol": "boardman.agent.move.v1",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BoardmanAgentRuntime/1.0",
            "X-Boardman-Agent": str(agent.get("agent_id") or ""),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("[webhook] %s failed: %s", webhook_url, exc)
        return None

    if isinstance(body, dict):
        mv = body.get("move") or body.get("action")
        if mv is not None:
            return str(mv)
    return None


def webhook_url_for(agent: dict[str, Any]) -> str:
    rt = agent.get("runtime") or {}
    return str(rt.get("webhook_url") or agent.get("webhook_url") or "").strip()


def silo_pick_move(
    agent: dict[str, Any],
    *,
    game_id: str,
    fen: str,
    legal_moves: list[str],
    clocks: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """In-process fallback: load THAT builder's silo only. Never both."""
    aid = agent.get("agent_id") or ""
    if aid == "agent_raja_kia_alekhine":
        from gaming.src.stack.agentic.agents.raja.runtime import pick_move
    elif aid == "agent_nero_sicilian_french":
        from gaming.src.stack.agentic.agents.nero.runtime import pick_move
    else:
        return None
    return pick_move(
        game_id=game_id,
        fen=fen,
        legal_moves=legal_moves,
        **(clocks or {}),
    )


def clocks_kwargs_from_state(state: Optional[dict[str, Any]]) -> dict[str, int]:
    """Flat clock fields out of a webhook state dict, for silo fallback moves.

    Accepts {wtime_ms,btime_ms,winc_ms,binc_ms,movetime_ms} plus shared inc_ms.
    Non-positive / non-numeric values are dropped so pick_move defaults apply.
    """
    c = (state or {}).get("clocks") or {}
    if not isinstance(c, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("wtime_ms", "btime_ms", "winc_ms", "binc_ms", "movetime_ms"):
        v = c.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            out[key] = int(v)
    inc = c.get("inc_ms")
    if isinstance(inc, (int, float)) and not isinstance(inc, bool) and inc > 0:
        out.setdefault("winc_ms", int(inc))
        out.setdefault("binc_ms", int(inc))
    return out


def ask_agent_move(
    agent: dict[str, Any],
    *,
    game_id: str,
    state: dict[str, Any],
    legal_moves: list[str],
    timeout_sec: float = 25.0,
) -> Optional[str]:
    """House asks a builder agent for one legal move (webhook first)."""
    url = webhook_url_for(agent)
    if url:
        mv = request_move(
            webhook_url=url,
            game_id=game_id,
            state=state,
            legal_moves=legal_moves,
            agent=agent,
            timeout_sec=timeout_sec,
        )
        if mv:
            return mv
    return silo_pick_move(
        agent,
        game_id=game_id,
        fen=str((state or {}).get("fen") or ""),
        legal_moves=legal_moves,
        clocks=clocks_kwargs_from_state(state),
    )


def serve_builder_webhook(
    *,
    name: str,
    pick,
    host: str = "127.0.0.1",
    port: int,
) -> None:
    """Tiny HTTP server — what a builder deploys. POST /move, GET /health.

    ThreadingHTTPServer so a long Stockfish think never blocks /health —
    a hanging health check is how gyms/supervisors kill an otherwise fine bot.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] in {"/health", "/"}:
                extra: dict = {}
                if name.lower() in {"raja", "nero"}:
                    try:
                        from gaming.src.stack.agentic.chess import lichess_uci

                        extra["uci_ready"] = lichess_uci.engine_ready()
                        extra["uci_path"] = lichess_uci.find_stockfish()
                        if name.lower() == "raja":
                            from gaming.src.stack.agentic.agents.raja.runtime import LAST_SOURCE
                        else:
                            from gaming.src.stack.agentic.agents.nero.runtime import LAST_SOURCE
                        extra["last_source"] = LAST_SOURCE
                    except Exception:
                        extra["uci_ready"] = False
                body = json.dumps(
                    {"ok": True, "agent": name, "protocol": "boardman.agent.move.v1", **extra}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {}
            try:
                move = pick(body)
            except Exception as exc:
                logger.exception("[%s] pick failed", name)
                out = json.dumps({"error": str(exc)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
                return
            engine_label = "builder_silo"
            if name.lower() in {"raja", "nero"}:
                try:
                    if name.lower() == "raja":
                        from gaming.src.stack.agentic.agents.raja.runtime import LAST_SOURCE
                    else:
                        from gaming.src.stack.agentic.agents.nero.runtime import LAST_SOURCE
                    engine_label = LAST_SOURCE or "builder_silo"
                except Exception:
                    pass
            payload = json.dumps({"move": move, "agent": name, "engine": engine_label}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            logger.info("[%s] " + fmt, name, *args)

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"{name} builder webhook → http://{host}:{port}/move")
    httpd.serve_forever()
