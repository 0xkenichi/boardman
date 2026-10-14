"""Owner-set webhooks: the House must not be steerable at internal targets.

post_json resolves once and pins the connection, refuses private / loopback /
link-local / multicast / reserved IPs (unless the dev switch is on or the
origin is one of the House's own builder ports), never follows redirects,
caps the reply and never reflects the reply body.
"""
from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("BOARDMAN_ALLOW_PRIVATE_WEBHOOKS", raising=False)
    monkeypatch.delenv("BOARDMAN_TRUSTED_WEBHOOK_ORIGINS", raising=False)


def _fake_resolve(monkeypatch, ip: str):
    def fake(host, port, *a, **k):
        fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",  # link-local (cloud metadata)
        "100.64.0.1",  # CGNAT shared space
        "0.0.0.0",
        "224.0.0.1",  # multicast
        "240.0.0.1",  # reserved
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",  # v4-mapped loopback
    ],
)
def test_private_targets_are_refused(monkeypatch, ip):
    from gaming.src.stack.agentic.runtime.webhook import WebhookBlocked, resolve_webhook_target

    _fake_resolve(monkeypatch, ip)
    with pytest.raises(WebhookBlocked):
        resolve_webhook_target("https://brain.example.com/move")


def test_public_target_is_pinned(monkeypatch):
    from gaming.src.stack.agentic.runtime.webhook import resolve_webhook_target

    _fake_resolve(monkeypatch, "93.184.216.34")
    assert resolve_webhook_target("https://brain.example.com/move") == (
        "https",
        "brain.example.com",
        443,
        "93.184.216.34",
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://brain.example.com/",
        "ftp://brain.example.com/",
        "http://user:pw@brain.example.com/",
        "http:///nohost",
    ],
)
def test_bad_urls_are_refused(url):
    from gaming.src.stack.agentic.runtime.webhook import WebhookBlocked, resolve_webhook_target

    with pytest.raises(WebhookBlocked):
        resolve_webhook_target(url)


def test_house_builder_origins_are_trusted_but_nothing_else_local():
    from gaming.src.stack.agentic.runtime.webhook import WebhookBlocked, resolve_webhook_target

    assert resolve_webhook_target("http://127.0.0.1:18761/move")[3] == "127.0.0.1"
    assert resolve_webhook_target("http://127.0.0.1:18771")[3] == "127.0.0.1"
    with pytest.raises(WebhookBlocked):
        resolve_webhook_target("http://127.0.0.1:8000/api/stack/agentic/football/season/reset")
    with pytest.raises(WebhookBlocked):
        resolve_webhook_target("http://localhost:18761/move")


class _Server:
    def __init__(self, handler_body):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):  # noqa: N805
                n = int(inner.headers.get("Content-Length") or 0)
                inner.rfile.read(n)
                handler_body(inner)

            def log_message(inner, *args):  # noqa: N805
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/move"

    def __exit__(self, *exc):
        self.httpd.shutdown()


def _reply(inner, status: int, body: bytes, headers: dict | None = None):
    inner.send_response(status)
    for k, v in (headers or {}).items():
        inner.send_header(k, v)
    inner.send_header("Content-Length", str(len(body)))
    inner.end_headers()
    inner.wfile.write(body)


def test_local_webhook_blocked_without_dev_switch():
    from gaming.src.stack.agentic.runtime.webhook import post_json

    with _Server(lambda h: _reply(h, 200, b'{"move": "e2e4"}')) as url:
        assert post_json(url, {"x": 1}) is None


def test_dev_switch_allows_local_and_round_trips(monkeypatch):
    from gaming.src.stack.agentic.runtime.webhook import post_json

    monkeypatch.setenv("BOARDMAN_ALLOW_PRIVATE_WEBHOOKS", "1")
    with _Server(lambda h: _reply(h, 200, b'{"move": "e2e4"}')) as url:
        assert post_json(url, {"x": 1}) == {"move": "e2e4"}


def test_redirects_are_not_followed(monkeypatch):
    from gaming.src.stack.agentic.runtime.webhook import post_json

    monkeypatch.setenv("BOARDMAN_ALLOW_PRIVATE_WEBHOOKS", "1")
    hits = []

    def body(h):
        hits.append(h.path)
        _reply(h, 302, b"", {"Location": "http://169.254.169.254/latest/meta-data/"})

    with _Server(body) as url:
        assert post_json(url, {"x": 1}) is None
    assert hits == ["/move"]


def test_oversized_reply_is_dropped(monkeypatch):
    from gaming.src.stack.agentic.runtime.webhook import MAX_WEBHOOK_RESPONSE_BYTES, post_json

    monkeypatch.setenv("BOARDMAN_ALLOW_PRIVATE_WEBHOOKS", "1")
    big = json.dumps({"move": "x" * (MAX_WEBHOOK_RESPONSE_BYTES + 10)}).encode()
    with _Server(lambda h: _reply(h, 200, big)) as url:
        assert post_json(url, {"x": 1}) is None


def test_reply_body_is_not_logged(monkeypatch, caplog):
    from gaming.src.stack.agentic.runtime.webhook import post_json

    monkeypatch.setenv("BOARDMAN_ALLOW_PRIVATE_WEBHOOKS", "1")
    secret = b"INTERNAL-SECRET-PAGE"
    with _Server(lambda h: _reply(h, 500, secret)) as url:
        with caplog.at_level("WARNING"):
            assert post_json(url, {"x": 1}) is None
    with _Server(lambda h: _reply(h, 200, secret)) as url:  # not JSON
        with caplog.at_level("WARNING"):
            assert post_json(url, {"x": 1}) is None
    assert "INTERNAL-SECRET-PAGE" not in caplog.text


def test_request_move_and_matchday_ask_use_the_guard(monkeypatch):
    """Both House → webhook paths refuse an internal target."""
    from gaming.src.stack.agentic.games.football_managers import manager_protocol as mp
    from gaming.src.stack.agentic.runtime import webhook as wh

    _fake_resolve(monkeypatch, "169.254.169.254")
    agent = {"agent_id": "agent_x", "runtime": {"webhook_url": "http://evil.example.com/"}}
    assert wh.request_move(webhook_url="http://evil.example.com/", game_id="g", state={}, legal_moves=["a"], agent=agent) is None
    assert mp.request_matchday_plan(agent, {"ask": 1}) is None
    assert mp.request_press_conference_answer(agent, {"ask": 1}) is None
