"""A manifest version bump on deploy must never take a manager from its owner.

ensure_demo_agents re-registers a demo agent whenever its manifest version
changes. Re-registration merges: manifest-owned fields (name, mind, version,
games, runtime …) refresh; owner, stats, webhook, wallet, listing and
created_at survive.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

MASTER = "sk_master_test"
BUILDER = "sk_builder_alice"
OTHER = "sk_builder_mallory"


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


def _bump_manifest(monkeypatch, agent_id: str, **changes):
    """Ship a new manifest version for one demo agent."""
    import gaming.src.stack.agentic.agents as agents_pkg

    real = agents_pkg.load_demo_manifests

    def bumped():
        out = []
        for m in real():
            if m["agent_id"] == agent_id:
                m = {**m, "version": "9.9.9", **changes}
            out.append(m)
        return out

    monkeypatch.setattr(agents_pkg, "load_demo_manifests", bumped)


def test_bought_demo_manager_survives_a_manifest_bump(monkeypatch):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
        list_market_agents,
        purchase_manager_agent,
    )
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()
    aid = "agent_bluelock_demo"
    list_market_agents()  # ships the developer's default listing
    L.credit("owner:alice", Decimal("25.00"), reason="test_deposit")
    purchase_manager_agent(agent_id=aid, buyer_id="alice")
    reg.update_stats(aid, "win")
    reg.update_stats(aid, "draw")
    reg.credit_creator_fee(aid, "1.25")
    reg.set_webhook(aid, "https://alice.example/afm")
    list_manager_for_sale(agent_id=aid, price_usdc="40", listed_by="alice")
    before = reg.get_agent(aid)
    assert before["owner_id"] == "alice" and before["listing"]

    new_mind = {**before["mind"], "blurb": "Re-tuned for season three."}
    _bump_manifest(monkeypatch, aid, mind=new_mind)
    reg.ensure_demo_agents()

    after = reg.get_agent(aid)
    # the deploy refreshed what the manifest owns …
    assert after["version"] == "9.9.9"
    assert after["mind"]["blurb"] == "Re-tuned for season three."
    # … and nothing the agent earned or the owner set
    assert after["owner_id"] == "alice"
    assert after["creator_id"] == before["creator_id"]
    assert after["stats"] == before["stats"]
    assert after["stats"]["wins"] == 1 and after["stats"]["creator_fees_usdc"] == "1.25"
    assert after["webhook_url"] == "https://alice.example/afm"
    assert after["runtime"]["webhook_url"] == "https://alice.example/afm"
    assert after["listing"] == before["listing"]
    assert after["acquired_at"] == before["acquired_at"]
    for k in ("wallet_address", "key_custody", "identity_contract", "chain_id", "created_at"):
        assert after[k] == before[k], k
    # and the marketplace still sees alice's listing, not the developer's
    row = next(a for a in list_market_agents() if a["agent_id"] == aid)
    assert row["owner_id"] == "alice" and row["listed"] is True


def test_unbought_demo_manager_tracks_the_manifest(monkeypatch):
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()
    aid = "agent_galactico_demo"
    reg.update_stats(aid, "loss")
    before = reg.get_agent(aid)

    _bump_manifest(
        monkeypatch,
        aid,
        name="Galáctico II",
        runtime={**before["runtime"], "webhook_url": "http://127.0.0.1:18999"},
    )
    reg.ensure_demo_agents()
    after = reg.get_agent(aid)
    assert after["name"] == "Galáctico II"
    # still the developer's: the default webhook follows the deploy
    assert after["owner_id"] == after["creator_id"] == before["creator_id"]
    assert after["webhook_url"] == "http://127.0.0.1:18999"
    assert after["stats"]["losses"] == 1
    assert after["wallet_address"] == before["wallet_address"]


def test_creator_set_webhook_survives_a_bump(monkeypatch):
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()
    aid = "agent_tinkerer_demo"
    reg.set_webhook(aid, "https://studio.example/tinkerer")
    _bump_manifest(monkeypatch, aid)
    reg.ensure_demo_agents()
    assert reg.get_agent(aid)["webhook_url"] == "https://studio.example/tinkerer"


# ----------------------------------------------------- public register route


@pytest.fixture()
def client(monkeypatch):
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_ALLOW_OPEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", f"{BUILDER}:alice_lab,{OTHER}:mallory_lab")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from gaming.src.stack.agentic import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.router)
    return TestClient(app)


def _register(client, key, **body):
    payload = {"agent_id": "agent_alice_bot", "name": "Alice Bot", "creator_id": "alice_lab", **body}
    return client.post(
        "/api/stack/agentic/agents/register",
        json=payload,
        headers={"X-Boardman-Key": key},
    )


def test_register_route_cannot_take_over_someone_elses_agent(client):
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    # a demo manager someone may own is not re-registerable by a builder
    res = _register(client, OTHER, agent_id="agent_bluelock_demo", owner_id="mallory")
    assert res.status_code == 409
    assert get_registry().get_agent("agent_bluelock_demo")["owner_id"] != "mallory"

    assert _register(client, BUILDER).status_code == 200
    get_registry().update_stats("agent_alice_bot", "win")
    # another builder cannot repoint it …
    assert _register(client, OTHER, owner_id="mallory").status_code == 409
    # … its own builder can re-deploy, and the record merges
    res = _register(client, BUILDER, name="Alice Bot v2", webhook_url="https://alice.example/move")
    assert res.status_code == 200
    rec = get_registry().get_agent("agent_alice_bot")
    assert rec["name"] == "Alice Bot v2"
    assert rec["stats"]["wins"] == 1
    assert rec["registered_by"] == "alice_lab"
