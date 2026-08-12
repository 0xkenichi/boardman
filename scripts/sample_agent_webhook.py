#!/usr/bin/env python3
"""
Minimal Boardman agent webhook — plug any brain behind this.

  python3 scripts/sample_agent_webhook.py
  # listens on :8765/move

Register:
  curl -X POST localhost:8000/api/stack/agentic/agents/register \\
    -H 'content-type: application/json' \\
    -d '{"agent_id":"agent_my_bot","name":"MyBot","creator_id":"me",
         "game_ids":["agentic.connect4"],"webhook_url":"http://127.0.0.1:8765/move"}'
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
        # Prefer center-ish for connect4 columns; else random legal
        move = None
        if legal and all(x.isdigit() for x in legal):
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
        print("[webhook]", fmt % args)


if __name__ == "__main__":
    port = 8765
    print(f"Boardman sample agent webhook on http://127.0.0.1:{port}/move")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
