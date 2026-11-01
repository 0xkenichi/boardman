"""Avalanche build: Fuji as the arena settlement chain, C-Chain mainnet as prep.

The switch is env only (.env.avalanche.example). Arc stays the default, and
an Arc-only override can never point the Avalanche signer at Arc.
"""
from __future__ import annotations

import pytest

from gaming.src.backend.services import chains, realms
from gaming.src.stack.agentic import onchain, spectator_onchain

FUJI_USDC = "0x5425890298aed601595a70AB815c96711a31Bc65"
FUJI_ESCROW = "0x00000000000000000000000000000000000a7a1c"
FUJI_POOL = "0x00000000000000000000000000000000000b0015"


@pytest.fixture()
def avalanche_build(monkeypatch):
    """The env .env.avalanche.example sets, with test addresses."""
    monkeypatch.setenv("CLAW_ENABLED_CHAINS", "avalanche")
    monkeypatch.setenv("CLAW_DEFAULT_CHAIN", "avalanche")
    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "avalanche")
    monkeypatch.setenv("CLAW_ESCROW_ADDRESS_AVALANCHE", FUJI_ESCROW)
    monkeypatch.setenv("SPECTATOR_ESCROW_ADDRESS_AVALANCHE", FUJI_POOL)
    chains.reload_chains_config()
    yield
    monkeypatch.undo()
    chains.reload_chains_config()


def test_avalanche_is_the_default_build(monkeypatch):
    for name in ("BOARDMAN_ARENA_CHAIN", "BOARDMAN_HUMANS_CHAIN", "CLAW_DEFAULT_CHAIN", "CLAW_ENABLED_CHAINS"):
        monkeypatch.delenv(name, raising=False)
    chains.reload_chains_config()
    assert onchain.default_chain() == "avalanche"
    assert chains.default_chain_id() == "avalanche"
    assert realms.humans_chain() == "avalanche_mainnet"
    assert [c["id"] for c in chains.list_chains()] == ["avalanche"]
    from gaming.src.backend.services.funding_rails import settlement_rail_id

    assert settlement_rail_id() == "avalanche"


def test_arc_still_works_when_switched_on(monkeypatch):
    """Arc support stays in the code: one env switch makes it the arena chain."""
    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "arc")
    monkeypatch.setenv("CLAW_ENABLED_CHAINS", "arc")
    chains.reload_chains_config()
    assert onchain.default_chain() == "arc"
    assert onchain._chain_config()["evm_chain_id"] == 5042002
    chains.reload_chains_config()


def test_fuji_is_the_arena_chain_in_the_avalanche_build(avalanche_build):
    cfg = onchain._chain_config()
    assert cfg["chain_id"] == "avalanche"
    assert cfg["evm_chain_id"] == 43113
    assert cfg["usdc"].lower() == FUJI_USDC.lower()
    assert cfg["escrow"] == FUJI_ESCROW
    assert "avax-test.network" in cfg["rpc_url"]
    assert onchain._explorer(cfg, "0xabc") == "https://testnet.snowtrace.io/tx/0xabc"
    assert chains.default_chain_id() == "avalanche"
    assert [c["id"] for c in chains.list_chains()] == ["avalanche"]
    assert chains.escrow_version("avalanche") == 2


def test_arc_overrides_never_leak_into_avalanche(avalanche_build, monkeypatch):
    monkeypatch.setenv("ARC_RPC_URL", "https://rpc.testnet.arc.io")
    monkeypatch.setenv("ARC_USDC_ADDRESS", "0x3600000000000000000000000000000000000000")
    monkeypatch.setenv("BOARDMAN_ESCROW_ADDRESS_ARC", "0xD382f627fB565eb96D9EFFb66B9119DD4a555847")
    monkeypatch.setenv("SPECTATOR_ESCROW_ADDRESS", "0xd45bE49456021B74D2712fcffD47f17f91D39664")
    cfg = onchain._chain_config("avalanche")
    assert "arc" not in cfg["rpc_url"]
    assert cfg["usdc"].lower() == FUJI_USDC.lower()
    assert cfg["escrow"] == FUJI_ESCROW
    assert spectator_onchain.spectator_pool_address("avalanche") == FUJI_POOL
    # ...and the Arc chain still gets its own overrides.
    assert onchain._chain_config("arc")["escrow"] == "0xD382f627fB565eb96D9EFFb66B9119DD4a555847"
    assert spectator_onchain.spectator_pool_address("arc") == "0xd45bE49456021B74D2712fcffD47f17f91D39664"


def test_avalanche_specific_overrides_win(avalanche_build, monkeypatch):
    monkeypatch.setenv("BOARDMAN_ESCROW_ADDRESS_AVALANCHE", "0x00000000000000000000000000000000000e5c00")
    monkeypatch.setenv("AVALANCHE_FUJI_RPC_URL", "http://127.0.0.1:9650/ext/bc/C/rpc")
    chains.reload_chains_config()
    cfg = onchain._chain_config()
    assert cfg["escrow"] == "0x00000000000000000000000000000000000e5c00"
    assert cfg["rpc_url"] == "http://127.0.0.1:9650/ext/bc/C/rpc"


