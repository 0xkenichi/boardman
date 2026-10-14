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

import http.client
import ipaddress
import json
import logging
import os
import socket
import ssl
import time
from typing import Any, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- outbound guard
#
# Webhook URLs are owner-set, so every House → webhook call goes through
# post_json: the host is resolved once and the connection is pinned to that
# IP (no DNS rebinding), private / loopback / link-local / multicast /
# reserved targets are refused, redirects are never followed, the reply is
# capped and the whole exchange runs against one deadline.
#
# The House's own builder webhooks live on 127.0.0.1 (house.ensure_builder_
# webhooks: Raja :18761, Nero :18762, Sheila :18764, AFM demo managers
# :18771-18777); exactly those origins are trusted by default
# (BOARDMAN_TRUSTED_WEBHOOK_ORIGINS overrides the list).
# BOARDMAN_ALLOW_PRIVATE_WEBHOOKS=1 lifts the private block entirely — dev only.

MAX_WEBHOOK_RESPONSE_BYTES = 256 * 1024
_DEFAULT_TRUSTED_ORIGINS = ",".join(
    f"127.0.0.1:{port}" for port in (18761, 18762, 18764, *range(18771, 18778))
)


class WebhookBlocked(ValueError):
    """The webhook URL points somewhere the House must not call."""


def _allow_private() -> bool:
    return os.getenv("BOARDMAN_ALLOW_PRIVATE_WEBHOOKS", "").strip().lower() in {"1", "true", "yes", "on"}


def _trusted_origins() -> set[tuple[str, int]]:
    raw = os.getenv("BOARDMAN_TRUSTED_WEBHOOK_ORIGINS")
    if raw is None:
        raw = _DEFAULT_TRUSTED_ORIGINS
    out: set[tuple[str, int]] = set()
    for part in raw.split(","):
        host, _, port = part.strip().rpartition(":")
        if host and port.isdigit():
            out.add((host.strip("[]").lower(), int(port)))
    return out


def _is_public_ip(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_global
        and not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    )


def resolve_webhook_target(url: str) -> tuple[str, str, int, str]:
    """Validate ``url`` and pick the IP to connect to.

    Returns ``(scheme, host, port, ip)``. Raises WebhookBlocked for anything
    the House must not call."""
    parts = urlsplit((url or "").strip())
    scheme = (parts.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise WebhookBlocked("webhook must be http(s)")
    if parts.username or parts.password:
        raise WebhookBlocked("webhook URL must not carry credentials")
    host = (parts.hostname or "").lower()
    if not host:
        raise WebhookBlocked("webhook URL has no host")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise WebhookBlocked("webhook URL has a bad port") from exc
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WebhookBlocked("webhook host does not resolve") from exc
    ips: list[str] = []
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]
        if addr not in ips:
            ips.append(addr)
    if not ips:
        raise WebhookBlocked("webhook host does not resolve")
    if not (_allow_private() or (host, port) in _trusted_origins()):
        for addr in ips:
            if not _is_public_ip(ipaddress.ip_address(addr)):
                raise WebhookBlocked("webhook host resolves to a private or reserved address")
    return scheme, host, port, ips[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        # certificate is still verified against the hostname, not the IP
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def post_json(
    url: str,
    payload: Any,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout_sec: float = 8.0,
    log_tag: str = "webhook",
) -> Optional[Any]:
    """POST JSON to an owner-set webhook and return the decoded JSON reply.

    None on any refusal or failure (blocked target, non-2xx including any
    redirect, oversize or late reply, bad JSON). Errors are logged by kind
    only — the reply body is never reflected back."""
    deadline = time.monotonic() + max(0.1, float(timeout_sec))
    try:
        scheme, host, port, ip = resolve_webhook_target(url)
    except WebhookBlocked as exc:
        logger.warning("[%s] refused %s: %s", log_tag, host_of(url), exc)
        return None
    parts = urlsplit(url.strip())
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    body = json.dumps(payload).encode("utf-8")
    conn_cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    conn = conn_cls(host, port, ip, timeout=max(0.1, deadline - time.monotonic()))
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        resp = conn.getresponse()
        if not 200 <= resp.status < 300:
            logger.warning("[%s] %s answered HTTP %s", log_tag, host, resp.status)
            return None
        chunks: list[bytes] = []
        size = 0
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                logger.warning("[%s] %s missed the deadline", log_tag, host)
                return None
            if conn.sock is not None:
                conn.sock.settimeout(left)
            chunk = resp.read(min(65536, MAX_WEBHOOK_RESPONSE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_WEBHOOK_RESPONSE_BYTES:
                logger.warning("[%s] %s reply over %d bytes", log_tag, host, MAX_WEBHOOK_RESPONSE_BYTES)
                return None
        return json.loads(b"".join(chunks).decode("utf-8"))
    except Exception as exc:
        logger.warning("[%s] %s failed: %s", log_tag, host, type(exc).__name__)
        return None
    finally:
        conn.close()


def host_of(url: str) -> str:
    """Host part of a URL for logs (never the path, query or credentials)."""
    try:
        return urlsplit(url or "").hostname or "?"
    except ValueError:
        return "?"


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
    body = post_json(
        webhook_url,
        payload,
        headers={
            "User-Agent": "BoardmanAgentRuntime/1.0",
            "X-Boardman-Agent": str(agent.get("agent_id") or ""),
        },
        timeout_sec=timeout_sec,
        log_tag="webhook",
    )
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
