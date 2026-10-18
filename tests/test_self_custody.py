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
from gaming.src.backend.services.self_custody import (
    chain,
    config,
    intents,
    notices,
    proof,
    routing,
    setup,
    store,
    wallets,
)
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
        self.owners: dict[str, Account] = {}  # smart account -> the key its passkey stands for
        self.sig_checks: list[tuple] = []
        self.rpc_down = False

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

    def is_valid_signature(self, account, digest, signature):
        """ERC-1271 as a smart account owned by one EOA would answer it (real
        ECDSA: a signature by anyone else, or over other bytes, fails)."""
        self.sig_checks.append((account, digest))
        if self.rpc_down:
            raise ConnectionError("rpc down")
        owner = self.owners.get(account.lower())
        if owner is None:
            return False
        try:
            return Account._recover_hash(digest, signature=signature) == owner.address
        except Exception:
            return False

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
        wallets.link_unverified(ada["id"], ADA_SA, CRED)
        world.chain.balances[ADA_SA.lower()] = C.to_raw(Decimal("40"))
    if bola_passkey:
        wallets.link_unverified(bola["id"], BOLA_SA, "cred_bola_0123456789")
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
    assert c.post("/api/self-custody/setup/challenge", headers=hdr,
                  json={"address": "0x" + "5a" * 20}).status_code == 404
    assert c.get("/api/self-custody/approve/" + "a" * 43, headers=hdr).status_code == 404
    assert c.post("/api/self-custody/approve/" + "a" * 43, headers=hdr,
                  json={"tx_hash": h(1), "amount": "5"}).status_code == 404


def test_migration_matches_store_module():
    path = ROOT / "supabase" / "migrations" / "20261018130000_self_custody_intents.sql"
    assert path.read_text() == store.postgres_migration_sql()
    path = ROOT / "supabase" / "migrations" / "20261018150000_self_custody_wallet_requests.sql"
    assert path.read_text() == store.postgres_requests_migration_sql()


# ── wallet setup: proof, chat confirmation, change cool-down ─────────────────

ADA_KEY = Account.from_key("0x" + "a1" * 32)   # what Ada's passkey stands for in the fake chain
EVE_KEY = Account.from_key("0x" + "e1" * 32)   # an attacker's own passkey
EVE_SA = "0x" + "ee" * 20
NEW_SA = "0x" + "5c" * 20


def _sig(key, message: str) -> str:
    return "0x" + bytes(key.unsafe_sign_hash(proof.eip191_hash(message)).signature).hex()


def _own(world, sa: str, key) -> None:
    world.chain.owners[sa.lower()] = key


def _prove(world, tok, sa, key, *, cred=CRED, caller=None, auth_iat_ms=None, now_ms=None):
    """What the page does: challenge for the new address, passkey signs, post."""
    _own(world, sa, key)
    c = setup.challenge(tok, address=sa, caller=caller, auth_iat_ms=auth_iat_ms, now_ms=now_ms)
    return c, setup.register(tok, address=sa, credential_id=cred, challenge_id=c["challenge_id"],
                             signature=_sig(key, c["message"]), caller=caller, auth_iat_ms=auth_iat_ms,
                             now_ms=now_ms)


def _prompts(dv, who: str) -> list:
    """Chat prompts with buttons a deliverer recorded for one chat."""
    return [o for to, outs in dv.session if to == who for o in outs if getattr(o, "options", None)]


def _ada_both_chats(world):
    """Ada on WhatsApp (inside the 24 h window) and on Telegram."""
    from tests.channels_match_fixtures import ids_svc

    ada = wa_player(world, ADA, "ada", in_window=True)
    ids_svc.ensure_telegram_identity(ada["id"], 7001, chat_id=7001, username="ada")
    return ada


def _engine_wa():
    from gaming.src.channels.core.engine import Engine

    return FakeChannel("wa", engine=Engine())  # real notifier: the recording deliverers