def test_avalanche_without_an_escrow_fails_closed(monkeypatch):
    """No silent fallback to Arc's escrow when Fuji has none configured."""
    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "avalanche")
    chains.reload_chains_config()
    real = chains.get_chain

    def no_escrow(cid, **kw):
        row = dict(real(cid, **kw))
        if row["id"] == "avalanche":
            row["escrow_address"] = ""
        return row

    monkeypatch.setattr(chains, "get_chain", no_escrow)
    with pytest.raises(RuntimeError, match="avalanche"):
        onchain._chain_config()
    chains.reload_chains_config()


def test_c_chain_mainnet_is_real_money_and_never_the_arena(monkeypatch):
    chains.reload_chains_config()
    row = chains.get_chain("avalanche_mainnet")
    assert row["chain_id"] == 43114 and row["network"] == "mainnet" and row["enabled"] is False
    assert row["usdc_address"] == "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E"
    assert chains.normalize_chain_id("avax_mainnet") == "avalanche_mainnet"
    assert realms.is_real_chain("avalanche_mainnet")
    assert 43114 in realms.real_evm_chain_ids()
    assert 43113 in realms.practice_evm_chain_ids()
    with pytest.raises(realms.RealmViolation):
        onchain._chain_config("avalanche_mainnet")
    with pytest.raises(realms.RealmViolation):
        realms.assert_practice_evm(43114, path="test")
    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "avalanche_mainnet")
    with pytest.raises(realms.RealmMisconfigured):
        onchain.default_chain()


def test_mainnet_default_chain_env_is_ignored(monkeypatch):
    monkeypatch.setenv("CLAW_ENABLED_CHAINS", "avalanche,avalanche_mainnet")
    monkeypatch.setenv("CLAW_DEFAULT_CHAIN", "avalanche_mainnet")
    chains.reload_chains_config()
    assert chains.default_chain_id() == "avalanche"
    chains.reload_chains_config()


def test_chain_help_follows_the_build(avalanche_build):
    text = chains.format_chain_help()
    assert "avalanche — Avalanche Fuji ★ live (AVAX gas)" in text
    assert "Arc" not in text
    assert text.rstrip().endswith("private avalanche")


def test_new_matches_land_on_the_arena_chain(avalanche_build):
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    agents = {a["name"].lower(): a for a in get_registry().ensure_demo_agents()}
    m = get_match_service().create_match(
        agent_a_id=agents["raja"]["agent_id"], agent_b_id=agents["nero"]["agent_id"], stake_usdc=2.0
    )
    assert m["chain_id"] == "avalanche"
    with pytest.raises(realms.RealmViolation):
        get_match_service().create_match(
            agent_a_id=agents["raja"]["agent_id"],
            agent_b_id=agents["nero"]["agent_id"],
            stake_usdc=2.0,
            chain_id="avalanche_mainnet",
        )


@pytest.mark.parametrize("env", ["CLAW_DEFAULT_CHAIN", "SPECTATOR_CHAIN", "BOARDMAN_SETTLEMENT_RAIL"])
def test_spectator_betting_treats_c_chain_mainnet_as_mainnet(monkeypatch, env):
    """Betting stays off on any mainnet, not only Arc's."""
    from gaming.src.backend.services import spectator_policy

    for name in ("NETWORK", "CLAW_DEFAULT_CHAIN", "SPECTATOR_CHAIN", "BOARDMAN_SETTLEMENT_RAIL"):
        monkeypatch.delenv(name, raising=False)
    chains.reload_chains_config()
    assert spectator_policy.is_mainnet() is False
    monkeypatch.setenv(env, "avalanche")
    assert spectator_policy.is_mainnet() is False
    monkeypatch.setenv(env, "avalanche_mainnet")
    assert spectator_policy.is_mainnet() is True


def test_geo_fence_is_strict_on_c_chain_mainnet(monkeypatch):
    from gaming.src.backend.middleware import geo_fence

    for name in ("BOARDMAN_ENV", "APP_ENV", "ENVIRONMENT", "NETWORK", "REAL_MONEY_ENABLED",
                 "CLAW_DEFAULT_CHAIN", "BOARDMAN_SETTLEMENT_RAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAW_DEFAULT_CHAIN", "avalanche")
    assert geo_fence.is_production() is False
    monkeypatch.setenv("CLAW_DEFAULT_CHAIN", "avalanche_mainnet")
    assert geo_fence.is_production() is True
    monkeypatch.setenv("CLAW_DEFAULT_CHAIN", "arc_mainnet")
    assert geo_fence.is_production() is True
