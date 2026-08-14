"""Link a Lichess BOT token to a Boardman agent identity + wallet.

Lichess is the gym (play anyone, any clock). Boardman is the venue
(identity, USDC wallet, stake, spectator book). The token stays in .env;
agents.json only stores the public Lichess username and which env key holds
the secret.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# agent_id → env keys. Token never written to disk here.
LINKS: dict[str, dict[str, Any]] = {
    "agent_raja_kia_alekhine": {
        "token_env": (
            "LICHESS_RAJA_API_TOKEN",
            "LICHESS_API_TOKEN",
            "LICHESS_BOT_TOKEN",
        ),
        "user_env": ("RAJA_LICHESS_USER",),
        "default_user": "myrajafromboardman",
    },
    "agent_nero_sicilian_french": {
        "token_env": (
            "LICHESS_NERO_API_TOKEN",
            "LICHESS_API_TOKEN_NERO",
            "LICHESS_BOT_TOKEN_NERO",
            "NERO_LICHESS_API_TOKEN",
        ),
        "user_env": ("NERO_LICHESS_USER",),
        "default_user": "keniichii",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_for(agent_id: str, env: Optional[dict[str, str]] = None) -> str:
    spec = LINKS.get(agent_id) or {}
    src = env if env is not None else os.environ
    for key in spec.get("token_env") or ():
        val = (src.get(key) or "").strip()
        if val:
            return val
    return ""


def token_env_name(agent_id: str, env: Optional[dict[str, str]] = None) -> str:
    spec = LINKS.get(agent_id) or {}
    src = env if env is not None else os.environ
    for key in spec.get("token_env") or ():
        if (src.get(key) or "").strip():
            return key
    keys = spec.get("token_env") or ()
    return keys[0] if keys else ""


def username_for(agent_id: str, env: Optional[dict[str, str]] = None) -> str:
    spec = LINKS.get(agent_id) or {}
    src = env if env is not None else os.environ
    for key in spec.get("user_env") or ():
        val = (src.get(key) or "").strip()
        if val:
            return val
    return str(spec.get("default_user") or "")


def fetch_account(token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://lichess.org/api/account",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def public_identity(agent_id: str, *, live: bool = False, env: Optional[dict[str, str]] = None) -> dict[str, Any]:
    token = token_for(agent_id, env)
    user = username_for(agent_id, env)
    title = None
    if live and token:
        try:
            acct = fetch_account(token)
            user = str(acct.get("username") or user)
            title = acct.get("title")
        except Exception:
            logger.exception("[lichess-identity] account fetch failed for %s", agent_id)
    return {
        "username": user,
        "url": f"https://lichess.org/@/{user}" if user else "",
        "title": title,
        "token_env": token_env_name(agent_id, env),
        "linked": bool(token),
        "venue": "lichess_gym",
    }


def bind_agent(registry, agent_id: str, *, live: bool = False, env: Optional[dict[str, str]] = None) -> Optional[dict[str, Any]]:
    """Attach public Lichess identity to the Boardman agent (wallet unchanged)."""
    rec = registry.get_agent(agent_id)
    if not rec:
        return None
    ident = public_identity(agent_id, live=live, env=env)
    data = registry._agents()
    a = data["agents"].get(agent_id)
    if not a:
        return None
    a["lichess"] = ident
    rt = dict(a.get("runtime") or {})
    rt["lichess"] = {
        "username": ident["username"],
        "url": ident["url"],
        "token_env": ident["token_env"],
        "linked": ident["linked"],
    }
    a["runtime"] = rt
    a["updated_at"] = _now()
    data["agents"][agent_id] = a
    from gaming.src.stack.agentic.store import save_json
    from gaming.src.stack.agentic.registry import AGENTS_FILE

    save_json(AGENTS_FILE, data)
    return a


def bind_known_agents(registry, *, live: bool = False, env: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    out = []
    for agent_id in LINKS:
        rec = bind_agent(registry, agent_id, live=live, env=env)
        if rec:
            out.append(rec)
    return out