def test_proof_vectors_match_viem():
    """Same vectors as frontend/lib/__tests__/setupProof.test.mjs (viem 2.57.7)."""
    from eth_account.messages import _hash_eip191_message, encode_defunct
    from eth_utils import keccak

    assert "0x" + keccak(proof.VALIDATOR_BYTECODE).hex() == \
        "0x00f03afb646c45f698b5a1f540c482aebc9f5215003e4707d362a02526753936"
    cd = proof.validator_calldata("0x" + "5a" * 20, keccak(b"boardman"), b"\x11" * 65)
    assert len(cd) == 1908
    assert "0x" + keccak(cd).hex() == "0x922d78fbdbf2aa75561b64bf1b66899467a8004c22233d3d8db9b8d2b1ec1ab5"
    msg = proof.message_for(site="https://boardman.test", profile_id="p_ada", address="0x" + "5a" * 20,
                            evm_chain_id=5042002, kind="setup", nonce="0" * 32, issued_ms=1_760_000_000_000,
                            expires_ms=1_760_000_600_000)
    assert "Wallet: 0x5a5A5a5a5A5a5a5a5a5A5a5A5A5a5a5A5A5A5A5A\nAccount: p_ada\nChain ID: 5042002" in msg
    h = "0xc81fcf8effc4b98b8f94567d2bf845e922a6d88a2959549583f338ad6bd7e173"
    assert "0x" + proof.eip191_hash(msg).hex() == h
    assert "0x" + _hash_eip191_message(encode_defunct(text=msg)).hex() == h


def test_rpc_reader_verifies_with_one_deployless_call():
    """Web3Reader: eth_call with no ``to`` and the validator init code;
    0x01 = valid, a revert = invalid, a transport error raises."""
    from web3 import Web3
    from web3.providers.base import BaseProvider

    seen, answer = [], {"v": {"result": "0x01"}}

    class Prov(BaseProvider):
        def make_request(self, method, params):
            if method == "eth_chainId":
                return {"jsonrpc": "2.0", "id": 1, "result": hex(5042002)}
            seen.append((method, params))
            if answer["v"] == "down":
                raise ConnectionError("down")
            return {"jsonrpc": "2.0", "id": 1, **answer["v"]}

    r = chain.Web3Reader.__new__(chain.Web3Reader)
    r.w3 = Web3(Prov())
    digest = proof.eip191_hash("hi")
    assert r.is_valid_signature(ADA_SA, digest, b"\x01" * 65) is True
    method, (tx, _block) = seen[-1]
    assert method == "eth_call" and "to" not in tx
    assert tx["data"].startswith("0x" + proof.VALIDATOR_BYTECODE.hex())
    answer["v"] = {"result": "0x00"}
    assert r.is_valid_signature(ADA_SA, digest, b"\x01" * 65) is False
    answer["v"] = {"error": {"code": 3, "message": "execution reverted", "data": "0x"}}
    assert r.is_valid_signature(ADA_SA, digest, b"\x01" * 65) is False
    answer["v"] = "down"
    with pytest.raises(Exception):
        r.is_valid_signature(ADA_SA, digest, b"\x01" * 65)


