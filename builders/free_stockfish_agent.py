#!/usr/bin/env python3
"""Free autonomous chess agent for Boardman.

Stockfish is GPL and free. This file is the whole agent.

  python3 builders/free_stockfish_agent.py
  # http://127.0.0.1:18763/move

Then register (House issues the key):

  curl -s -X POST "$BOARDMAN_API/api/stack/agentic/agents/register" \\
    -H "X-Rematch-Key: $BOARDMAN_STACK_KEY" \\
    -H "content-type: application/json" \\
    -d '{
      "agent_id":"agent_pike_stockfish",
      "name":"Pike",
      "creator_id":"creator_you",
      "game_ids":["agentic.chess_standard"],
      "webhook_url":"https://YOUR-HOST:18763/move"
    }'

Brain order: local `stockfish` binary → stockfish.online → first legal move.
No OpenAI/Anthropic key. No Boardman repo required in production — copy this file.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

NAME = os.getenv("PIKE_NAME") or "Pike"
PORT = int(os.getenv("PIKE_PORT") or "18763")
HOST = os.getenv("PIKE_HOST") or "0.0.0.0"


def _stockfish_bin() -> str:
    return (
        os.getenv("STOCKFISH_PATH")
        or shutil.which("stockfish")
        or ""
    )


def _uci_from_bin(fen: str, movetime_ms: int = 400) -> str:
    bin_path = _stockfish_bin()
    if not bin_path:
        return ""
    try:
        p = subprocess.Popen(
            [bin_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        assert p.stdin and p.stdout
        cmd = (
            f"uci\nisready\nposition fen {fen}\n"
            f"go movetime {movetime_ms}\n"
        )
        out, _ = p.communicate(cmd, timeout=4)
        p.kill()
        best = ""
        for line in (out or "").splitlines():
            if line.startswith("bestmove "):
                best = line.split()[1]
        return best if best and best != "(none)" else ""
    except Exception:
        return ""


def _uci_from_web(fen: str) -> str:
    q = urllib.parse.urlencode({"fen": fen, "depth": 10})
    url = "https://stockfish.online/api/s/v2.php?" + q
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BoardmanPike/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
        # { success, bestmove: "bestmove e2e4 ponder e7e5" } or similar
        raw = str(data.get("bestmove") or data.get("move") or "")
        if raw.startswith("bestmove "):
            raw = raw.split()[1]
        return raw.strip()
    except Exception:
        return ""


def pick(body: dict) -> str:
    legal = [str(x) for x in (body.get("legal_moves") or [])]
    fen = ""
    st = body.get("state") or {}
    if isinstance(st, dict):
        fen = str(st.get("fen") or "")
    if fen:
        mv = _uci_from_bin(fen) or _uci_from_web(fen)
        if mv and (not legal or mv in legal or any(x.startswith(mv) for x in legal)):
            return mv
    return legal[0] if legal else "0000"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in {"/", "/health", "/move"}:
            self._send(
                200,
                {
                    "ok": True,
                    "agent": NAME,
                    "protocol": "boardman.agent.move.v1",
                    "engine": "stockfish",
                    "local": bool(_stockfish_bin()),
                },
            )
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            body = {}
        self._send(200, {"move": pick(body), "agent": NAME, "engine": "stockfish"})

    def log_message(self, fmt: str, *args) -> None:
        print("[pike]", fmt % args)


def main() -> None:
    src = "local stockfish" if _stockfish_bin() else "stockfish.online (free HTTP)"
    print(f"{NAME} · {src}")
    print(f"webhook http://127.0.0.1:{PORT}/move")
    print("Copy this file. Point House webhook_url at it. No paid LLM.")
    HTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
