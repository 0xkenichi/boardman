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