def test_valid_proof_waits_for_the_chat_yes_then_links_once(sc):
    world = sc
    ada = _ada_both_chats(world)
    url, _ = setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)
    assert url.startswith("https://boardman.test/app/wallet/setup?t=")
    tok = _token(url)
    v = setup.view(tok)
    assert v["ok"] and v["wallet"] is None and v["pending"] is None and v["username"] == "Boardman @ada"
    assert v["chain"]["modular_path"] == "arcTestnet" and v["chain"]["evm_chain_id"] == 5042002
    c, out = _prove(world, tok, ADA_SA, ADA_KEY)
    # the challenge binds profile, wallet, chain and purpose
    for part in (f"Account: {ada['id']}", "Chain ID: 5042002", "Purpose: setup", "boardman.test wants you"):
        assert part in c["message"]
    assert f"Wallet: {ADA_SA}".lower() in c["message"].lower()
    assert world.chain.sig_checks[-1][0].lower() == ADA_SA
    assert out["status"] == "pending_confirm" and out["address"].lower() == ADA_SA
    # proven but NOT linked yet: nothing routes to it, top-ups go to the play wallet
    assert wallets.address(ada["id"]) is None and routing.account(ada["id"]) is None
    from gaming.src.backend.services.paycrest import wallets as pw

    assert pw.arc_destination_sync(ada["id"]) == PLAY_ADDR
    # the link was used
    with pytest.raises(IntentRefused) as e:
        setup.challenge(tok, address=ADA_SA)
    assert e.value.kind == "used"
    # every chat is asked: WhatsApp and Telegram
    assert run(notices.confirm_prompt(ada["id"], kind="setup", address=out["address"], nonce=out["confirm_nonce"]))
    wa_prompt, tg_prompt = _prompts(world.wa_dv, ADA)[-1], _prompts(world.tg_dv, "7001")[-1]
    for p in (wa_prompt, tg_prompt):
        assert "Is this your new wallet?" in p.body and out["address"] in p.body
        assert [o.label for o in p.options] == ["Yes, it's mine", "No"]
    yes = wa_prompt.options[0].id
    assert len(yes.encode()) <= 64
    wa = _engine_wa()
    run(wa.tap_id(ADA, yes))
    assert "Your passkey wallet is linked" in wa.last_text(ADA)
    assert wallets.address(ada["id"]).lower() == ADA_SA
    assert pw.arc_destination_sync(ada["id"]).lower() == ADA_SA
    # the other chat is told
    assert any("passkey wallet is linked" in o.body for to, outs in world.tg_dv.session if to == "7001" for o in outs)
    # a prompt works once
    run(wa.tap_id(ADA, yes))
    assert "already answered" in wa.last_text(ADA)
    # stored in the existing per-player wallet table, no key material
    from gaming.src.backend.services.paycrest import store as pstore

    row = pstore.get_wallet(ada["id"], "arc/passkey")
    assert row["wallet_id"] == f"passkey:{CRED}" and row["account_type"] == "circle_msca_passkey"
    # a second link cannot swap the address without a fresh web sign-in
    tok2 = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    with pytest.raises(IntentRefused) as e:
        setup.challenge(tok2, address=NEW_SA)
    assert e.value.kind == "reauth"
    assert wallets.address(ada["id"]).lower() == ADA_SA


