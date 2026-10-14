"""AFM football authz through the full backend app, money path end to end.

test_sec_football_authz mounts the agentic router on a bare FastAPI(); this
file drives gaming.src.backend.main:app instead, so the geo-fence middleware
and every other piece of the real request path sit in front of the key checks.

  - every mutating /football route answers 401 without a key on the real app
  - a refused purchase moves no money and no ownership
  - a keyed purchase (the BFF shape: master key + X-Boardman-Caller) still
    settles on the demo ledger and pays the seller
  - the keyless local demo (BOARDMAN_STACK_ALLOW_OPEN=1) still reaches the
    platform-only clock routes
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

MASTER = "sk_bm_e2e_master_0123456789"
BASE = "/api/stack/agentic"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    for var in (
        "REMATCH_API_KEY",
        "STACK_API_KEY",
        "BOARDMAN_STACK_API_KEYS",
        "BOARDMAN_STACK_API_KEYS_FILE",
        "BOARDMAN_STACK_ALLOW_OPEN",
        "CIRCLE_API_KEY",
        "CIRCLE_ENTITY_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def client():
    from gaming.src.backend.main import app

    return TestClient(app)


def _as(caller: str) -> dict[str, str]:
    """What the BFF sends for a signed-in user."""
    return {"X-Boardman-Key": MASTER, "X-Boardman-Caller": caller}


def _mutating_football_routes() -> list[tuple[str, str]]:
    from gaming.src.stack.agentic.api import router

    out = set()
    for r in router.routes:
        path = getattr(r, "path", "")
        if not path.startswith(BASE + "/football/"):
            continue
        for m in getattr(r, "methods", ()) or ():
            if m in {"POST", "PUT", "PATCH", "DELETE"}:
                out.add((m, path.replace("{agent_id}", "nope")))
    return sorted(out)


MUTATING = _mutating_football_routes()


def test_discovery_found_the_money_routes():
    paths = {p for _, p in MUTATING}
    for must in ("purchase", "offer/accept", "wallet/bind", "betting/bet", "season/reset"):
        assert any(p.endswith(must) for p in paths), must


@pytest.mark.parametrize("method,path", MUTATING)
def test_unkeyed_write_is_401_on_the_real_app(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401, (method, path, r.text)


def test_purchase_refused_then_settled(client):
    from gaming.src.stack.agentic import ledger as L

    made = client.post(
        BASE + "/football/agents/create",
        json={"manager_name": "E2E City", "club_name": "E2E City FC"},
        headers=_as("dev_e2e"),
    )
    assert made.status_code == 200, made.text
    aid = made.json()["agent"]["agent_id"]
    listed = client.post(
        BASE + "/football/agents/list",
        json={"agent_id": aid, "price_usdc": 25},
        headers=_as("dev_e2e"),
    )
    assert listed.status_code == 200, listed.text

    body = {"agent_id": aid, "settlement": "ledger"}
    refused = client.post(BASE + "/football/agents/purchase", json={**body, "buyer_id": "buyer_e2e"})
    assert refused.status_code == 401
    assert L.balance("owner:dev_e2e") == Decimal("0")
    owner = {a["agent_id"]: a["owner_id"] for a in client.get(
        BASE + "/football/agents", headers={"X-Boardman-Key": MASTER}
    ).json()["agents"]}
    assert owner[aid] == "dev_e2e"

    # signed in but broke: 402, nothing moves (no faucet for human buyers)
    broke = client.post(BASE + "/football/agents/purchase", json=body, headers=_as("buyer_e2e"))
    assert broke.status_code == 402, broke.text
    assert "insufficient balance" in broke.json()["detail"]
    assert L.balance("owner:dev_e2e") == Decimal("0")
    assert L.balance("owner:buyer_e2e") == Decimal("0")

    L.credit("owner:buyer_e2e", Decimal("25"), reason="test_deposit")
    bought = client.post(BASE + "/football/agents/purchase", json=body, headers=_as("buyer_e2e"))
    assert bought.status_code == 200, bought.text
    assert bought.json()["sale"]["mode"] == "ledger"
    assert L.balance("owner:dev_e2e") == Decimal("25")
    assert L.balance("owner:buyer_e2e") == Decimal("0")


def test_open_demo_still_reaches_platform_routes(client, monkeypatch):
    monkeypatch.delenv("BOARDMAN_API_KEY", raising=False)
    monkeypatch.setenv("BOARDMAN_STACK_ALLOW_OPEN", "1")
    assert client.post(BASE + "/football/season/tick").status_code == 200
