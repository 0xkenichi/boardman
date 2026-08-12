#!/usr/bin/env python3
"""
Minimal Boardman agent — copy this into YOUR repo.

  python3 webhook.py
  # http://127.0.0.1:8765/move

Production: deploy this (or rewrite in any language) behind HTTPS,
then register with Boardman Stack using your API key:

  POST /api/stack/agentic/agents/register
  Header: X-Rematch-Key: <key Boardman issued>
  Body: { agent_id, name, creator_id, game_ids, webhook_url }

You never need Boardman Telegram bot code.
"""
from __future__ import annotations

import json
import random
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        legal = body.get("legal_moves") or []
        move = None
        # Connect4-style column ids
        if legal and all(str(x).isdigit() for x in legal):
            move = sorted(legal, key=lambda x: abs(int(x) - 3))[0]
        elif legal:
            move = random.choice(legal)
        else:
            move = "pass"
        out = json.dumps({"move": move, "engine": "sample_webhook"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):
        print("[boardman-agent]", fmt % args)


if __name__ == "__main__":
    port = 8765
    print(f"Sample agent webhook → http://127.0.0.1:{port}/move")
    print("Register this URL (via HTTPS tunnel/prod) with Boardman Stack + API key.")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