def test_missing_forged_replayed_expired_and_mismatched_proofs_are_refused(sc, monkeypatch):
    """Each case refuses before anything is queued; a challenge is single use."""
    world = sc
    ada = wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola", in_window=True)
    _own(world, ADA_SA, ADA_KEY)

    def fresh():
        return _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])

    def reg(tok, c, sig, *, addr=ADA_SA, now_ms=None):
        return setup.register(tok, address=addr, credential_id=CRED, challenge_id=c["challenge_id"] if c else "",
                              signature=sig, now_ms=now_ms)

    def refused(kind, fn):
        with pytest.raises(IntentRefused) as e:
            fn()
        assert e.value.kind == kind, (e.value.kind, e.value.message)

    # missing proof: no challenge id / no signature
    tok = fresh()
    c = setup.challenge(tok, address=ADA_SA)
    refused("bad_proof", lambda: reg(tok, None, _sig(ADA_KEY, c["message"])))
    refused("bad_proof", lambda: reg(tok, c, ""))  # malformed signature: refused, challenge spent
    refused("used", lambda: reg(tok, c, _sig(ADA_KEY, c["message"])))
    # forged: signed by a key that does not own the account → link burned
    tok = fresh()
    c = setup.challenge(tok, address=ADA_SA)
    refused("bad_proof", lambda: reg(tok, c, _sig(EVE_KEY, c["message"])))
    refused("used", lambda: setup.challenge(tok, address=ADA_SA))
    # signed over a different text (another challenge's message)
    tok = fresh()
    c1 = setup.challenge(tok, address=ADA_SA)
    c2 = setup.challenge(tok, address=ADA_SA)  # supersedes c1
    refused("used", lambda: reg(tok, c1, _sig(ADA_KEY, c1["message"])))
    refused("bad_proof", lambda: reg(tok, c2, _sig(ADA_KEY, c1["message"])))
    # expired (signed-in web session, so only the challenge has run out)
    c = setup.challenge(None, address=ADA_SA, caller=ada["id"])
    refused("expired", lambda: setup.register(None, address=ADA_SA, credential_id=CRED,
                                              challenge_id=c["challenge_id"], signature=_sig(ADA_KEY, c["message"]),
                                              caller=ada["id"], now_ms=c["expires_at_ms"] + 1))
    refused("used", lambda: setup.register(None, address=ADA_SA, credential_id=CRED,
                                           challenge_id=c["challenge_id"], signature=_sig(ADA_KEY, c["message"]),
                                           caller=ada["id"]))
    # wrong profile: Bola's challenge with Ada's link, Ada's challenge from Bola's session
    tok = fresh()
    tok_b = _token(setup.issue_link(bola["id"], channel="whatsapp", external_id=BOLA)[0])
    cb = setup.challenge(tok_b, address=ADA_SA)
    refused("bad_proof", lambda: reg(tok, cb, _sig(ADA_KEY, cb["message"])))
    c = setup.challenge(tok, address=ADA_SA)
    refused("wrong_profile", lambda: setup.register(tok, address=ADA_SA, credential_id=CRED,
                                                    challenge_id=c["challenge_id"],
                                                    signature=_sig(ADA_KEY, c["message"]), caller=bola["id"]))
    # wrong link: a challenge made through the web session cannot be redeemed with a chat link
    cs = setup.challenge(None, address=ADA_SA, caller=ada["id"])
    refused("bad_proof", lambda: reg(tok, cs, _sig(ADA_KEY, cs["message"])))
    # wrong wallet: the challenge names another address
    c = setup.challenge(tok, address=ADA_SA)
    _own(world, NEW_SA, ADA_KEY)
    refused("bad_proof", lambda: reg(tok, c, _sig(ADA_KEY, c["message"]), addr=NEW_SA))
    # wrong chain: the network changed between challenge and proof
    c = setup.challenge(tok, address=ADA_SA)
    real = config.chain_settings
    monkeypatch.setattr(config, "chain_settings", lambda chain=None: {**real(chain), "evm_chain_id": 1})
    refused("wrong_chain", lambda: reg(tok, c, _sig(ADA_KEY, c["message"])))
    monkeypatch.setattr(config, "chain_settings", real)
    # RPC down: "try again", the link survives, the challenge does not
    c = setup.challenge(tok, address=ADA_SA)
    world.chain.rpc_down = True
    refused("not_configured", lambda: reg(tok, c, _sig(ADA_KEY, c["message"])))
    world.chain.rpc_down = False
    refused("used", lambda: reg(tok, c, _sig(ADA_KEY, c["message"])))
    # nothing of the above linked or even queued anything
    assert wallets.address(ada["id"]) is None and wallets.pending(ada["id"]) is None
    # and the same link still works with a real proof
    _, out = _prove(world, tok, ADA_SA, ADA_KEY)
    assert out["status"] == "pending_confirm"
    # no token and no session: refused
    refused("not_found", lambda: setup.view(None))


