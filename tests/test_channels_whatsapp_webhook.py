"""WhatsApp webhook: verify handshake, signatures (good, bad, replayed),
payload parsing, the Graph client's request shapes, templates and notify."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gaming.src.channels.core.identity.repo import Identity, utcnow
from gaming.src.channels.core.messages import Option
from gaming.src.channels.core.notify import Notice, NotificationService
from gaming.src.channels.fake.adapter import RecordingDeliverer
from gaming.src.channels.whatsapp import templates
from gaming.src.channels.whatsapp.client import GraphClient, HttpResponse
from gaming.src.channels.whatsapp.parse import parse
from gaming.src.channels.whatsapp.signature import sign, verify_signature
from tests.channels_fixtures import wa_user, world  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SECRET = "test-app-secret"
U = "2348011112222"


def _payload(msg_id="wamid.A1", text="balance", ts=None, **extra):
    import time

    m = {"from": U, "id": msg_id, "timestamp": str(ts or int(time.time())), "type": "text",
         "text": {"body": text}}
    m.update(extra)
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "2348000000000", "phone_number_id": "PNID"},
            "contacts": [{"wa_id": U, "profile": {"name": "Ada"}}],
            "messages": [m]}}]}]}


class _Recorder:
    def __init__(self):
        self.sent = []

    def send(self, to, message):
        self.sent.append((to, message))
        return f"wamid.OUT{len(self.sent)}"


@pytest.fixture
def app(world, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ENABLED", "1")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    rec = _Recorder()
    monkeypatch.setattr("gaming.src.channels.whatsapp.client.client_from_env", lambda transport=None: rec)
    from gaming.src.backend.main import create_app

    client = TestClient(create_app())
    client.recorder = rec
    return client


def _post(app, body: bytes, sig=None):
    headers = {"Content-Type": "application/json"}
    if sig is not False:
        headers["X-Hub-Signature-256"] = sig or sign(SECRET, body)
    return app.post("/webhooks/whatsapp", content=body, headers=headers)


def test_webhook_not_mounted_by_default(world):
    from gaming.src.backend.main import create_app

    r = TestClient(create_app()).get("/webhooks/whatsapp", params={"hub.mode": "subscribe"})
    assert r.status_code in (404, 405)


def test_verify_handshake(app):
    ok = app.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                               "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    bad = app.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                "hub.challenge": "1"})
    assert bad.status_code == 403


def test_good_signature_is_processed(app, world):
    wa_user(world.repo)
    body = json.dumps(_payload()).encode()
    r = _post(app, body)
    assert r.status_code == 200 and r.json()["queued"] == 1
    (to, msg), = app.recorder.sent
    assert to == U and "*Wallet*" in msg["interactive"]["body"]["text"]


def test_bad_or_missing_signature_is_rejected(app, world):
    wa_user(world.repo)
    body = json.dumps(_payload()).encode()
    assert _post(app, body, sig="sha256=" + "0" * 64).status_code == 401
    assert _post(app, body, sig=False).status_code == 401
    tampered = body.replace(b"balance", b"withdraw")
    assert _post(app, tampered, sig=sign(SECRET, body)).status_code == 401
    assert app.recorder.sent == []


def test_replayed_delivery_is_processed_once(app, world):
    wa_user(world.repo)
    body = json.dumps(_payload(msg_id="wamid.REPLAY")).encode()
    assert _post(app, body).json()["queued"] == 1
    again = _post(app, body)
    assert again.status_code == 200 and again.json()["queued"] == 0
    assert len(app.recorder.sent) == 1


def test_stale_delivery_is_dropped(app, world):
    wa_user(world.repo)
    body = json.dumps(_payload(msg_id="wamid.OLD", ts=1_000_000)).encode()
    assert _post(app, body).json()["queued"] == 0
    assert app.recorder.sent == []


def test_status_updates_outbox(app, world):
    from gaming.src.channels.core import store

    now = store.now_ms()
    with store.db().transaction() as tx:
        tx.execute("INSERT INTO channel_outbox (channel, external_id, profile_id, kind, mode, template, "
                   "provider_message_id, status, error, created_at_ms, updated_at_ms) "
                   "VALUES ('whatsapp', ?, 'p', 'deposit_received', 'template', 'deposit_received', "
                   "'wamid.S1', 'sent', NULL, ?, ?)", (U, now, now))
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "statuses": [{"id": "wamid.S1", "status": "failed", "recipient_id": U,
                      "errors": [{"code": 131047, "title": "Re-engagement message"}]}]}}]}]}
    assert _post(app, json.dumps(payload).encode()).status_code == 200
    with store.db().transaction(readonly=True) as tx:
        row = tx.one("SELECT status, error FROM channel_outbox WHERE provider_message_id = 'wamid.S1'")
    assert row["status"] == "failed" and "131047" in row["error"]


def test_signature_helper():
    assert verify_signature(b"{}", sign("s", b"{}"), secret="s")
    assert not verify_signature(b"{}", sign("s", b"{}"), secret="")
    assert not verify_signature(b"{}", None, secret="s")


# ── parsing ──────────────────────────────────────────────────────────────────


def test_parse_interactive_list_template_button_and_image():
    p = _payload()
    msgs = p["entry"][0]["changes"][0]["value"]["messages"]
    msgs[:] = [
        {"from": U, "id": "1", "timestamp": "1", "type": "interactive",
         "interactive": {"type": "button_reply", "button_reply": {"id": "v1|balance|start|", "title": "Wallet"}}},
        {"from": U, "id": "2", "timestamp": "1", "type": "interactive", "context": {"id": "wamid.PREV"},
         "interactive": {"type": "list_reply", "list_reply": {"id": "v1|nav|more|1", "title": "More…"}}},
        {"from": U, "id": "3", "timestamp": "1", "type": "button", "button": {"payload": "v1|x|y|", "text": "Yes"}},
        {"from": U, "id": "4", "timestamp": "1", "type": "image",
         "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "sha256": "abc", "caption": "2-1"}},
        {"from": U, "id": "5", "timestamp": "1", "type": "sticker", "sticker": {"id": "S"}},
    ]
    events, statuses = parse(p)
    assert [e.kind for e in events] == ["button", "button", "button", "media", "unsupported"]
    assert events[1].context_id == "wamid.PREV" and events[1].button_id == "v1|nav|more|1"
    assert events[3].media.ref == "MEDIA1" and events[3].media.caption == "2-1"
    assert events[0].profile_name == "Ada" and events[0].phone == U
    assert parse({"object": "page"}) == ([], [])


# ── Graph client request shapes ──────────────────────────────────────────────


def test_client_request_shapes():
    calls = []

    def transport(method, url, *, headers, json=None, params=None):
        calls.append((method, url, headers, json))
        if url.endswith("/MEDIA1"):
            return HttpResponse(200, b'{"url": "https://lookaside.example/x", "mime_type": "image/png"}')
        return HttpResponse(200, b'{"messages": [{"id": "wamid.X"}]}')

    c = GraphClient("tok", "PNID", transport=transport, version="v21.0")
    assert c.send_text(U, "hi") == "wamid.X"
    method, url, headers, body = calls[0]
    assert (method, url) == ("POST", "https://graph.facebook.com/v21.0/PNID/messages")
    assert headers["Authorization"] == "Bearer tok"
    assert body == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": U,
                    "type": "text", "text": {"body": "hi", "preview_url": False}}
    c.mark_read("wamid.IN")
    assert calls[1][3] == {"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.IN"}
    assert c.media_info("MEDIA1")["mime_type"] == "image/png"


def test_client_raises_on_api_error():
    from gaming.src.channels.whatsapp.client import WhatsAppError

    def transport(method, url, *, headers, json=None, params=None):
        return HttpResponse(400, b'{"error": {"code": 131026, "message": "Message undeliverable"}}')

    with pytest.raises(WhatsAppError) as e:
        GraphClient("t", "p", transport=transport).send_text(U, "x")
    assert "131026" in str(e.value)


# ── templates and notify ─────────────────────────────────────────────────────


def test_templates_are_documented_word_for_word():
    doc = (ROOT / "docs" / "channels" / "WHATSAPP_SETUP.md").read_text()
    for t in templates.ALL:
        assert f"`{t.name}`" in doc, t.name
        assert t.body in doc, t.name
        assert len(t.buttons) <= 3 and all(len(b) <= 20 for b in t.buttons)
        assert t.body.count("{{") == len(t.params)
        assert not re.search(r"[\U0001F300-\U0001FAFF]", t.body)  # no emoji in utility copy


def test_template_message_shape():
    msg = templates.message(templates.DEPOSIT_RECEIVED, {"amount": "10.00", "balance": "52.00"}, ["v1|balance|start|"])
    assert msg["template"]["name"] == "deposit_received"
    assert msg["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "10.00"}, {"type": "text", "text": "52.00"}]
    assert msg["template"]["components"][1]["parameters"][0]["payload"] == "v1|balance|start|"
    with pytest.raises(templates.MissingParam):
        templates.message(templates.DEPOSIT_RECEIVED, {"amount": "1"})


def _notifier(world):
    wa, tg = RecordingDeliverer("whatsapp"), RecordingDeliverer("telegram")
    return NotificationService({"whatsapp": wa, "telegram": tg}, repo=world.repo), wa, tg


def _notice():
    return Notice("deposit_received", {"amount": "10.00", "balance": "50.00"}, "Deposit received: $10.00.",
                  [Option("v1|balance|start|", "Wallet")])


def test_notify_inside_window_sends_session_message(world):
    prof = wa_user(world.repo)
    world.repo.update("whatsapp", U, last_inbound_at=utcnow() - timedelta(hours=2))
    svc, wa, _ = _notifier(world)
    (d,) = asyncio.run(svc.notify(prof["id"], _notice()))
    assert d.mode == "session" and wa.session and not wa.templates


def test_notify_outside_window_uses_template(world):
    prof = wa_user(world.repo)
    world.repo.update("whatsapp", U, last_inbound_at=utcnow() - timedelta(hours=30))
    svc, wa, _ = _notifier(world)
    (d,) = asyncio.run(svc.notify(prof["id"], _notice()))
    assert (d.mode, d.template) == ("template", "deposit_received")
    assert wa.templates[0][1]["template"]["name"] == "deposit_received"


def test_notify_skips_opted_out_and_falls_back_to_telegram(world):
    prof = wa_user(world.repo)
    world.repo.upsert(Identity("telegram", "77", prof["id"], notify_priority=200))
    world.repo.update("whatsapp", U, opted_out_at=utcnow())
    svc, wa, tg = _notifier(world)
    (d,) = asyncio.run(svc.notify(prof["id"], _notice()))
    assert d.channel == "telegram" and tg.session and not wa.session and not wa.templates


def test_notify_kind_without_template_falls_back(world):
    prof = wa_user(world.repo)
    world.repo.upsert(Identity("telegram", "77", prof["id"], notify_priority=200))
    svc, wa, tg = _notifier(world)
    out = asyncio.run(svc.notify(prof["id"], Notice("marketing_promo", {}, "Play again!")))
    assert [d.mode for d in out] == ["skipped", "session"] and out[1].channel == "telegram"
