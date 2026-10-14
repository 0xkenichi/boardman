"""Agent key custody: random keys, sealed at rest, no seed fallback, rotation."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest
from eth_account import Account

SECRET = "test-keystore-secret-" + "x" * 32
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path / "agentic"))
    monkeypatch.delenv("BOARDMAN_KEYSTORE_DIR", raising=False)
    monkeypatch.delenv("BOARDMAN_KEYSTORE_BACKEND", raising=False)
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "0")
    monkeypatch.setenv("BOARDMAN_KEYSTORE_SECRET", SECRET)
    from gaming.src.stack.agentic.registry import get_registry

    get_registry.cache_clear()
    yield
    get_registry.cache_clear()


def _legacy_key(seed: str) -> str:
    from eth_hash.auto import keccak

    return "0x" + keccak(f"boardman.agent.wallet.v1:{seed}".encode()).hex()


def _register(agent_id: str = "agent_test_ks", **kw):
    from gaming.src.stack.agentic.registry import get_registry

    return get_registry().register_agent(
        agent_id=agent_id, name="T", owner_id="o", strategy_id="s",
        openings=[], mind={}, **kw,
    )


# ------------------------------------------------------------- keystore core


def test_round_trip_random_key(tmp_path):
    from gaming.src.stack.agentic.keystore import AgentKeystore, FileBackend

    ks = AgentKeystore(FileBackend(tmp_path / "ks"))
    addr = ks.create("agent_a")
    pk = ks.private_key("agent_a")
    assert Account.from_key(pk).address == addr
    assert ks.get_or_create("agent_a") == addr  # reused, not regenerated
    assert AgentKeystore(FileBackend(tmp_path / "ks2")).create("agent_a") != addr

    path = tmp_path / "ks" / "agent_a.json"
    raw = path.read_text()
    assert pk[2:] not in raw.lower()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with pytest.raises(Exception):
        ks.create("agent_a")  # never overwrite a live key


def test_refuses_without_secret(tmp_path, monkeypatch):
    from gaming.src.stack.agentic.keystore import (
        AgentKeystore, FileBackend, KeystoreLocked,
    )

    ks = AgentKeystore(FileBackend(tmp_path / "ks"))
    addr = ks.create("agent_a")
    monkeypatch.delenv("BOARDMAN_KEYSTORE_SECRET")
    assert ks.address("agent_a") == addr  # public lookup still works
    with pytest.raises(KeystoreLocked):
        ks.private_key("agent_a")
    with pytest.raises(KeystoreLocked):
        ks.create("agent_b")
    monkeypatch.setenv("BOARDMAN_KEYSTORE_SECRET", "short")
    with pytest.raises(KeystoreLocked):
        ks.private_key("agent_a")


def test_wrong_secret_and_swapped_entry_fail_closed(tmp_path, monkeypatch):
    from gaming.src.stack.agentic.keystore import AgentKeystore, FileBackend, KeystoreError

    ks = AgentKeystore(FileBackend(tmp_path / "ks"))
    ks.create("agent_a")
    ks.create("agent_b")
    a = json.loads((tmp_path / "ks" / "agent_a.json").read_text())
    a["agent_id"] = "agent_b"
    (tmp_path / "ks" / "agent_b.json").write_text(json.dumps(a))
    with pytest.raises(KeystoreError):
        ks.private_key("agent_b")  # aad binds agent_id + address
    monkeypatch.setenv("BOARDMAN_KEYSTORE_SECRET", "y" * 40)
    with pytest.raises(KeystoreError):
        ks.private_key("agent_a")


def test_rejects_path_like_agent_ids(tmp_path):
    from gaming.src.stack.agentic.keystore import AgentKeystore, FileBackend, KeystoreError

    ks = AgentKeystore(FileBackend(tmp_path / "ks"))
    for bad in ("../x", "a/b", "a.pending", ""):
        with pytest.raises(KeystoreError):
            ks.create(bad)


def test_unknown_backend_refused(monkeypatch):
    from gaming.src.stack.agentic.keystore import KeystoreError, get_keystore

    monkeypatch.setenv("BOARDMAN_KEYSTORE_BACKEND", "kms")
    with pytest.raises(KeystoreError):
        get_keystore()


# ---------------------------------------------------- registry + signing path


def test_registry_uses_random_keystore_key():
    from gaming.src.stack.agentic import wallets
    from gaming.src.stack.agentic.keystore import get_keystore
    from gaming.src.stack.agentic.onchain import load_agent_private_key

    rec = _register(seed="boardman.agent.agent_test_ks")
    legacy = Account.from_key(_legacy_key("boardman.agent.agent_test_ks")).address
    assert rec["wallet_address"] != legacy
    assert rec["key_custody"] == "keystore"
    assert get_keystore().address("agent_test_ks") == rec["wallet_address"]
    assert Account.from_key(load_agent_private_key("agent_test_ks")).address == rec["wallet_address"]
    assert not hasattr(wallets, "seed_to_private_key")
    # re-registering keeps the same wallet
    assert _register()["wallet_address"] == rec["wallet_address"]


def test_no_seed_or_plaintext_fallback_when_key_missing():
    from gaming.src.stack.agentic.keystore import KeyNotFound
    from gaming.src.stack.agentic.onchain import load_agent_private_key
    from gaming.src.stack.agentic.store import save_json

    legacy_pk = _legacy_key("boardman.agent.raja.kia_alekhine.v3")
    save_json("secrets_agent_raja_kia_alekhine.json", {"private_key": legacy_pk})
    with pytest.raises(KeyNotFound):
        load_agent_private_key("agent_raja_kia_alekhine")


def test_signing_refuses_when_rotation_pending():
    from gaming.src.stack.agentic.onchain import load_agent_private_key
    from gaming.src.stack.agentic.store import load_json, save_json

    _register()
    data = load_json("agents.json", {})
    data["agents"]["agent_test_ks"]["wallet_address"] = "0x" + "11" * 20
    save_json("agents.json", data)
    with pytest.raises(RuntimeError, match="rotation pending"):
        load_agent_private_key("agent_test_ks")


def test_locked_keystore_registers_unprovisioned_offchain(monkeypatch):
    from gaming.src.stack.agentic.keystore import KeyNotFound, KeystoreLocked
    from gaming.src.stack.agentic.onchain import load_agent_private_key

    monkeypatch.delenv("BOARDMAN_KEYSTORE_SECRET")
    rec = _register()
    assert rec["key_custody"] == "unprovisioned"
    with pytest.raises((KeyNotFound, KeystoreLocked)):
        load_agent_private_key("agent_test_ks")
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "1")
    with pytest.raises(KeystoreLocked):
        _register("agent_test_live")


def test_house_never_gets_a_spend_key():
    from gaming.src.stack.agentic.keystore import get_keystore

    rec = _register("agent_house_like", role="house")
    assert rec["key_custody"] == "none"
    assert get_keystore().address("agent_house_like") is None


def test_manifests_carry_no_key_seeds():
    from gaming.src.stack.agentic.agents import load_demo_manifests

    for m in load_demo_manifests():
        assert "seed" not in m, m["agent_id"]


# ------------------------------------------------------------------ rotation


def _rotation_module():
    spec = importlib.util.spec_from_file_location(
        "rotate_agent_wallets", ROOT / "scripts" / "rotate_agent_wallets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_legacy_agents():
    from gaming.src.stack.agentic.store import save_json

    raja_pk = _legacy_key("boardman.agent.raja.kia_alekhine.v3")
    afm_pk = _legacy_key("boardman.agent.afm.agent_custom_mgr")
    agents = {
        "agent_raja_kia_alekhine": {
            "agent_id": "agent_raja_kia_alekhine", "name": "Raja", "role": "contestant",
            "wallet_address": Account.from_key(raja_pk).address,
        },
        "agent_custom_mgr": {
            "agent_id": "agent_custom_mgr", "name": "Custom", "role": "contestant",
            "wallet_address": Account.from_key(afm_pk).address,
        },
        "agent_boardman_house": {
            "agent_id": "agent_boardman_house", "name": "Boardman", "role": "house",
            "wallet_address": "0x" + "22" * 20,
        },
    }
    save_json("agents.json", {"agents": agents})
    save_json("secrets_agent_raja_kia_alekhine.json", {"private_key": raja_pk})
    return agents, (raja_pk, afm_pk)


def test_rotation_dry_run_stages_keys_and_prints_no_secrets(capsys, monkeypatch):
    from gaming.src.stack.agentic.keystore import PENDING, get_keystore
    from gaming.src.stack.agentic.store import load_json

    rot = _rotation_module()
    monkeypatch.setattr(rot, "_sweep", lambda *a, **k: pytest.fail("dry run swept"))
    agents, legacy_pks = _seed_legacy_agents()
    before = load_json("agents.json", {})

    assert rot.main([]) == 0
    out = capsys.readouterr().out
    ks = get_keystore()
    for aid in ("agent_raja_kia_alekhine", "agent_custom_mgr"):
        new = ks.address(aid, slot=PENDING)
        assert new and new in out
        assert agents[aid]["wallet_address"] in out
        assert ks.address(aid) is None  # not promoted
    assert "[legacy-plaintext]" in out and "[legacy-seed]" in out
    assert "house has no spend key" in out
    for pk in legacy_pks:
        assert pk[2:] not in out.lower()
    for p in ks.backend.root.glob("*.json"):
        assert p.read_text().count("ciphertext") == 1
    assert load_json("agents.json", {}) == before  # registry untouched

    # stable plan on re-run
    first = ks.address("agent_custom_mgr", slot=PENDING)
    assert rot.main([]) == 0
    assert ks.address("agent_custom_mgr", slot=PENDING) == first


def test_rotation_dry_run_refuses_without_secret(capsys, monkeypatch):
    rot = _rotation_module()
    _seed_legacy_agents()
    monkeypatch.delenv("BOARDMAN_KEYSTORE_SECRET")
    assert rot.main([]) == 2
    assert "refusing" in capsys.readouterr().err


def test_rotation_finalize_promotes_and_seals(monkeypatch):
    from gaming.src.stack.agentic.keystore import PENDING, get_keystore
    from gaming.src.stack.agentic.onchain import load_agent_private_key
    from gaming.src.stack.agentic.store import load_json

    rot = _rotation_module()
    agents, _ = _seed_legacy_agents()
    swept = []
    monkeypatch.setattr(
        rot, "_sweep",
        lambda pk, to, reserve, chain: swept.append((Account.from_key(pk).address, to))
        or {"swept_usdc": "0", "tx_hash": None},
    )
    monkeypatch.setattr("builtins.input", lambda *_: "nope")
    assert rot.main(["--execute"]) == 1  # needs typed confirmation
    assert not swept

    assert rot.main(["--execute", "--yes", "--agents", "agent_raja_kia_alekhine"]) == 0
    ks = get_keystore()
    new = ks.address("agent_raja_kia_alekhine")
    assert ks.address("agent_raja_kia_alekhine", slot=PENDING) is None
    assert swept == [(agents["agent_raja_kia_alekhine"]["wallet_address"], new)]
    rec = load_json("agents.json", {})["agents"]["agent_raja_kia_alekhine"]
    assert rec["wallet_address"] == new
    assert rec["previous_wallet_address"] == agents["agent_raja_kia_alekhine"]["wallet_address"]
    assert load_json("secrets_agent_raja_kia_alekhine.json", {})["private_key"] is None
    assert Account.from_key(load_agent_private_key("agent_raja_kia_alekhine")).address == new