def test_stolen_link_gives_the_attacker_nothing(sc):
    """Eve gets Ada's setup link (forwarded, shoulder-surfed) and completes
    setup with her OWN passkey. Her proof is valid — for her wallet — but the
    wallet only becomes Ada's after Ada says yes in Ada's chat."""
    world = sc
    ada = _ada_both_chats(world)
    eve = wa_player(world, BOLA, "eve", in_window=True)
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    _, out = _prove(world, tok, EVE_SA, EVE_KEY)
    assert out["status"] == "pending_confirm"
    run(notices.confirm_prompt(ada["id"], kind="setup", address=out["address"], nonce=out["confirm_nonce"]))
    # nothing is routed to Eve's wallet while it waits
    from gaming.src.backend.services.paycrest import wallets as pw

    assert wallets.address(ada["id"]) is None and routing.account(ada["id"]) is None
    assert pw.arc_destination_sync(ada["id"]) == PLAY_ADDR
    # Ada's chat shows Eve's address, so Ada can tell it is not hers
    prompt = _prompts(world.wa_dv, ADA)[-1]
    assert out["address"] in prompt.body
    yes, no = (o.id for o in prompt.options)
    # Eve cannot answer it from her own chat (a forwarded button is someone else's tap)
    wa = _engine_wa()
    run(wa.tap_id(BOLA, yes))
    assert "isn't yours" in wa.last_text(BOLA)
    assert wallets.address(ada["id"]) is None and wallets.address(eve["id"]) is None
    # Ada taps No: declined, nothing linked; the Yes button is dead
    run(wa.tap_id(ADA, no))
    assert "was NOT linked" in wa.last_text(ADA)
    run(wa.tap_id(ADA, yes))
    assert "already answered" in wa.last_text(ADA)
    assert wallets.address(ada["id"]) is None and wallets.pending(ada["id"]) is None
    # Ada's other chat hears about it too
    assert any("declined" in o.body for to, outs in world.tg_dv.session if to == "7001" for o in outs)
    # and if Ada never answers, it simply expires
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    _, out = _prove(world, tok, EVE_SA, EVE_KEY)
    later = store.now_ms() + config.confirm_ttl_ms() + 1
    res = setup.answer(ada["id"], out["confirm_nonce"], approve=True, now_ms=later)
    assert res["result"] == "refused" and "expired" in res["message"]
    assert wallets.address(ada["id"]) is None


def test_wallet_screen_reoffers_a_missed_confirmation(sc):
    world = sc
    ada = wa_player(world, ADA, "ada", in_window=True)
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    _, out = _prove(world, tok, ADA_SA, ADA_KEY)
    wa = _engine_wa()
    run(wa.text(ADA, "balance"))
    assert "Waiting for your confirmation" in wa.last_text(ADA) and out["address"] in wa.last_text(ADA)
    run(wa.tap(ADA, "Confirm new wallet"))
    assert "Is this your new wallet?" in wa.last_text(ADA)
    run(wa.tap(ADA, "Yes, it's mine"))
    assert "Your passkey wallet is linked" in wa.last_text(ADA)
    assert wallets.address(ada["id"]).lower() == ADA_SA
    # the first prompt's nonce was replaced
    assert setup.answer(ada["id"], out["confirm_nonce"], approve=True)["result"] == "refused"


