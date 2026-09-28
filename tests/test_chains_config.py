"""Arc mainnet wiring: chains.yaml entry, chains.py fallback, aliases, env overrides.

Mainnet chain ID is 5042 (Circle docs) — NOT 5042001. Testnet stays 5042002.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def chains_mod():
    import gaming.src.backend.services.chains as chains

    importlib.reload(chains)
    try:
        yield chains
    finally:
        chains.reload_chains_config()


def test_yaml_has_arc_mainnet_with_correct_chain_id(chains_mod):
    chains_mod.reload_chains_config()
    cfg = chains_mod.load_chains_config()
    row = (cfg.get("chains") or {}).get("arc_mainnet")
    assert row, "arc_mainnet missing from config/chains.yaml"
    assert row["chain_id"] == 5042
    assert row["circle_blockchain"] == "ARC"
    assert row["enabled"] is False  # not user-facing until escrow deploy
    assert row["usdc_address"].lower() == "0x3600000000000000000000000000000000000000"


def test_fallback_chain_map_includes_arc_mainnet(chains_mod, monkeypatch):
    monkeypatch.setattr(chains_mod, "_CONFIG_PATH", Path("/no/such/chains.yaml"))
    chains_mod.reload_chains_config()
    row = chains_mod.get_chain("arc_mainnet")
    assert row["chain_id"] == 5042
    assert row["circle_blockchain"] == "ARC"


def test_normalize_aliases(chains_mod):
    assert chains_mod.normalize_chain_id("arc_mainnet") == "arc_mainnet"
    assert chains_mod.normalize_chain_id("arcmainnet") == "arc_mainnet"
    assert chains_mod.normalize_chain_id("mainnet") == "arc_mainnet"
    assert chains_mod.normalize_chain_id("arc_testnet") == "arc"
    assert chains_mod.normalize_chain_id("ARC") == "arc"


def test_mainnet_not_live_for_users(chains_mod):
    chains_mod.reload_chains_config()
    assert chains_mod.is_chain_enabled("arc_mainnet") is False
    assert chains_mod.default_chain_id() == "arc"  # settlement stays on testnet for now
    with pytest.raises(ValueError):
        chains_mod.get_chain("arc_mainnet", require_enabled=True)


def test_circle_to_chain_maps_arc_labels(chains_mod):
    assert chains_mod.CIRCLE_TO_CHAIN["ARC-TESTNET"] == "arc"
    assert chains_mod.CIRCLE_TO_CHAIN["ARC"] == "arc_mainnet"


def test_env_overrides_apply_to_mainnet(chains_mod, monkeypatch):
    chains_mod.reload_chains_config()
    monkeypatch.setenv("ARC_MAINNET_RPC_URL", "https://rpc.example.mainnet")
    monkeypatch.setenv("BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET", "0x" + "ab" * 20)
    monkeypatch.setenv("CIRCLE_USDC_TOKEN_ID_ARC_MAINNET", "tok-uuid-1234")
    chains_mod.reload_chains_config()
    row = chains_mod.get_chain("arc_mainnet")
    assert row["rpc_url"] == "https://rpc.example.mainnet"
    assert row["escrow_address"] == "0x" + "ab" * 20
    assert chains_mod.get_circle_usdc_token_id("arc_mainnet") == "tok-uuid-1234"


def test_yaml_file_on_disk_has_5042():
    import yaml

    data = yaml.safe_load((_REPO / "config" / "chains.yaml").read_text(encoding="utf-8"))
    row = data["chains"]["arc_mainnet"]
    assert row["chain_id"] == 5042
    assert data["chains"]["arc"]["chain_id"] == 5042002
