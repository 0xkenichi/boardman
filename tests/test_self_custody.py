"""Self-custody passkey wallets against a fake chain. No network, no bundler:
the "browser" here is the test, which plays the role of the passkey page by
posting a tx hash, and the fake chain decides what really happened."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from eth_abi import decode
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient

from gaming.src.backend.services.self_custody import calls as C
from gaming.src.backend.services.self_custody import chain, config, intents, routing, setup, store, wallets
from gaming.src.backend.services.self_custody.intents import IntentRefused
from gaming.src.channels.core import ids, withdraw_links
from gaming.src.channels.fake.adapter import FakeChannel
from tests.channels_fixtures import DEST, PLAY_ADDR, world  # noqa: F401
from tests.channels_match_fixtures import mworld, tg_player, wa_player  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
MASTER = "test-self-custody-master"
ADA, BOLA = "2348011112222", "2348033334444"
RESOLVER = Account.from_key("0x" + "11" * 32)
ADA_SA = "0x" + "5a" * 20
BOLA_SA = "0x" + "5b" * 20
CRED = "cred_ada_0123456789"


def run(coro):
    return asyncio.run(coro)


def h(n: int) -> str:
    return "0x" + f"{n:064x}"


class FakeChain:
    """Receipts and logs a test puts there; balances per account."""

    def __init__(self) -> None:
        self.block = 1_000
        self.version = 2
        self.balances: dict[str, int] = {}
        self.receipts: dict[str, dict] = {}
        self.all_logs: list[dict] = []

    def block_number(self) -> int:
        return self.block

    def receipt(self, tx_hash: str):
        return self.receipts.get(tx_hash.lower())

    def logs(self, address, topics, from_block):
        out = []
        for lg in self.all_logs:
            if lg["address"].lower() != address.lower() or lg["blockNumber"] < from_block:
                continue
            if all(t is None or (i < len(lg["topics"]) and lg["topics"][i] == t.lower())
                   for i, t in enumerate(topics)):
                out.append(lg)
        return out

    def usdc_balance(self, usdc, account):
        return self.balances.get(account.lower(), 0)

    def escrow_version(self, escrow):
        return self.version

    # what the chain would emit
    def land(self, tx: str, logs: list[dict], status: int = 1) -> None:
        self.block += 1
        for lg in logs:
            lg.update(transactionHash=tx, blockNumber=self.block)
        self.receipts[tx.lower()] = {"status": status, "blockNumber": self.block, "transactionHash": tx,
                                     "logs": logs}
        if status == 1:
            self.all_logs.extend(logs)


def created_log(escrow, cid, account, raw):
    return {"address": escrow, "topics": [C.MATCH_CREATED_TOPIC, C.match_id_hex(cid).lower(), C.addr_topic(account)],
            "data": "0x" + f"{raw:064x}"}


def joined_log(escrow, cid, account):
    return {"address": escrow, "topics": [C.MATCH_JOINED_TOPIC, C.match_id_hex(cid).lower(), C.addr_topic(account)],
            "data": "0x"}


def transfer_log(usdc, frm, to, raw):
    return {"address": usdc, "topics": [C.TRANSFER_TOPIC, C.addr_topic(frm), C.addr_topic(to)],
            "data": "0x" + f"{raw:064x}"}


@pytest.fixture
def sc(mworld, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SELF_CUSTODY_WALLETS_ENABLED", "1")
    monkeypatch.setattr("gaming.src.stack.agentic.onchain.load_resolver_key", lambda: RESOLVER.key.hex())
    fake = FakeChain()
    chain.set_reader(fake)
    s = config.chain_settings()
    mworld.chain = fake
    mworld.escrow_addr = s["escrow"]
    mworld.usdc = s["usdc"]
    yield mworld
    chain.set_reader(None)


def _token(url: str) -> str:
    return url.rsplit("/", 1)[-1].rsplit("t=", 1)[-1]


def _accepted(world, *, ada_passkey=True, bola_passkey=False):
    from gaming.src.channels.core.actions.matches import insert_challenge

    ada = wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola", in_window=True)
    if ada_passkey:
        wallets.register(ada["id"], ADA_SA, CRED)
        world.chain.balances[ADA_SA.lower()] = C.to_raw(Decimal("40"))
    if bola_passkey:
        wallets.register(bola["id"], BOLA_SA, "cred_bola_0123456789")
        world.chain.balances[BOLA_SA.lower()] = C.to_raw(Decimal("40"))
    ch = insert_challenge(creator_id=ada["id"], opponent_id=bola["id"], amount=Decimal("5"),
                          game="mobile.fc_mobile", visibility="private")
    world.sb.challenge(ch["id"]).update(status="accepted")
    from gaming.src.channels.core.actions import matches as svc

    return ada, bola, svc.load(ch["id"])


def _prepare(world, profile, ch):
    return run(intents.prepare_lock(profile["id"], ch, channel="whatsapp", external_id=ADA))


def _submit(p, tx, *, amount="5", cid=None, user_op=None):
    return intents.submit(p.token, tx_hash=tx, user_op_hash=user_op, amount=amount,
                          challenge_id=cid if cid is not None else p.intent["challenge_id"])


# ── flag off: nothing changes ────────────────────────────────────────────────


def test_flag_off_is_invisible(mworld, monkeypatch):  # noqa: F811
    world = mworld
    monkeypatch.delenv("SELF_CUSTODY_WALLETS_ENABLED", raising=False)
    ada = wa_player(world, ADA, "ada", in_window=True)
    assert routing.lock_route(ada["id"], {"id": "x", "creator_id": ada["id"]}) == routing.CUSTODIAL
    assert routing.withdraw_route(ada["id"]) == routing.CUSTODIAL
    assert routing.account(ada["id"]) is None
    with pytest.raises(IntentRefused) as e:
        setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)
    assert e.value.kind == "off"
    # the chat lock is still the in-chat Yes/No prompt
    _, _, ch = _accepted_off(world)
    wa = FakeChannel("wa")
    run(wa.tap_id(ADA, ids.encode("match", "lock", ch["id"])))
    assert "Lock $5.00 USDC?" in wa.last_text(ADA)
    assert [lb for _, lb in wa.offered(ADA)] == ["Yes, lock it", "No"]
    # wallet screen has no passkey section
    run(wa.text(ADA, "balance"))
    assert "passkey" not in wa.last_text(ADA).lower()


def _accepted_off(world):
    from gaming.src.channels.core.actions import matches as svc
    from gaming.src.channels.core.actions.matches import insert_challenge

    bola = wa_player(world, BOLA, "bola")
    ada = next(p for p in world.sb.tables["profiles"] if p.get("gaming_tag") == "ada")
    ch = insert_challenge(creator_id=ada["id"], opponent_id=bola["id"], amount=Decimal("5"),
                          game="mobile.fc_mobile", visibility="private")
    world.sb.challenge(ch["id"]).update(status="accepted")
    return ada, bola, svc.load(ch["id"])


def test_routes_404_when_off(world, monkeypatch):  # noqa: F811
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    from gaming.src.backend.main import create_app

    c = TestClient(create_app())
    hdr = {"X-Boardman-Key": MASTER}
    assert c.get("/api/self-custody/setup", headers=hdr).status_code == 404
    assert c.get("/api/self-custody/approve/" + "a" * 43, headers=hdr).status_code == 404
    assert c.post("/api/self-custody/approve/" + "a" * 43, headers=hdr,
                  json={"tx_hash": h(1), "amount": "5"}).status_code == 404


def test_migration_matches_store_module():
    path = ROOT / "supabase" / "migrations" / "20261018130000_self_custody_intents.sql"
    assert path.read_text() == store.postgres_migration_sql()


# ── wallet setup ─────────────────────────────────────────────────────────────


def test_setup_link_registers_once_and_never_replaces(sc):
    world = sc
    ada = wa_player(world, ADA, "ada", in_window=True)
    url, _ = setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)
    assert url.startswith("https://boardman.test/app/wallet/setup?t=")
    tok = _token(url)
    v = setup.view(tok)
    assert v["ok"] and v["wallet"] is None and v["username"] == "Boardman @ada"
    assert v["chain"]["modular_path"] == "arcTestnet" and v["chain"]["evm_chain_id"] == 5042002
    out = setup.register(tok, address=ADA_SA, credential_id=CRED)
    assert out["created"] and out["address"].lower() == ADA_SA
    # single use
    with pytest.raises(IntentRefused) as e:
        setup.register(tok, address=ADA_SA, credential_id=CRED)
    assert e.value.kind == "used"
    # a second link cannot swap the address
    tok2 = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    with pytest.raises(IntentRefused) as e:
        setup.register(tok2, address="0x" + "66" * 20, credential_id=CRED)
    assert e.value.kind == "exists"
    assert wallets.address(ada["id"]).lower() == ADA_SA
    # stored in the existing per-player wallet table, no key material
    from gaming.src.backend.services.paycrest import store as pstore

    row = pstore.get_wallet(ada["id"], "arc/passkey")
    assert row["wallet_id"] == f"passkey:{CRED}" and row["account_type"] == "circle_msca_passkey"


def test_setup_refuses_someone_elses_address_and_wrong_session(sc):
    world = sc
    ada = wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola")
    wallets.register(bola["id"], BOLA_SA, "cred_bola_0123456789")
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    with pytest.raises(IntentRefused) as e:
        setup.view(tok, caller=bola["id"])
    assert e.value.kind == "wrong_profile"
    with pytest.raises(IntentRefused) as e:
        setup.register(tok, address=BOLA_SA, credential_id=CRED)
    assert e.value.kind == "taken"
    # no token and no session: refused
    with pytest.raises(IntentRefused):
        setup.view(None)


# ── lock: prepare → approve → confirm on chain ───────────────────────────────


def test_creator_lock_calls_are_exact_and_permit_binds_both_players(sc):
    world = sc
    ada, bola, ch = _accepted(world)
    p = _prepare(world, ada, ch)
    assert p.url.startswith("https://boardman.test/app/approve/")
    calls = p.intent["calls"]
    assert [c["to"].lower() for c in calls] == [world.usdc.lower(), world.escrow_addr.lower()]
    spender, amount = decode(["address", "uint256"], bytes.fromhex(calls[0]["data"][10:]))
    assert spender.lower() == world.escrow_addr.lower() and amount == 5_000_000
    assert calls[1]["data"].startswith("0x" + C.selector("createMatch(bytes32,address,uint256,uint256,bytes)").hex())
    mid, p2, stake, deadline, sig = decode(["bytes32", "address", "uint256", "uint256", "bytes"],
                                           bytes.fromhex(calls[1]["data"][10:]))
    assert mid == C.match_id_bytes32(ch["id"]) and stake == 5_000_000
    assert p2.lower() == PLAY_ADDR.lower()  # bola has no passkey: their Circle wallet is bound
    msg = encode_typed_data(full_message={
        "types": {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                   {"name": "chainId", "type": "uint256"},
                                   {"name": "verifyingContract", "type": "address"}],
                  "CreateMatch": [{"name": "matchId", "type": "bytes32"}, {"name": "player1", "type": "address"},
                                  {"name": "player2", "type": "address"}, {"name": "stake", "type": "uint256"},
                                  {"name": "deadline", "type": "uint256"}]},
        "primaryType": "CreateMatch",
        "domain": {"name": "BoardmanEscrow", "version": "2", "chainId": 5042002,
                   "verifyingContract": C.to_checksum_address(world.escrow_addr)},
        "message": {"matchId": mid, "player1": C.to_checksum_address(ADA_SA), "player2": p2, "stake": stake,
                    "deadline": deadline},
    })
    assert Account.recover_message(msg, signature=sig) == RESOLVER.address
    v = intents.view(p.token)
    assert v["headline"].startswith("Lock 5.00 USDC into escrow for match ")
    assert v["account"].lower() == ADA_SA and v["credential_id"] == CRED and v["match"]["opponent"] == "@bola"


def test_v1_escrow_uses_the_v1_create_call(sc):
    world = sc
    world.chain.version = 1
    ada, _, ch = _accepted(world)
    p = _prepare(world, ada, ch)
    assert p.intent["calls"][1]["data"].startswith("0x" + C.selector("createMatch(bytes32,uint256)").hex())


def test_lock_confirms_only_on_the_real_escrow_event(sc):
    world = sc
    ada, bola, ch = _accepted(world)
    p = _prepare(world, ada, ch)
    # the page claims a hash the chain does not know yet: pending, match untouched
    out = _submit(p, h(1))
    assert out["status"] == "pending"
    assert world.sb.challenge(ch["id"])["status"] == "accepted"
    assert store.get(p.intent["id"])["status"] == "submitted"
    # the tx lands with the escrow's MatchCreated: the watcher confirms
    world.chain.land(h(1), [created_log(world.escrow_addr, ch["id"], ADA_SA, 5_000_000)])
    counts = run(intents.sweep())
    assert counts["confirmed"] == 1
    row = world.sb.challenge(ch["id"])
    assert row["status"] == "creator_locked" and row["creator_lock_tx_hash"] == h(1)
    audit = world.sb.tables["escrow_audit"][-1]
    assert audit["movement"] == "lock_in" and audit["metadata"]["self_custody"] is True
    assert audit["idempotency_key"] == f"approve-create-{ch['id']}"
    # bola is told it is their turn
    assert any("Your turn" in o.body for to, outs in world.wa_dv.session if to == BOLA for o in outs)
    # nothing custodial ran
    assert not [e for e in world.escrow if e[0] in ("create", "join")]
    # idempotent
    assert run(intents.sweep())["confirmed"] == 0


def test_fake_events_and_reverted_txs_never_confirm(sc):
    world = sc
    ada, _, ch = _accepted(world)
    # 1. an event from some other contract with identical topics
    p = _prepare(world, ada, ch)
    world.chain.land(h(2), [created_log("0x" + "99" * 20, ch["id"], ADA_SA, 5_000_000)])
    assert _submit(p, h(2))["status"] == "pending"
    assert world.sb.challenge(ch["id"])["status"] == "accepted"
    # 2. the right contract, but another account / a smaller stake
    p = _prepare(world, ada, ch)
    world.chain.land(h(3), [created_log(world.escrow_addr, ch["id"], BOLA_SA, 5_000_000),
                            created_log(world.escrow_addr, ch["id"], ADA_SA, 1_000_000)])
    assert _submit(p, h(3))["status"] == "pending"
    # 3. a reverted transaction
    p = _prepare(world, ada, ch)
    world.chain.land(h(4), [created_log(world.escrow_addr, ch["id"], ADA_SA, 5_000_000)], status=0)
    out = _submit(p, h(4))
    assert out["status"] == "failed" and not out["ok"]
    run(intents.sweep())
    assert world.sb.challenge(ch["id"])["status"] == "accepted"
    assert "escrow_audit" not in world.sb.tables


def test_closed_tab_still_confirms_from_logs(sc):
    world = sc
    ada, _, ch = _accepted(world)
    p = _prepare(world, ada, ch)
    world.chain.land(h(5), [created_log(world.escrow_addr, ch["id"], ADA_SA, 5_000_000)])
    assert run(intents.sweep())["confirmed"] == 1
    assert store.get(p.intent["id"])["tx_hash"] == h(5)
    assert world.sb.challenge(ch["id"])["status"] == "creator_locked"


def test_one_tx_cannot_confirm_two_intents(sc):
    world = sc
    ada, _, ch = _accepted(world)
    p = _prepare(world, ada, ch)
    world.chain.land(h(6), [created_log(world.escrow_addr, ch["id"], ADA_SA, 5_000_000)])
    assert _submit(p, h(6))["status"] == "confirmed"
    w = intents.prepare_withdraw(ada["id"], DEST, Decimal("1"), channel="whatsapp", external_id=ADA)
    with pytest.raises(IntentRefused) as e:
        intents.submit(w.token, tx_hash=h(6), user_op_hash=None, amount="1", challenge_id=None)
    assert e.value.kind == "taken"


# ── the one-time approve link ────────────────────────────────────────────────


def test_approve_link_single_use_expiry_tamper_and_owner(sc, monkeypatch):
    world = sc
    monkeypatch.setenv("CHANNELS_WITHDRAW_LINKS_PER_HOUR", "50")
    ada, bola, ch = _accepted(world)
    p = _prepare(world, ada, ch)
    # token hashed at rest
    with withdraw_links.store.db().transaction(readonly=True) as tx:
        rows = tx.all("SELECT token_hash, purpose FROM channel_tokens WHERE purpose = 'sc_approve'")
    assert rows == [{"token_hash": withdraw_links.token_hash(p.token), "purpose": "sc_approve"}]
    # another signed-in account
    with pytest.raises(IntentRefused) as e:
        intents.view(p.token, session_profile_id=bola["id"])
    assert e.value.kind == "wrong_profile"
    # tampered amount burns the link
    with pytest.raises(IntentRefused) as e:
        _submit(p, h(7), amount="50")
    assert e.value.kind == "amount_mismatch"
    with pytest.raises(IntentRefused) as e:
        intents.view(p.token)
    assert e.value.kind == "used"
    # tampered match id burns too
    p = _prepare(world, ada, ch)
    with pytest.raises(IntentRefused) as e:
        _submit(p, h(7), cid="another-match")
    assert e.value.kind == "amount_mismatch"
    # single use
    p = _prepare(world, ada, ch)
    _submit(p, h(8))
    with pytest.raises(IntentRefused) as e:
        _submit(p, h(9))
    assert e.value.kind == "used"
    # expiry
    p = run(intents.prepare_lock(ada["id"], ch, channel="whatsapp", external_id=ADA, now_ms=1_000))
    with pytest.raises(IntentRefused):
        intents.view(p.token, now_ms=store.now_ms() + 3_600_000)
    # a newer link replaces an older one
    p1 = _prepare(world, ada, ch)
    p2 = _prepare(world, ada, ch)
    with pytest.raises(IntentRefused) as e:
        intents.view(p1.token)
    assert e.value.kind == "used"
    assert intents.view(p2.token)["ok"]
    # bad hash format
    with pytest.raises(IntentRefused) as e:
        _submit(p2, "0x1234")
    assert e.value.kind == "bad_request"


def test_not_enough_in_the_wallet_is_refused_early(sc):
    world = sc
    ada, _, ch = _accepted(world)
    world.chain.balances[ADA_SA.lower()] = C.to_raw(Decimal("4.99"))
    with pytest.raises(IntentRefused) as e:
        _prepare(world, ada, ch)
    assert e.value.kind == "funds" and ADA_SA in e.value.message.lower()


# ── join, payout ─────────────────────────────────────────────────────────────


def _creator_locked(world, *, bola_passkey=True):
    ada, bola, ch = _accepted(world, bola_passkey=bola_passkey)
    p = _prepare(world, ada, ch)
    world.chain.land(h(10), [created_log(world.escrow_addr, ch["id"], ADA_SA, 5_000_000)])
    assert _submit(p, h(10))["status"] == "confirmed"
    from gaming.src.channels.core.actions import matches as svc

    return ada, bola, svc.load(ch["id"])


def test_join_binds_to_the_permitted_account_and_winner_is_paid_there(sc):
    world = sc
    ada, bola, ch = _creator_locked(world)
    assert store.get(intents.creator_binding(ch["id"])["id"])["detail"]["player2"].lower() == BOLA_SA
    assert routing.lock_route(bola["id"], ch) == routing.PASSKEY
    p = run(intents.prepare_lock(bola["id"], ch, channel="whatsapp", external_id=BOLA))
    assert p.intent["calls"][1]["data"] == C.join_match(world.escrow_addr, C.match_id_bytes32(ch["id"]),
                                                        5_000_000).data
    world.chain.land(h(11), [joined_log(world.escrow_addr, ch["id"], BOLA_SA)])
    assert intents.submit(p.token, tx_hash=h(11), user_op_hash=h(12), amount="5",
                          challenge_id=ch["id"])["status"] == "confirmed"
    row = world.sb.challenge(ch["id"])
    assert row["status"] == "locked" and row["opponent_lock_tx_id"] == f"userop:{h(12)}"
    # settlement pays the account that staked, not the custodial wallet
    assert intents.locked_address(ch["id"], ada["id"]).lower() == ADA_SA
    from gaming.src.backend.services import clawstation_settlement as cs

    run(cs._execute_payout(world.sb.challenge(ch["id"]), ada["id"]))
    assert world.escrow[-1] == ("resolve", ch["id"], C.to_checksum_address(ADA_SA))


def test_opponent_with_a_custodial_binding_stays_custodial(sc):
    world = sc
    ada, bola, ch = _creator_locked(world, bola_passkey=False)
    # bola sets up a passkey after the creator's permit bound their Circle wallet
    wallets.register(bola["id"], BOLA_SA, "cred_bola_0123456789")
    assert routing.lock_route(bola["id"], ch) == routing.CUSTODIAL
    with pytest.raises(IntentRefused) as e:
        run(intents.prepare_lock(bola["id"], ch, channel="whatsapp", external_id=BOLA))
    assert e.value.kind == "wrong_wallet"


# ── channels ─────────────────────────────────────────────────────────────────


def test_whatsapp_lock_sends_approve_link_instead_of_yes(sc):
    world = sc
    ada, _, ch = _accepted(world)
    wa = FakeChannel("wa")
    run(wa.tap_id(ADA, ids.encode("match", "lock", ch["id"])))
    text = wa.last_text(ADA)
    assert "approve with your passkey" in text and "Boardman can't move your money" in text
    assert wa.links(ADA)[-1].startswith("https://boardman.test/app/approve/")
    assert "Yes, lock it" not in [lb for _, lb in wa.offered(ADA)]
    assert not world.escrow
    assert intents.view(_token(wa.links(ADA)[-1]))["action"] == "lock_create"


def test_required_flag_sends_setup_link_to_players_without_a_wallet(sc, monkeypatch):
    world = sc
    monkeypatch.setenv("SELF_CUSTODY_REQUIRED", "1")
    ada, _, ch = _accepted(world, ada_passkey=False)
    wa = FakeChannel("wa")
    run(wa.tap_id(ADA, ids.encode("match", "lock", ch["id"])))
    assert "Set up your wallet first" in wa.last_text(ADA)
    assert wa.links(ADA)[-1].startswith("https://boardman.test/app/wallet/setup?t=")
    assert not world.escrow


def test_custodial_players_keep_the_yes_prompt_when_not_required(sc):
    world = sc
    ada, _, ch = _accepted(world, ada_passkey=False)
    wa = FakeChannel("wa")
    run(wa.tap_id(ADA, ids.encode("match", "lock", ch["id"])))
    assert "Lock $5.00 USDC?" in wa.last_text(ADA)


def test_withdraw_sends_passkey_link_no_pin_and_confirms_on_transfer(sc):
    world = sc
    ada = wa_player(world, ADA, "ada", in_window=True)
    wallets.register(ada["id"], ADA_SA, CRED)
    world.chain.balances[ADA_SA.lower()] = C.to_raw(Decimal("40"))
    wa = FakeChannel("wa")
    run(wa.text(ADA, "withdraw"))
    run(wa.text(ADA, DEST))
    run(wa.text(ADA, "20"))
    assert "approve with your passkey" in wa.last_text(ADA) and "PIN" not in wa.last_text(ADA)
    url = wa.links(ADA)[-1]
    assert url.startswith("https://boardman.test/app/approve/")
    v = intents.view(_token(url))
    assert v["action"] == "withdraw" and v["to"].lower() == DEST
    to, raw = decode(["address", "uint256"], bytes.fromhex(v["calls"][0]["data"][10:]))
    assert to.lower() == DEST and raw == 20_000_000
    world.chain.land(h(20), [transfer_log(world.usdc, ADA_SA, DEST, 20_000_000)])
    out = intents.submit(_token(url), tx_hash=h(20), user_op_hash=None, amount="20", challenge_id=None)
    assert out["status"] == "confirmed"
    assert not world.transfers  # the custodial payout never ran


def test_legacy_telegram_lock_button_sends_passkey_link(sc, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from gaming.src.bot.handlers import simple_ui
    from gaming.src.channels.core.actions.matches import insert_challenge

    world = sc
    tobi = tg_player(world, 5001, "tobi")
    bola = wa_player(world, BOLA, "bola")
    wallets.register(tobi["id"], ADA_SA, CRED)
    world.chain.balances[ADA_SA.lower()] = C.to_raw(Decimal("40"))

    async def profile(user):
        return tobi

    monkeypatch.setattr(simple_ui, "get_or_create_profile", profile)
    ch = insert_challenge(creator_id=tobi["id"], opponent_id=bola["id"], amount=Decimal("5"),
                          game="mobile.fc_mobile", visibility="private")
    world.sb.challenge(ch["id"]).update(status="accepted")
    cb = MagicMock()
    cb.data = f"ui:lock:{ch['id']}"
    cb.from_user = MagicMock(id=5001, username="u5001", first_name="T", last_name=None)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    run(simple_ui.ui_lock(cb))
    call = cb.message.answer.call_args
    assert "approve with your passkey" in call.args[0]
    button = call.kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "Approve with passkey" and button.url.startswith("https://boardman.test/app/approve/")
    assert not world.escrow


def test_balance_offers_setup_and_shows_own_wallet(sc):
    world = sc
    wa_player(world, ADA, "ada", in_window=True)
    wa = FakeChannel("wa")
    run(wa.text(ADA, "balance"))
    assert "Passkey wallet" in wa.last_text(ADA)
    run(wa.tap(ADA, "Set up passkey wallet"))
    assert wa.links(ADA)[-1].startswith("https://boardman.test/app/wallet/setup?t=")


def test_naira_mints_to_the_passkey_account_and_cash_out_is_refused(sc):
    world = sc
    from gaming.src.backend.services.paycrest import offramp
    from gaming.src.backend.services.paycrest import wallets as pw

    ada = wa_player(world, ADA, "ada", in_window=True)
    assert pw.arc_destination_sync(ada["id"]) == PLAY_ADDR
    wallets.register(ada["id"], ADA_SA, CRED)
    assert pw.arc_destination_sync(ada["id"]).lower() == ADA_SA
    principal = SimpleNamespace(profile_id=ada["id"], channel="whatsapp", external_id=ADA)
    from gaming.src.backend.services.paycrest import config as pconfig

    world_cfg = pconfig.enabled
    try:
        pconfig.enabled = lambda: True
        with pytest.raises(offramp.NairaError) as e:
            offramp.prepare(principal, Decimal("5"), {"label": "GTB"})
        assert e.value.kind == "self_custody"
    finally:
        pconfig.enabled = world_cfg


# ── the HTTP surface the BFF calls ───────────────────────────────────────────


def test_http_setup_and_approve(sc, monkeypatch):
    world = sc
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    from gaming.src.backend.main import create_app

    c = TestClient(create_app())
    hdr = {"X-Boardman-Key": MASTER}
    ada, _, ch = _accepted(world, ada_passkey=False)
    world.chain.balances[ADA_SA.lower()] = C.to_raw(Decimal("40"))
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    assert c.get("/api/self-custody/setup", params={"t": tok}).status_code == 401  # platform only
    r = c.get("/api/self-custody/setup", params={"t": tok}, headers=hdr)
    assert r.status_code == 200 and r.json()["wallet"] is None
    r = c.post("/api/self-custody/setup", params={"t": tok}, headers=hdr,
               json={"address": ADA_SA, "credential_id": CRED})
    assert r.status_code == 200 and r.json()["address"].lower() == ADA_SA
    assert any("passkey wallet is linked" in o.body for to, outs in world.wa_dv.session if to == ADA for o in outs)
    # session caller without a token
    r = c.get("/api/self-custody/setup", headers={**hdr, "X-Boardman-Caller": ada["id"]})
    assert r.json()["wallet"]["address"].lower() == ADA_SA

    from gaming.src.channels.core.actions import matches as svc

    p = _prepare(world, ada, svc.load(ch["id"]))
    r = c.get(f"/api/self-custody/approve/{p.token}", headers=hdr)
    assert r.status_code == 200 and r.json()["calls"] == p.intent["calls"]
    world.chain.land(h(30), [created_log(world.escrow_addr, ch["id"], ADA_SA, 5_000_000)])
    r = c.post(f"/api/self-custody/approve/{p.token}", headers=hdr,
               json={"tx_hash": h(30), "amount": "5", "challenge_id": ch["id"]})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert "intent_id" not in r.json()
    r = c.post(f"/api/self-custody/approve/{p.token}", headers=hdr,
               json={"tx_hash": h(30), "amount": "5", "challenge_id": ch["id"]})
    assert r.status_code == 409