def test_wallet_change_needs_signin_proof_chat_and_a_cooldown(sc, monkeypatch):
    world = sc
    ada = _ada_both_chats(world)
    wallets.link_unverified(ada["id"], ADA_SA, CRED)
    now = store.now_ms()
    stale = now - config.reauth_max_age_ms() - 1
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    _own(world, NEW_SA, ADA_KEY)
    # chat link alone, a session without sign-in time, an old sign-in, another profile: refused
    for kw in ({"caller": None}, {"caller": ada["id"]}, {"caller": ada["id"], "auth_iat_ms": stale}):
        with pytest.raises(IntentRefused) as e:
            setup.challenge(tok if kw["caller"] is None else None, address=NEW_SA, **kw)
        assert e.value.kind == "reauth"
    v = setup.view(None, caller=ada["id"], auth_iat_ms=stale)
    assert v["change_needs_signin"] and not v["can_change"]
    assert setup.view(None, caller=ada["id"], auth_iat_ms=now)["can_change"]
    # fresh sign-in + proof → waits for the chat
    c, out = _prove(world, None, NEW_SA, ADA_KEY, cred="cred_ada_new_0123", caller=ada["id"], auth_iat_ms=now)
    assert c["kind"] == "change" and "Purpose: change" in c["message"]
    assert out["kind"] == "change" and out["status"] == "pending_confirm"
    from gaming.src.backend.services.paycrest import wallets as pw

    # old wallet still active for stakes; new money is held back from both passkey accounts
    assert routing.account(ada["id"]).lower() == ADA_SA
    assert pw.arc_destination_sync(ada["id"]) == PLAY_ADDR
    run(notices.confirm_prompt(ada["id"], kind="change", address=out["address"], nonce=out["confirm_nonce"],
                               previous=wallets.address(ada["id"])))
    for dv, who in ((world.wa_dv, ADA), (world.tg_dv, "7001")):
        p = _prompts(dv, who)[-1]
        assert "Change your passkey wallet?" in p.body and "24 hours" in p.body
    wa = _engine_wa()
    run(wa.tap_id(ADA, _prompts(world.wa_dv, ADA)[-1].options[0].id))
    assert "Wallet change scheduled" in wa.last_text(ADA)
    assert ("v1|scw|c|" in "".join(i for i, _ in wa.offered(ADA)))
    # every other chat is told, with a way to cancel
    tg_note = _prompts(world.tg_dv, "7001")[-1]
    assert "Wallet change scheduled" in tg_note.body and tg_note.options[0].label == "Cancel the change"
    # during the cool-down: old account active, deposits to the play wallet
    assert wallets.address(ada["id"]).lower() == ADA_SA
    assert pw.arc_destination_sync(ada["id"]) == PLAY_ADDR
    v = setup.view(None, caller=ada["id"], auth_iat_ms=now)
    assert v["pending"]["status"] == "cooling" and v["pending"]["active_at_ms"] > now
    # 24 h later the new account takes over (one transaction, on the next read)
    later = store.now_ms() + config.change_cooldown_ms() + 1_000
    monkeypatch.setattr(store, "now_ms", lambda: later)
    assert wallets.address(ada["id"]).lower() == NEW_SA
    assert wallets.get(ada["id"])["credential_id"] == "cred_ada_new_0123"
    assert pw.arc_destination_sync(ada["id"]).lower() == NEW_SA
    assert wallets.pending(ada["id"]) is None


def test_a_wallet_change_can_be_cancelled_from_any_chat(sc, monkeypatch):
    world = sc
    ada = _ada_both_chats(world)
    wallets.link_unverified(ada["id"], ADA_SA, CRED)
    now = store.now_ms()
    _, out = _prove(world, None, NEW_SA, ADA_KEY, caller=ada["id"], auth_iat_ms=now)
    assert setup.answer(ada["id"], out["confirm_nonce"], approve=True)["result"] == "cooling"
    from gaming.src.channels.core.engine import Engine

    tg = FakeChannel("tg", engine=Engine())
    run(tg.text("7001", "balance"))
    assert "Wallet change" in tg.last_text("7001")
    run(tg.tap("7001", "Cancel the change"))
    assert "Wallet change cancelled" in tg.last_text("7001")
    later = store.now_ms() + config.change_cooldown_ms() + 1_000
    monkeypatch.setattr(store, "now_ms", lambda: later)
    assert wallets.address(ada["id"]).lower() == ADA_SA
    # someone else's cancel button does nothing
    assert setup.cancel("someone-else", out["request_id"]) is None


