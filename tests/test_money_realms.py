"""Money realms: real money (humans, Arc mainnet) never mixes with practice
money (arena, Arc testnet). See src/backend/services/realms.py."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.channels_fixtures import world  # noqa: F401
from tests.channels_match_fixtures import mworld, wa_player  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
ADA = "2348011112222"
BOLA = "2348033334444"
ESCROW_MAINNET = "0x" + "e1" * 20
LIVE_KEY = "LIVE_API_KEY:abc:def"
TEST_KEY = "TEST_API_KEY:abc:def"
KS_SECRET = "test-keystore-secret-" + "y" * 32


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def realms():
    from gaming.src.backend.services import chains, realms as mod

    chains.reload_chains_config()
    yield mod
    chains.reload_chains_config()


@pytest.fixture()
def humans_live(monkeypatch, realms):
    """REAL_MONEY_ENABLED + an Arc mainnet escrow address: humans are live."""
    from gaming.src.backend.services import chains

    monkeypatch.setenv("REAL_MONEY_ENABLED", "1")
    monkeypatch.setenv("BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET", ESCROW_MAINNET)
    chains.reload_chains_config()
    assert realms.humans_live()
    yield realms
    monkeypatch.delenv("BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET", raising=False)
    chains.reload_chains_config()


# ── chains and realm chains ──────────────────────────────────────────────────


def test_every_chain_declares_its_network(realms):
    from gaming.src.backend.services.chains import load_chains_config

    rows = load_chains_config()["chains"]
    assert all(r.get("network") in ("mainnet", "testnet") for r in rows.values())
    assert realms.chain_network("arc") == "testnet"
    assert realms.chain_network("arc_mainnet") == "mainnet"
    assert realms.chain_network("base_mainnet") == "mainnet"
    assert realms.chain_network("no_such_chain") == "mainnet"  # unknown = real (fail closed)


def test_realm_chains_default_and_refuse_the_wrong_network(realms, monkeypatch):
    assert realms.arena_chain() == "arc"
    assert realms.humans_chain() == "arc_mainnet"
    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "arc_mainnet")
    with pytest.raises(realms.RealmMisconfigured):
        realms.arena_chain()
    monkeypatch.delenv("BOARDMAN_ARENA_CHAIN")
    monkeypatch.setenv("BOARDMAN_HUMANS_CHAIN", "arc")
    with pytest.raises(realms.RealmMisconfigured):
        realms.humans_chain()


def test_legacy_default_chain_is_never_real(realms, monkeypatch):
    from gaming.src.backend.services import chains

    monkeypatch.setenv("CLAW_ENABLED_CHAINS", "arc,arc_mainnet")
    monkeypatch.setenv("CLAW_DEFAULT_CHAIN", "arc_mainnet")
    chains.reload_chains_config()
    assert chains.default_chain_id() == "arc"


def test_humans_not_live_until_switch_and_escrow(realms, monkeypatch):
    from gaming.src.backend.services import chains

    assert not realms.humans_live()
    assert realms.new_challenge_chain() == "arc"
    with pytest.raises(realms.RealmViolation):
        realms.resolve_challenge_chain("arc_mainnet")
    monkeypatch.setenv("REAL_MONEY_ENABLED", "1")
    chains.reload_chains_config()
    assert not realms.humans_live()  # no escrow address yet
    assert realms.new_challenge_chain() == "arc"


def test_humans_live_routes_new_challenges_to_mainnet(humans_live):
    realms = humans_live
    assert realms.new_challenge_chain() == "arc_mainnet"
    assert realms.resolve_challenge_chain(None) == "arc_mainnet"
    assert realms.resolve_challenge_chain("arc") == "arc"  # explicit practice stays practice
    with pytest.raises(realms.RealmViolation):
        realms.resolve_challenge_chain("base_mainnet")


def test_escrow_version_real_chain_ignores_testnet_override(humans_live, monkeypatch):
    from gaming.src.backend.services.chains import escrow_version

    monkeypatch.setenv("BOARDMAN_ESCROW_VERSION", "1")
    assert escrow_version("arc_mainnet") == 2
    assert escrow_version("arc") == 1


# ── Circle credentials ───────────────────────────────────────────────────────


def test_circle_credentials_follow_the_blockchain(realms, monkeypatch):
    monkeypatch.setenv("CIRCLE_API_KEY", TEST_KEY)
    monkeypatch.setenv("CIRCLE_ENTITY_SECRET", "a" * 64)
    monkeypatch.setenv("CIRCLE_WALLET_SET_ID", "set-test")
    monkeypatch.setenv("CIRCLE_API_KEY_LIVE", LIVE_KEY)
    monkeypatch.setenv("CIRCLE_ENTITY_SECRET_LIVE", "b" * 64)
    monkeypatch.setenv("CIRCLE_WALLET_SET_ID_LIVE", "set-live")
    live = realms.circle_credentials("ARC")
    test = realms.circle_credentials("ARC-TESTNET")
    assert (live.realm, live.api_key, live.wallet_set_id) == ("humans", LIVE_KEY, "set-live")
    assert (test.realm, test.api_key, test.wallet_set_id) == ("arena", TEST_KEY, "set-test")
    assert realms.circle_credentials("BASE").realm == "humans"
    assert realms.circle_credentials("BASE-SEPOLIA").realm == "arena"


def test_circle_never_falls_back_across_realms(realms, monkeypatch):
    from backend.circle_wallet_service import CircleWalletService

    monkeypatch.setenv("CIRCLE_API_KEY", TEST_KEY)
    monkeypatch.setenv("CIRCLE_ENTITY_SECRET", "a" * 64)
    monkeypatch.setenv("CIRCLE_WALLET_SET_ID", "set-test")
    svc = CircleWalletService(blockchain="ARC")
    assert svc.api_key is None and svc.entity_secret is None and svc.wallet_set_id is None
    out = svc.create_custodial_wallet_for_user("p1")
    assert out["success"] is False and "CIRCLE_WALLET_SET_ID_LIVE" in out["error"]
    assert CircleWalletService(blockchain="ARC-TESTNET").api_key == TEST_KEY


def test_circle_refuses_a_key_from_the_other_environment(realms, monkeypatch):
    from backend.circle_wallet_service import CircleWalletService

    monkeypatch.setenv("CIRCLE_API_KEY", LIVE_KEY)
    with pytest.raises(realms.RealmViolation):
        CircleWalletService(blockchain="ARC-TESTNET")
    monkeypatch.setenv("CIRCLE_API_KEY_LIVE", TEST_KEY)
    with pytest.raises(realms.RealmViolation):
        CircleWalletService(blockchain="ARC")


# ── profile balances ─────────────────────────────────────────────────────────


def test_preferred_chain_is_always_practice(realms, monkeypatch):
    from gaming.src.backend.services import clawstation_circle as cc

    monkeypatch.setattr(cc._SupabaseProfileStore, "get_profile",
                        AsyncMock(return_value={"gaming_preferred_chain": "arc_mainnet"}))
    assert run(cc.get_preferred_chain("p1")) == "arc"
    with pytest.raises(realms.RealmViolation):
        run(cc.set_preferred_chain("p1", "arc_mainnet"))


def test_real_balance_is_on_chain_only_never_the_practice_overlay(realms, monkeypatch):
    from gaming.src.backend.services import clawstation_circle as cc
    from gaming.src.backend.services.play_adjust import add_adjust

    pid = "11111111-1111-1111-1111-111111111111"
    add_adjust(pid, "50", reason="spectator payout (practice)")
    reads: list[tuple[str, str]] = []

    async def on_chain(address, chain):
        reads.append((address, chain))
        return Decimal("3"), None

    monkeypatch.setattr(cc, "_on_chain_usdc_async", on_chain)
    monkeypatch.setattr(cc, "get_real_play_wallet", lambda u, c: {"address": "0xREAL", "wallet_id": "w-real"})
    monkeypatch.setattr(cc, "get_deposit_address", AsyncMock(return_value="0xpractice"))
    assert run(cc.get_usdc_balance(pid, chain_id="arc_mainnet")) == Decimal("3")
    assert run(cc.get_usdc_balance(pid, chain_id="arc")) == Decimal("53")
    assert reads[0] == ("0xREAL", "arc_mainnet") and reads[1] == ("0xpractice", "arc")
    summary = run(cc.get_balance_summary(pid, chain_id="arc_mainnet"))
    assert summary["spendable_usdc"] == Decimal("3") and summary["adjust_usdc"] == 0
    assert summary["realm"] == "humans" and summary["money"] == "real"


def test_real_balance_without_a_wallet_is_zero_and_creates_nothing(realms, monkeypatch):
    from gaming.src.backend.services import clawstation_circle as cc

    monkeypatch.setattr(cc, "_circle_for_chain", lambda c: pytest.fail("no Circle call to read a balance"))
    assert run(cc.get_usdc_balance("22222222-2222-2222-2222-222222222222", chain_id="arc_mainnet")) == 0


def test_real_wallet_is_created_once_apart_from_the_practice_wallet(realms, monkeypatch):
    from gaming.src.backend.services import clawstation_circle as cc

    pid = "33333333-3333-3333-3333-333333333333"
    created: list[dict] = []

    class FakeCircle:
        def create_custodial_wallet_for_user(self, profile_id, phone, *, account_type, idempotency_key):
            created.append({"account_type": account_type, "key": idempotency_key})
            return {"success": True, "wallet_id": "w-live-1", "wallet_address": "0xAbC" + "0" * 37}

    monkeypatch.setattr(cc, "_circle_for_chain", lambda c: FakeCircle())
    monkeypatch.setattr(cc._SupabaseProfileStore, "get_profile",
                        AsyncMock(side_effect=AssertionError("practice profile columns untouched")))
    monkeypatch.setattr(cc._SupabaseProfileStore, "set_chain_wallet",
                        AsyncMock(side_effect=AssertionError("practice profile columns untouched")))
    w1 = run(cc.ensure_user_wallet(pid, chain_id="arc_mainnet"))
    w2 = run(cc.ensure_user_wallet(pid, chain_id="arc_mainnet"))
    assert w1["wallet_id"] == w2["wallet_id"] == "w-live-1"
    assert w1["realm"] == "humans" and w1["chain_id"] == "arc_mainnet"
    assert len(created) == 1 and created[0]["account_type"] == "SCA"


def test_profile_wallet_columns_refuse_a_real_chain(realms):
    from gaming.src.backend.services import clawstation_circle as cc

    with pytest.raises(realms.RealmViolation):
        run(cc._SupabaseProfileStore.set_chain_wallet("p1", "arc_mainnet", "w", "0x" + "1" * 40))


# ── arena paths refuse real money ────────────────────────────────────────────


def test_web_spectator_pull_uses_the_practice_wallet_only(realms, monkeypatch):
    from gaming.src.backend.api import rematch_web
    from gaming.src.backend.services import clawstation_circle as cc

    seen: list[str] = []

    async def bal(pid, chain_id=None):
        seen.append(chain_id)
        return Decimal("100")

    async def wallet(pid, chain_id=None):
        seen.append(chain_id)
        return {"wallet_id": "w-practice", "chain_id": chain_id}

    svc = MagicMock()
    svc.transfer_usdc.return_value = {"success": True, "tx_hash": "0x1"}
    monkeypatch.setattr(cc, "get_usdc_balance", bal)
    monkeypatch.setattr(cc, "ensure_user_wallet", wallet)
    monkeypatch.setattr("backend.circle_wallet_service.CircleWalletService", lambda **k: svc)
    monkeypatch.setattr(rematch_web, "_house_pull_dest", lambda: "0x" + "9" * 40)
    run(rematch_web._pull_play_usdc("p1", 1.0))
    assert seen == ["arc", "arc"]

    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "arc_mainnet")
    with pytest.raises(realms.RealmMisconfigured):
        run(rematch_web._pull_play_usdc("p1", 1.0))


def test_wallet_bridge_reads_and_debits_practice_only(realms, monkeypatch):
    from gaming.src.backend.services import clawstation_circle as cc
    from gaming.src.stack.agentic import wallet_bridge

    seen: list[str] = []

    async def strict(pid, chain_id=None):
        seen.append(chain_id)
        return Decimal("5"), None

    monkeypatch.setattr(cc, "get_usdc_balance_strict", strict)
    assert run(wallet_bridge.read_play_chain_usdc("p1")) == Decimal("5")
    assert seen == ["arc"]
    monkeypatch.setenv("BOARDMAN_ARENA_CHAIN", "arc_mainnet")
    with pytest.raises(realms.RealmMisconfigured):
        wallet_bridge.deposit("p1", "1", "idem-12345", chain_usdc=Decimal("5"))


def test_agentic_signer_refuses_real_chains(realms):
    from gaming.src.stack.agentic import onchain

    with pytest.raises(realms.RealmViolation):
        onchain._chain_config("arc_mainnet")
    for real_id in (5042, 8453):
        with pytest.raises(realms.RealmViolation):
            realms.assert_practice_evm(real_id, path="test")
    realms.assert_practice_evm(5042002, path="test")
    w3 = MagicMock()
    w3.eth.chain_id = 5042
    with pytest.raises(realms.RealmViolation):
        onchain._send(w3, MagicMock(address="0x" + "1" * 40), {}, "resolve")


def test_spectator_pool_and_afm_refuse_real_chains(realms, monkeypatch):
    from gaming.src.backend.services import spectator_escrow
    from gaming.src.stack.agentic.games.football_managers import agent_market

    monkeypatch.setenv("SPECTATOR_CHAIN", "arc_mainnet")
    with pytest.raises(realms.RealmViolation):
        run(spectator_escrow.deposit_to_pool("p1", "agm_123", "a", Decimal("1")))
    with pytest.raises(realms.RealmViolation):
        agent_market._circle("arc_mainnet")


def test_settlement_rail_can_never_be_real(realms, monkeypatch):
    from gaming.src.backend.services.funding_rails import settlement_rail_id

    monkeypatch.setenv("BOARDMAN_SETTLEMENT_RAIL", "arc_mainnet")
    assert settlement_rail_id() == "arc"


# ── real-money paths refuse practice money ───────────────────────────────────


def test_paycrest_off_unless_both_chains_are_real(realms, monkeypatch):
    from gaming.src.backend.services.paycrest import config

    monkeypatch.setenv("PAYCREST_ENABLED", "1")
    monkeypatch.setenv("REAL_MONEY_ENABLED", "1")
    monkeypatch.setenv("PAYCREST_API_KEY", "k")
    assert config.enabled()
    monkeypatch.setenv("PAYCREST_SETTLEMENT_CHAIN", "arc")  # testnet USDC must never reach a bank
    assert not config.enabled()
    monkeypatch.delenv("PAYCREST_SETTLEMENT_CHAIN")
    monkeypatch.setenv("PAYCREST_DELIVERY_CHAIN", "base")
    assert not config.enabled()


def test_cctp_never_crosses_networks(realms):
    from gaming.src.backend.services.bridge import cctp

    kw = dict(idempotency_key="k1", profile_id="p1", amount=Decimal("1"), from_wallet_id="w", mint_recipient="0x1")
    with pytest.raises(realms.RealmViolation):
        cctp.start(kind="onramp_sweep", src_chain="base", dst_chain="arc_mainnet", **kw)
    with pytest.raises(realms.RealmViolation):
        cctp.start(kind="offramp_out", src_chain="arc", dst_chain="base", **kw)


# ── resolver keys ────────────────────────────────────────────────────────────


def test_mainnet_resolver_comes_from_the_keystore_only(realms, monkeypatch, tmp_path):
    from gaming.src.stack.agentic.keystore import get_keystore

    monkeypatch.setenv("BOARDMAN_KEYSTORE_SECRET", KS_SECRET)
    monkeypatch.setenv("BOARDMAN_KEYSTORE_DIR", str(tmp_path / "ks"))
    with pytest.raises(realms.RealmMisconfigured):
        realms.resolver_private_key("arc_mainnet")  # not configured
    monkeypatch.setenv("BOARDMAN_RESOLVER_KEY_MAINNET", "0x" + "ab" * 32)
    with pytest.raises(realms.RealmMisconfigured, match="plaintext"):
        realms.resolver_private_key("arc_mainnet")
    addr = get_keystore().create("resolver_arc_mainnet")
    monkeypatch.setenv("BOARDMAN_RESOLVER_KEY_MAINNET", "resolver_arc_mainnet")
    from eth_account import Account

    pk = realms.resolver_private_key("arc_mainnet")
    assert Account.from_key(pk).address == addr
    monkeypatch.setenv("BOARDMAN_RESOLVER_KEY", pk)  # the testnet resolver must differ
    with pytest.raises(realms.RealmMisconfigured):
        realms.resolver_private_key("arc_mainnet")


def test_real_chain_blockchain_layer_refuses_env_keys(realms, monkeypatch):
    from backend.blockchain_layer import BlockchainLayer

    monkeypatch.setenv("ADMIN_PRIVATE_KEY", "0x" + "cd" * 32)
    with pytest.raises(ValueError, match="keystore"):
        BlockchainLayer(chain_id="arc_mainnet", rpc_url="http://127.0.0.1:9", evm_chain_id=5042, real_money=True)


# ── stake caps ───────────────────────────────────────────────────────────────


def test_caps_per_match_and_rolling_day(realms, monkeypatch):
    from gaming.src.backend.services import stake_caps as caps

    assert caps.max_stake_usdc() == Decimal("25") and caps.daily_stake_usdc() == Decimal("100")
    with pytest.raises(caps.StakeCapExceeded) as e:
        caps.reserve("p1", "arc_mainnet", "c0", Decimal("26"))
    assert e.value.kind == "per_match"
    t = 1_000_000_000_000
    for i in range(4):
        assert caps.reserve("p1", "arc_mainnet", f"c{i + 1}", Decimal("25"), now=t + i)
    assert caps.reserve("p1", "arc_mainnet", "c1", Decimal("25"), now=t + 10) is False  # a retry
    with pytest.raises(caps.StakeCapExceeded) as e:
        caps.reserve("p1", "arc_mainnet", "c5", Decimal("2"), now=t + 20)
    assert e.value.kind == "daily" and "$100.00" in str(e.value)
    assert caps.check("p1", "arc_mainnet", Decimal("2"), now=t + 20)
    assert caps.release("p1", "c4", reason="lock failed")
    assert caps.reserve("p1", "arc_mainnet", "c5", Decimal("25"), now=t + 30)
    # the window rolls: a day later the old stakes no longer count
    assert caps.check("p1", "arc_mainnet", Decimal("25"), now=t + caps.WINDOW_MS + 31) is None
    assert caps.used_today("p2") == 0
    assert caps.totals_by_chain() == [{"realm": "humans", "chain": "arc_mainnet", "count": 4, "usdc": "100.00"}]


def test_caps_ignore_practice_and_follow_env(realms, monkeypatch):
    from gaming.src.backend.services import stake_caps as caps

    assert caps.reserve("p1", "arc", "c1", Decimal("25")) is False
    assert caps.check("p1", "arc", Decimal("25")) is None
    monkeypatch.setenv("BOARDMAN_HUMANS_MAX_STAKE_USDC", "10")
    monkeypatch.setenv("BOARDMAN_HUMANS_DAILY_STAKE_USDC", "15")
    assert "$10.00 per player" in caps.check("p1", "arc_mainnet", Decimal("11"))
    caps.reserve("p1", "arc_mainnet", "c2", Decimal("10"))
    assert "Daily real-money limit is $15.00" in caps.check("p1", "arc_mainnet", Decimal("10"))
    monkeypatch.setenv("BOARDMAN_HUMANS_MAX_STAKE_USDC", "nonsense")
    assert caps.max_stake_usdc() == Decimal("25")


def test_migrations_match_the_modules():
    from gaming.src.backend.services import stake_caps
    from gaming.src.backend.services.paycrest import store

    mig = ROOT / "supabase" / "migrations"
    assert (mig / "20261020120000_realm_stakes.sql").read_text() == stake_caps.postgres_migration_sql()
    assert (mig / "20261020120100_paycrest_order_chain.sql").read_text() == store.postgres_upgrade_migration_sql()


def test_paycrest_orders_carry_their_chain():
    from gaming.src.backend.services.paycrest import store

    order, created = store.create_order(idempotency_key="bm-test-1", direction="onramp", profile_id="p1",
                                        status="quoted", chain="arc_mainnet")
    assert created and order["chain"] == "arc_mainnet"


# ── the escrow chokepoint ───────────────────────────────────────────────────


def _escrow_world(monkeypatch, *, chain: str, amount: Decimal = Decimal("10")):
    from gaming.src.backend.services import clawstation_escrow as esc

    ch = {"id": "aaaaaaaa-0000-0000-0000-000000000001", "creator_id": "p1", "opponent_id": "p2",
          "status": "accepted", "amount_usdc": float(amount), "settlement_chain": chain}
    monkeypatch.setattr(esc, "_load_challenge", lambda cid: dict(ch))
    monkeypatch.setattr(esc, "_find_existing_audit", lambda *a, **k: None)
    monkeypatch.setattr(esc, "_record_audit", lambda *a, **k: None)
    monkeypatch.setattr(esc, "_update_challenge", lambda *a, **k: None)
    monkeypatch.setattr(esc, "_load_profile_wallet", lambda pid, c: (f"w-{pid}", ""))
    addrs = {"p1": "0x" + "a1" * 20, "p2": "0x" + "b2" * 20}

    async def ensure(pid, chain_id=None):
        return {"wallet_id": f"w-{pid}", "address": addrs[pid], "blockchain": "ARC", "chain_id": chain_id}

    monkeypatch.setattr(esc, "ensure_user_wallet", ensure)
    circle = MagicMock()
    circle.approve_usdc_transfer.return_value = {"success": True, "transaction_id": "ta"}
    circle.execute_contract_function.return_value = {"success": True, "transaction_id": "tc", "tx_hash": "0x2"}
    circle.wait_for_transaction_async = AsyncMock(return_value={"success": True, "tx_hash": "0x2"})
    monkeypatch.setattr(esc, "_circle", lambda c: circle)
    return esc, ch, circle, addrs


def test_real_lock_over_the_cap_moves_nothing(humans_live, monkeypatch):
    esc, ch, circle, _ = _escrow_world(monkeypatch, chain="arc_mainnet", amount=Decimal("30"))
    with pytest.raises(esc.EscrowError, match="capped"):
        run(esc.approve_and_create_match("p1", ch["id"], Decimal("30")))
    circle.approve_usdc_transfer.assert_not_called()
    circle.execute_contract_function.assert_not_called()


def test_real_lock_signs_a_v2_permit_with_the_mainnet_resolver(humans_live, monkeypatch):
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_utils import to_checksum_address

    from gaming.src.backend.services import stake_caps

    esc, ch, circle, addrs = _escrow_world(monkeypatch, chain="arc_mainnet")
    resolver = Account.create()
    monkeypatch.setattr("gaming.src.backend.services.realms.resolver_private_key",
                        lambda chain: resolver.key.hex() if chain == "arc_mainnet" else pytest.fail(chain))
    run(esc.approve_and_create_match("p1", ch["id"], Decimal("10")))
    args = circle.execute_contract_function.call_args.args
    assert args[2] == "createMatch(bytes32,address,uint256,uint256,bytes)"
    mid, p2, stake, deadline, sig = args[3]
    assert p2.lower() == addrs["p2"] and stake == "10000000"
    msg = encode_typed_data(full_message={
        "types": {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                   {"name": "chainId", "type": "uint256"},
                                   {"name": "verifyingContract", "type": "address"}],
                  "CreateMatch": [{"name": "matchId", "type": "bytes32"}, {"name": "player1", "type": "address"},
                                  {"name": "player2", "type": "address"}, {"name": "stake", "type": "uint256"},
                                  {"name": "deadline", "type": "uint256"}]},
        "primaryType": "CreateMatch",
        "domain": {"name": "BoardmanEscrow", "version": "2", "chainId": 5042,
                   "verifyingContract": to_checksum_address(ESCROW_MAINNET)},
        "message": {"matchId": bytes.fromhex(mid[2:]), "player1": to_checksum_address(addrs["p1"]),
                    "player2": p2, "stake": 10_000_000, "deadline": int(deadline)}})
    assert Account.recover_message(msg, signature=bytes.fromhex(sig[2:])) == resolver.address
    assert stake_caps.used_today("p1") == Decimal("10.00")


def test_failed_real_lock_before_submit_gives_the_cap_back(humans_live, monkeypatch):
    from gaming.src.backend.services import stake_caps

    esc, ch, circle, _ = _escrow_world(monkeypatch, chain="arc_mainnet")
    # no mainnet resolver configured: refused before any transaction
    with pytest.raises(esc.EscrowError, match="Nothing was charged"):
        run(esc.approve_and_create_match("p1", ch["id"], Decimal("10")))
    circle.approve_usdc_transfer.assert_not_called()
    assert stake_caps.used_today("p1") == 0
    # approve fails: still nothing submitted to the escrow
    monkeypatch.setattr("gaming.src.backend.services.realms.resolver_private_key", lambda c: "0x" + "12" * 32)
    circle.approve_usdc_transfer.return_value = {"success": False, "error": "nope"}
    with pytest.raises(esc.EscrowError):
        run(esc.approve_and_create_match("p1", ch["id"], Decimal("10")))
    assert stake_caps.used_today("p1") == 0
    # the escrow call was submitted but not confirmed: the stake keeps counting
    circle.approve_usdc_transfer.return_value = {"success": True, "transaction_id": "ta"}
    circle.wait_for_transaction_async = AsyncMock(side_effect=[{"success": True}, {"success": False, "error": "t/o"}])
    with pytest.raises(esc.EscrowError):
        run(esc.approve_and_create_match("p1", ch["id"], Decimal("10")))
    assert stake_caps.used_today("p1") == Decimal("10.00")


def test_practice_lock_is_untouched_by_caps_and_stays_v1(realms, monkeypatch):
    esc, ch, circle, _ = _escrow_world(monkeypatch, chain="arc", amount=Decimal("25"))
    monkeypatch.setattr(esc, "_require_escrow", lambda c: "0x" + "ee" * 20)
    run(esc.approve_and_create_match("p1", ch["id"], Decimal("25")))
    assert circle.execute_contract_function.call_args.args[2] == "createMatch(bytes32,uint256)"


# ── geo fence ────────────────────────────────────────────────────────────────


def _start_fc_mobile(wa):
    from gaming.src.backend.services.game_catalog import list_games

    run(wa.text(ADA, "challenge"))
    run(wa.tap(ADA, "Mobile"))
    run(wa.tap(ADA, "More…"))
    pos = [g["game_id"] for g in list_games(category="mobile")].index("mobile.fc_mobile") + 1
    run(wa.text(ADA, str(pos)))


def test_whatsapp_real_money_challenge_shows_caps_and_tags_the_chain(mworld, humans_live, monkeypatch):
    from gaming.src.channels.fake.adapter import FakeChannel

    monkeypatch.setenv("BOARDMAN_HUMANS_MAX_STAKE_USDC", "5")
    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    wa_player(world, BOLA, "bola")
    _start_fc_mobile(wa)
    text = wa.last_text(ADA)
    assert "($2 to $5)" in text and "Real money" in text and "$100 a day" in text
    assert [label for _, label in wa.offered(ADA)] == ["$2", "$5"]
    run(wa.text(ADA, "8"))
    assert "capped at $5.00" in wa.last_text(ADA)
    run(wa.tap(ADA, "$5"))
    run(wa.text(ADA, "@bola"))
    assert "Real money" in wa.last_text(ADA)
    run(wa.tap(ADA, "Send it"))
    rows = world.sb.challenges()
    assert rows and rows[-1].get("settlement_chain") == "arc_mainnet"


def test_whatsapp_practice_challenge_before_real_money_is_live(mworld):
    from gaming.src.channels.fake.adapter import FakeChannel

    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    _start_fc_mobile(wa)
    assert "Practice chips" in wa.last_text(ADA)


def test_real_money_turns_on_strict_geo_fence(monkeypatch):
    from gaming.src.backend.middleware import geo_fence

    assert not geo_fence.strict_mode()
    monkeypatch.setenv("REAL_MONEY_ENABLED", "1")
    assert geo_fence.strict_mode()
