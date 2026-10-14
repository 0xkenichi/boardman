"""Deposit routes need the key + caller, spectator approvals are the
caller's own, the self-credit payout route is gone, and no CORS config
allows the ``null`` origin with credentials."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MASTER = "sk_master_test"


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", "sk_builder:alice_lab")


# ---------------------------------------------------------------- deposit

@pytest.fixture()
def deposit_client(monkeypatch):
    from gaming.src.backend.api import deposit as D

    async def fake_address(user_id):
        return f"addr-for-{user_id}"

    monkeypatch.setattr(D, "get_deposit_address", fake_address)
    app = FastAPI()
    app.include_router(D.router, prefix="/api")
    return TestClient(app)


def test_deposit_needs_master_key(deposit_client):
    assert deposit_client.get("/api/deposit/address", params={"user_id": "u1"}).status_code == 401
    r = deposit_client.get("/api/deposit/address", params={"user_id": "u1"}, headers={"X-Boardman-Key": "sk_builder"})
    assert r.status_code == 403


def test_deposit_user_is_the_caller(deposit_client):
    h = {"X-Boardman-Key": MASTER, "X-Boardman-Caller": "alice"}
    assert deposit_client.get("/api/deposit/address", params={"user_id": "bob"}, headers=h).status_code == 403
    r = deposit_client.get("/api/deposit/address", headers=h)
    assert r.status_code == 200 and r.json()["address"] == "addr-for-alice"
    # the platform itself (no caller header) names the user
    r = deposit_client.get("/api/deposit/address", params={"user_id": "bob"}, headers={"X-Boardman-Key": MASTER})
    assert r.status_code == 200 and r.json()["address"] == "addr-for-bob"


# ---------------------------------------------------------------- spectator

@pytest.fixture()
def web_client(monkeypatch):
    from gaming.src.backend.api import rematch_web as W
    from gaming.src.backend.services import tx_approval as T

    rows = {"apr_alice": {"id": "apr_alice", "profile_id": "alice"}}
    monkeypatch.setattr(T, "get_approval_row", lambda aid: rows.get(aid))

    async def fake_apply(aid):
        return {"success": True, "approval_id": aid, "status": "approved"}

    monkeypatch.setattr(T, "apply_approved_spend", fake_apply)
    app = FastAPI()
    app.include_router(W.router)
    return TestClient(app, headers={"X-Rematch-Key": MASTER})


def test_payout_route_is_gone(web_client):
    r = web_client.post("/api/rematch/web/spectator/payout", json={"profile_id": "alice", "amount": 1000})
    assert r.status_code in (404, 405)


@pytest.mark.parametrize("path", ["/api/rematch/web/spectator/bet", "/api/rematch/web/spectator/approval"])
def test_approval_poll_is_the_callers_own(web_client, path):
    mine = web_client.get(path, params={"approval_id": "apr_alice"}, headers={"X-Boardman-Caller": "alice"})
    assert mine.status_code == 200 and mine.json()["approval_id"] == "apr_alice"
    theirs = web_client.get(path, params={"approval_id": "apr_alice"}, headers={"X-Boardman-Caller": "mallory"})
    assert theirs.status_code == 404
    unknown = web_client.get(path, params={"approval_id": "apr_nope"}, headers={"X-Boardman-Caller": "alice"})
    assert unknown.status_code == 404
    anon = web_client.get(path, params={"approval_id": "apr_alice"})
    assert anon.status_code == 400


# ---------------------------------------------------------------- CORS

def _cors_origins(app) -> list[str]:
    for mw in app.user_middleware:
        if getattr(mw.cls, "__name__", "") == "CORSMiddleware":
            return list(mw.kwargs.get("allow_origins") or [])
    return []


def test_realtime_api_cors_has_no_null_origin():
    pytest.importorskip("socketio", reason="realtime deps")
    try:
        from gaming.src.backend.api import realtime_api as R
    except Exception as exc:  # optional runtime deps
        pytest.skip(f"realtime_api not importable here: {exc}")
    origins = _cors_origins(R.app)
    assert origins and "null" not in origins and "*" not in origins


def test_cors_lists_drop_null_even_from_env(monkeypatch):
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for rel in ("src/backend/api/realtime_api.py", "src/backend/api_proof_of_play.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert ",null" not in src
        assert 'not in {"null", "*"}' in src
        ast.parse(src)
    agentic = (root / "scripts/run_agentic_api.py").read_text(encoding="utf-8")
    assert 'allow_origins=["*"]' not in agentic
    assert "allow_credentials=False" in agentic