def test_setup_refuses_someone_elses_address_and_wrong_session(sc):
    world = sc
    ada = wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola")
    wallets.link_unverified(bola["id"], BOLA_SA, "cred_bola_0123456789")
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    with pytest.raises(IntentRefused) as e:
        setup.view(tok, caller=bola["id"])
    assert e.value.kind == "wrong_profile"
    with pytest.raises(IntentRefused) as e:
        setup.challenge(tok, address=BOLA_SA)
    assert e.value.kind == "taken"


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
    wallets.link_unverified(bola["id"], BOLA_SA, "cred_bola_0123456789")
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
    wallets.link_unverified(ada["id"], ADA_SA, CRED)
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
    wallets.link_unverified(tobi["id"], ADA_SA, CRED)
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
    wallets.link_unverified(ada["id"], ADA_SA, CRED)
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
    _own(world, ADA_SA, ADA_KEY)
    r = c.post("/api/self-custody/setup/challenge", params={"t": tok}, headers=hdr, json={"address": ADA_SA})
    assert r.status_code == 200
    chal = r.json()
    body = {"address": ADA_SA, "credential_id": CRED, "challenge_id": chal["challenge_id"]}
    # a forged signature: 422, nothing queued, the link is burned
    r = c.post("/api/self-custody/setup", params={"t": tok}, headers=hdr,
               json={**body, "signature": _sig(EVE_KEY, chal["message"])})
    assert r.status_code == 422 and r.json()["error"] == "bad_proof"
    tok = _token(setup.issue_link(ada["id"], channel="whatsapp", external_id=ADA)[0])
    chal = c.post("/api/self-custody/setup/challenge", params={"t": tok}, headers=hdr,
                  json={"address": ADA_SA}).json()
    r = c.post("/api/self-custody/setup", params={"t": tok}, headers=hdr,
               json={**body, "challenge_id": chal["challenge_id"], "signature": _sig(ADA_KEY, chal["message"])})
    out = r.json()
    assert r.status_code == 200 and out["address"].lower() == ADA_SA and out["status"] == "pending_confirm"
    assert out["confirm_sent"] is True
    # the confirmation nonce never reaches the page
    assert not {"confirm_nonce", "profile_id", "request_id"} & set(out)
    prompt = _prompts(world.wa_dv, ADA)[-1]
    assert "Is this your new wallet?" in prompt.body
    assert c.get("/api/self-custody/setup", headers={**hdr, "X-Boardman-Caller": ada["id"]}).json()["wallet"] is None
    run(_engine_wa().tap_id(ADA, prompt.options[0].id))
    # session caller without a token
    r = c.get("/api/self-custody/setup", headers={**hdr, "X-Boardman-Caller": ada["id"]})
    assert r.json()["wallet"]["address"].lower() == ADA_SA and r.json()["change_needs_signin"]
    iat = str(store.now_ms() // 1000)
    r = c.get("/api/self-custody/setup", headers={**hdr, "X-Boardman-Caller": ada["id"], "X-Boardman-Auth-Iat": iat})
    assert r.json()["can_change"]
    r = c.post("/api/self-custody/setup/challenge", headers={**hdr, "X-Boardman-Caller": ada["id"]},
               json={"address": NEW_SA})
    assert r.status_code == 401 and r.json()["error"] == "reauth"

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


def test_pause_still_gates_new_stakes_but_not_withdrawals(sc, monkeypatch):
    from gaming.src.backend.services import safety

    world = sc
    ada, _, ch = _accepted(world)
    monkeypatch.setattr(safety, "is_paused", lambda: True)
    with pytest.raises(IntentRefused) as e:
        _prepare(world, ada, ch)
    assert e.value.kind == "gate"
    # the player's own money is not Boardman's to freeze
    p = intents.prepare_withdraw(ada["id"], DEST, Decimal("3"), channel="whatsapp", external_id=ADA)
    assert p.url.startswith("https://boardman.test/app/approve/")


def test_cctp_burn_calls_encode_mint_recipient():
    usdc, tm, me = "0x" + "36" * 20, "0x" + "28" * 20, "0x" + "ab" * 20
    approve, burn = C.cctp_burn_calls(usdc, tm, 7_000_000, 6, me, max_fee_raw=3_500)
    spender, raw = decode(["address", "uint256"], bytes.fromhex(approve.data[10:]))
    assert spender.lower() == tm and raw == 7_000_000
    args = decode(["uint256", "uint32", "bytes32", "address", "bytes32", "uint256", "uint32"],
                  bytes.fromhex(burn.data[10:]))
    assert args[0] == 7_000_000 and args[1] == 6 and args[2][-20:].hex() == me[2:]
    assert args[3].lower() == usdc and args[4] == bytes(32) and args[5] == 3_500 and args[6] == 2000
