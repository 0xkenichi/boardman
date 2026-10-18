"""Naira rail (Paycrest + CCTP) end to end against fakes. No network."""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gaming.src.backend.services.bridge import cctp
from gaming.src.backend.services.paycrest import client as pc_client
from gaming.src.backend.services.paycrest import config, events, offramp, onramp, reconcile, store
from gaming.src.backend.services.paycrest.models import BankAccount, KycPerson
from gaming.src.channels.core import withdraw_links
from gaming.src.channels.core.withdraw_links import LinkRefused
from gaming.src.channels.fake.adapter import FakeChannel
from tests.channels_fixtures import PLAY_ADDR, wa_user, world  # noqa: F401
from tests.paycrest_fakes import SECRET, rail, signed, webhook_body  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
U = "2348011112222"
MASTER = "test-paycrest-master"
BVN = "22212345678"
KYC = {"full_name": "Ada Obi", "birth_date": "1995-04-02", "id_type": "BVN", "id_number": BVN}
REFUND = {"institution": "GTBINGLA", "account_identifier": "0123456789"}
BASE, ARC = "base_mainnet", "arc_mainnet"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def api(world, monkeypatch):
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    from gaming.src.backend.main import create_app

    return TestClient(create_app())


def _token(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def _onramp_link(world, rail, amount_label="₦20,000"):
    prof = wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "deposit"))
    run(wa.tap(U, "Naira via Paycrest"))
    run(wa.tap(U, amount_label))
    quote = wa.last_text(U)
    run(wa.tap(U, "Continue"))
    url = wa.links(U)[-1]
    return prof, wa, quote, url


def _drain():
    for _ in range(5):
        cctp.reconcile()


def _order(oid):
    return store.get_order(oid)


# ── flags off: nothing visible ───────────────────────────────────────────────


def test_flags_off_rail_is_invisible(world, api, monkeypatch):
    monkeypatch.setenv("PAYCREST_API_KEY", "pk-test-not-real")
    monkeypatch.setenv("PAYCREST_ENABLED", "1")  # REAL_MONEY_ENABLED still off
    assert config.enabled() is False
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "deposit"))
    assert "Naira via Paycrest" not in wa.all_text(U)
    run(wa.tap_id(U, "v1|naira|start|in"))
    assert "not available" in wa.all_text(U)
    run(wa.text(U, "naira"))
    assert "Naira with Paycrest" not in wa.all_text(U)
    run(wa.text(U, "menu"))
    assert "Naira (Paycrest)" not in wa.all_text(U)
    run(wa.text(U, "withdraw"))
    assert "Cash out to bank" not in wa.all_text(U)
    body = webhook_body("pc-1", "settled")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).status_code == 404
    assert api.get("/api/channels/naira/x" * 1, headers={"X-Boardman-Key": MASTER}).status_code == 404
    from gaming.src.bot.keyboards import get_money_menu

    assert "v1|naira|start|in" not in json.dumps(get_money_menu().model_dump())


def test_default_env_keeps_everything_off():
    assert config.real_money_enabled() is False
    assert config.paycrest_flag() is False
    assert config.enabled() is False
    from gaming.src.backend.services.funding_rails import get_rail

    assert get_rail("paycrest_ngn")["enabled"] is False


def test_telegram_money_menu_shows_paycrest_only_when_on(rail):
    from gaming.src.bot.keyboards import get_money_menu

    dumped = json.dumps(get_money_menu().model_dump())
    assert "v1|naira|start|in" in dumped and "Top up with naira (Paycrest)" in dumped


# ── on-ramp ──────────────────────────────────────────────────────────────────


def test_onramp_happy_path_quote_kyc_webhooks_bridge(world, rail, api):
    prof, wa, quote, url = _onramp_link(world, rail)
    assert "Rate: ₦1,600.00 per $1" in quote and "real money" in quote.lower()
    assert "about *$12.49 USDC*" in quote  # 20000/1600 = 12.50 minus the capped 1 bps bridge fee
    assert url.startswith("https://boardman.test/app/naira/")
    assert BVN not in wa.all_text(U) and "BVN or NIN" in wa.all_text(U)  # asked for on the web only

    tok = _token(url)
    view = onramp.view(tok)
    assert view["amount_ngn"] == "20000" and view["real_money"] is True
    assert {"code": "GTBINGLA", "name": "Guaranty Trust Bank", "type": "bank"} in view["institutions"]

    out = onramp.submit(tok, kyc=KYC, refund=REFUND)
    assert out["ok"] and out["status"] == "awaiting_deposit"
    assert out["pay"]["account_identifier"] == "9900001111"
    sent = rail.pc.created[-1]
    assert sent["amountIn"] == "fiat" and sent["amount"] == "20000"
    assert sent["source"]["kyc"]["personDetails"]["idDocument"] == {"type": "BVN", "number": BVN, "issuerCountry": "NG"}
    assert sent["source"]["refundAccount"] == {"institution": "GTBINGLA", "accountIdentifier": "0123456789",
                                               "accountName": "ADA OBI"}
    base_addr = sent["destination"]["recipient"]["address"]
    assert sent["destination"]["recipient"]["network"] == "base"
    assert any("9900001111" in t for _, t in rail.told)  # account to pay sent to the chat

    # KYC is pass-through: not one byte of it in our tables
    with store.db().transaction(readonly=True) as tx:
        dump = json.dumps([tx.all(f"SELECT * FROM {t}") for t in store.TABLES], default=str)
    assert BVN not in dump and "1995-04-02" not in dump

    order = store.get_order_by_paycrest_id("pc-1")
    h = {"X-Boardman-Key": MASTER}
    body = webhook_body("pc-1", "pending")
    r = api.post("/webhooks/paycrest", content=body, headers=signed(body))
    assert r.status_code == 200 and r.json()["outcome"] == "processing"

    rail.ops.credit(BASE, base_addr, Decimal("12.50"))  # Paycrest delivers on Base
    body = webhook_body("pc-1", "settled", txHash="0xpaid")
    r = api.post("/webhooks/paycrest", content=body, headers={**signed(body), **h})
    assert r.json()["outcome"] == "settled"
    assert _order(order["id"])["status"] == "bridging"
    _drain()
    assert _order(order["id"])["status"] == "completed"
    assert rail.ops.bal(BASE, base_addr) == 0
    assert rail.ops.bal(ARC, PLAY_ADDR) == Decimal("12.49875")  # minus the 1 bps fast fee cap
    assert [c[0] for c in rail.ops.calls].count("mint") == 1
    burn = next(t for t in rail.ops.txs.values() if t["op"] == "burn")
    assert burn["fast"] is True and burn["dst_domain"] == 26
    assert any("in your play wallet" in t for _, t in rail.told)


def test_onramp_kyc_required_and_validated(world, rail):
    _prof, _wa, _q, url = _onramp_link(world, rail)
    tok = _token(url)
    with pytest.raises(LinkRefused) as e:
        onramp.submit(tok, kyc={**KYC, "id_number": "123"}, refund=REFUND)
    assert "11 digits" in e.value.message
    with pytest.raises(LinkRefused):
        onramp.submit(tok, kyc={**KYC, "birth_date": "2015-01-01"}, refund=REFUND)
    rail.pc.names["0123456789"] = "TUNDE BAKARE"
    with pytest.raises(LinkRefused) as e:
        onramp.submit(tok, kyc=KYC, refund=REFUND)
    assert "your own name" in e.value.message
    assert not rail.pc.created
    rail.pc.names.clear()
    rail.pc.kyc_reject = True
    out = onramp.submit(tok, kyc=KYC, refund=REFUND)
    assert out["ok"] is False and out["error"] == "kyc_rejected"
    o = store.list_orders(direction="onramp")[-1]
    assert o["status"] == "failed" and o["error"] == "kyc_rejected"
    with pytest.raises(LinkRefused):
        onramp.view(tok)  # burned


def test_kyc_models_never_print_secrets():
    p = KycPerson("Ada Obi", "1995-04-02", "nationalID", "12345678901")
    assert "12345678901" not in repr(p) and p.validate() is None
    assert p.to_api()["personDetails"]["idDocument"]["type"] == "nationalID"
    a = BankAccount("GTBINGLA", "0123456789", "ADA OBI", "GTBank")
    assert "0123456789" not in repr(a) and a.masked == "GTBank ••••6789"


def test_onramp_expired_and_refunded(world, rail, api):
    _p, _wa, _q, url = _onramp_link(world, rail)
    onramp.submit(_token(url), kyc=KYC, refund=REFUND)
    body = webhook_body("pc-1", "expired")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).json()["outcome"] == "expired"
    assert store.get_order_by_paycrest_id("pc-1")["status"] == "expired"
    assert any("expired" in t for _, t in rail.told)

    _p, _wa, _q, url = _onramp_link(world, rail, "₦5,000")
    onramp.submit(_token(url), kyc=KYC, refund=REFUND)
    hold = webhook_body("pc-2", "pending", event="payment_order.compliance_hold", statusDetail="under_review")
    assert api.post("/webhooks/paycrest", content=hold, headers=signed(hold)).json()["outcome"] == "hold"
    body = webhook_body("pc-2", "refunded", refundReason="payer_mismatch")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).json()["outcome"] == "refunded"
    o = store.get_order_by_paycrest_id("pc-2")
    assert o["status"] == "refunded" and o["details"]["hold"] is True
    assert any("isn't in your name" in t for _, t in rail.told)
    assert not rail.ops.ops("burn")


def test_onramp_daily_limit(world, rail):
    prof = wa_user(world.repo)
    now = store.now_ms()
    store.create_order(idempotency_key="k1", direction="onramp", profile_id=prof["id"], status="awaiting_deposit",
                       amount_ngn="990000")
    assert "₦10,000 more today" in onramp.limit_problem(prof["id"], Decimal("20000"), now_ms=now)
    assert onramp.limit_problem(prof["id"], Decimal("10000"), now_ms=now) is None
    assert "smallest" in onramp.limit_problem(prof["id"], Decimal("10"), now_ms=now)


# ── webhook security ─────────────────────────────────────────────────────────


def test_webhook_signature_good_bad_replay(world, rail, api):
    _p, _wa, _q, url = _onramp_link(world, rail)
    onramp.submit(_token(url), kyc=KYC, refund=REFUND)
    body = webhook_body("pc-1", "pending")
    assert api.post("/webhooks/paycrest", content=body).status_code == 401
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body, "wrong-secret")).status_code == 401
    tampered = body.replace(b"pending", b"settled")
    assert api.post("/webhooks/paycrest", content=tampered, headers=signed(body)).status_code == 401
    up = {"X-Paycrest-Signature": signed(body)["X-Paycrest-Signature"].upper()}
    assert api.post("/webhooks/paycrest", content=body, headers=up).json()["outcome"] == "processing"
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).json()["outcome"] == "duplicate"
    # a later, different delivery of an older status never moves the order back
    rail.ops.credit(BASE, rail.pc.created[-1]["destination"]["recipient"]["address"], Decimal("12.5"))
    s = webhook_body("pc-1", "settled")
    api.post("/webhooks/paycrest", content=s, headers=signed(s))
    late = webhook_body("pc-1", "pending", timestamp="later")
    assert api.post("/webhooks/paycrest", content=late, headers=signed(late)).json()["outcome"] == "noop"
    assert store.get_order_by_paycrest_id("pc-1")["status"] in ("bridging", "completed")


def test_webhook_fails_closed_without_secret(world, rail, api, monkeypatch):
    monkeypatch.delenv("PAYCREST_API_SECRET")
    body = webhook_body("pc-1", "pending")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).status_code == 401


def test_signature_helper():
    body = b'{"a":1}'
    sig = pc_client.sign(body, "s")
    assert pc_client.verify_signature(body, sig, "s")
    assert pc_client.verify_signature(body, f"  {sig.upper()} ", "s")
    assert not pc_client.verify_signature(body, sig[:-1], "s")
    assert not pc_client.verify_signature(body, sig, "")


# ── idempotency and retries ──────────────────────────────────────────────────


def test_onramp_retry_after_503_creates_one_order(world, rail):
    _p, _wa, _q, url = _onramp_link(world, rail)
    tok = _token(url)
    rail.pc.unavailable = 1
    with pytest.raises(LinkRefused) as e:
        onramp.submit(tok, kyc=KYC, refund=REFUND)
    assert "nothing was charged" in e.value.message
    assert store.list_orders(direction="onramp")[-1]["status"] == "quoted"
    assert onramp.submit(tok, kyc=KYC, refund=REFUND)["ok"]
    assert len(rail.pc.created) == 1
    with pytest.raises(LinkRefused):
        onramp.submit(tok, kyc=KYC, refund=REFUND)  # single use
    assert len(rail.pc.created) == 1


def test_ambiguous_submit_is_found_by_reference_not_resent(world, rail):
    _p, _wa, _q, url = _onramp_link(world, rail)
    rail.pc.ambiguous = 1
    out = onramp.submit(_token(url), kyc=KYC, refund=REFUND)
    assert out["status"] == "confirming" and "Don't pay" in out["message"]
    o = store.list_orders(direction="onramp")[-1]
    assert o["status"] == "submit_unknown"
    reconcile.reconcile_once(now_ms=store.now_ms() + 120_000)
    o = store.get_order(o["id"])
    assert o["status"] == "awaiting_deposit" and o["paycrest_id"] == "pc-1"
    assert len(rail.pc.created) == 1
    assert any("9900001111" in t for _, t in rail.told)


def test_order_and_bridge_creation_are_idempotent(world, rail):
    a, created_a = store.create_order(idempotency_key="same", direction="onramp", profile_id="p", status="quoted")
    b, created_b = store.create_order(idempotency_key="same", direction="onramp", profile_id="p", status="quoted")
    assert created_a and not created_b and a["id"] == b["id"]
    rail.ops.addr_of["w1"] = (BASE, "0x" + "1" * 40)
    rail.ops.credit(BASE, "0x" + "1" * 40, Decimal("5"))
    kw = dict(idempotency_key="br", kind="onramp_sweep", profile_id="p", src_chain=BASE, dst_chain=ARC,
              amount=Decimal("5"), from_wallet_id="w1", mint_recipient=PLAY_ADDR)
    one = cctp.start(**kw)
    two = cctp.start(**kw)
    assert one["id"] == two["id"]
    _drain()
    assert len(rail.ops.ops("burn")) == 1 and len(rail.ops.ops("mint")) == 1


def test_state_machine_refuses_illegal_moves():
    o, _ = store.create_order(idempotency_key="sm", direction="onramp", profile_id="p", status="quoted")
    assert store.transition(o["id"], "submitting", expect="quoted")
    assert not store.transition(o["id"], "submitting", expect="quoted")  # already there
    with pytest.raises(store.IllegalTransition):
        store.transition(o["id"], "completed", expect="submitting")
    assert not store.transition(o["id"], "completed")  # webhook-style: silently ignored
    assert store.transition(o["id"], "failed")
    assert not store.transition(o["id"], "awaiting_deposit")  # terminal


def test_migration_matches_store_module():
    path = ROOT / "supabase" / "migrations" / "20261018120000_paycrest_naira.sql"
    assert path.read_text() == store.postgres_migration_sql()
    assert "kyc" not in store.postgres_migration_sql().lower().replace("no kyc columns", "")


# ── bridge failures ──────────────────────────────────────────────────────────


def test_bridge_mint_failure_retries_then_succeeds(world, rail):
    rail.ops.addr_of["w1"] = (BASE, "0x" + "1" * 40)
    rail.ops.credit(BASE, "0x" + "1" * 40, Decimal("5"))
    rail.ops.fail["mint"] = 1
    rail.ops.attest_pending = 2
    br = cctp.start(idempotency_key="b1", kind="test", profile_id="p", src_chain=BASE, dst_chain=ARC,
                    amount=Decimal("5"), from_wallet_id="w1", mint_recipient=PLAY_ADDR)
    for _ in range(12):
        cctp.advance(br["id"])
    row = store.get_bridge(br["id"])
    assert row["status"] == "minted" and row["attempts"] == 1
    ok_mints = [t for t in rail.ops.txs.values() if t["op"] == "mint" and not t["failed"]]
    assert len(ok_mints) == 1 and ok_mints[0]["relayer"] == "relay-arc"


def test_bridge_gives_up_and_flags_order_for_review(world, rail):
    prof = wa_user(world.repo)
    w = {"wallet_id": "w-in", "address": "0x" + "2" * 40}
    store.put_wallet(prof["id"], f"{BASE}/in", w["wallet_id"], w["address"], "SCA")
    rail.ops.addr_of["w-in"] = (BASE, w["address"])
    rail.ops.credit(BASE, w["address"], Decimal("7"))
    o, _ = store.create_order(idempotency_key="g1", direction="onramp", profile_id=prof["id"], status="settled",
                              details={"arc_address": PLAY_ADDR})
    rail.ops.raise_["mint"] = 99
    onramp.sweep(prof["id"])
    br = store.get_bridge(store.get_order(o["id"])["bridge_id"])
    for _ in range(20):
        cctp.advance(br["id"])
    assert store.get_bridge(br["id"])["status"] == "failed"
    assert store.get_order(o["id"])["status"] == "needs_review"
    assert any("FAILED" in a for a in rail.alerts)


def test_reconciler_polls_missed_webhooks(world, rail):
    _p, _wa, _q, url = _onramp_link(world, rail)
    onramp.submit(_token(url), kyc=KYC, refund=REFUND)
    rail.pc.set_status("pc-1", "expired")
    reconcile.reconcile_once(now_ms=store.now_ms() + reconcile.POLL_AFTER_MS + 1)
    assert store.get_order_by_paycrest_id("pc-1")["status"] == "expired"


# ── cash-out: Arc → Base → Paycrest → bank ───────────────────────────────────


def _cashout_link(world, rail, amount="20"):
    prof = wa_user(world.repo)
    rail.ops.addr_of[f"w_{prof['id']}"] = (ARC, PLAY_ADDR)
    rail.ops.credit(ARC, PLAY_ADDR, Decimal("40"))
    wa = FakeChannel("wa")
    run(wa.text(U, "withdraw"))
    run(wa.tap(U, "Cash out to bank"))
    run(wa.tap(U, "OPay"))
    run(wa.text(U, "0123456789"))
    assert "ADA OBI" in wa.last_text(U)
    run(wa.tap(U, "Yes, that's me"))
    run(wa.text(U, amount))
    quote = wa.last_text(U)
    run(wa.tap(U, "Continue"))
    return prof, wa, quote, wa.links(U)[-1]


def test_withdraw_to_bank_end_to_end(world, rail, api):
    prof, wa, quote, url = _cashout_link(world, rail)
    assert "₦31,000" in quote and "real money" in quote.lower()  # 20 * 1550
    assert url.startswith("https://boardman.test/app/withdraw/")
    tok = _token(url)
    view = withdraw_links.view(tok)
    assert view["destination"]["bank"] == "OPay ••••6789" and view["naira"]["payout_ngn"] == "31000"

    out = run(withdraw_links.confirm(tok, pin="246810", pin_confirm="246810", amount="20"))
    assert out["ok"] and "Cash-out started" in out["message"]
    o = store.list_orders(direction="offramp")[-1]
    assert o["status"] == "bridging_out"
    burn = next(t for t in rail.ops.txs.values() if t["op"] == "approve")
    assert burn
    _drain()
    o = store.get_order(o["id"])
    assert o["status"] == "awaiting_settlement", o
    sent = rail.pc.created[-1]
    assert sent["source"] == {"type": "crypto", "currency": "USDC", "network": "base",
                              "refundAddress": o["details"]["out_address"]}
    assert sent["destination"]["recipient"]["accountIdentifier"] == "0123456789"
    assert Decimal(sent["amount"]) == Decimal("19.98")  # shrunk so amount + fee fits the bridged 20
    transfer = next(t for t in rail.ops.txs.values() if t["op"] == "transfer")
    assert transfer["amount"] == Decimal("20.00") and transfer["to"] == "0x" + "9" * 40
    assert rail.ops.bal(ARC, PLAY_ADDR) == Decimal("20")

    pcid = o["paycrest_id"]
    body = webhook_body(pcid, "settled")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).json()["outcome"] == "completed"
    assert store.get_order(o["id"])["status"] == "completed"
    assert any("has been paid to OPay ••••6789" in t for _, t in rail.told)
    # the link cannot pay twice
    with pytest.raises(LinkRefused):
        run(withdraw_links.confirm(tok, pin="246810", amount="20"))
    assert len([t for t in rail.ops.txs.values() if t["op"] == "transfer"]) == 1


def test_withdraw_refund_comes_home(world, rail, api):
    prof, wa, quote, url = _cashout_link(world, rail)
    run(withdraw_links.confirm(_token(url), pin="246810", pin_confirm="246810", amount="20"))
    _drain()
    o = store.list_orders(direction="offramp")[-1]
    out_addr = o["details"]["out_address"]
    rail.ops.credit(BASE, out_addr, Decimal("20"))  # Paycrest returns the deposit to refundAddress
    body = webhook_body(o["paycrest_id"], "refunded")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).json()["outcome"] == "refunded_on_base"
    _drain()
    assert store.get_order(o["id"])["status"] == "refunded"
    assert rail.ops.bal(ARC, PLAY_ADDR) > Decimal("39.9")
    assert any("back in your" in t for _, t in rail.told)


def test_paycrest_refusing_the_bank_returns_the_money(world, rail):
    prof, wa, quote, url = _cashout_link(world, rail)
    rail.pc.refuse = True
    run(withdraw_links.confirm(_token(url), pin="246810", pin_confirm="246810", amount="20"))
    _drain()
    o = store.list_orders(direction="offramp")[-1]
    assert o["status"] == "refunded"
    assert not rail.ops.ops("transfer")
    assert rail.ops.bal(ARC, PLAY_ADDR) == Decimal("39.998")  # 40 back, minus the capped fast-fee on the way home


def test_cashout_respects_caps_and_balance(world, rail):
    prof = wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "naira"))
    run(wa.tap(U, "Cash out to bank"))
    run(wa.text(U, "kuda"))
    run(wa.text(U, "123"))
    assert "10 digits" in wa.last_text(U)
    run(wa.text(U, "0123456789"))
    run(wa.tap(U, "Yes, that's me"))
    run(wa.text(U, "5000"))
    assert "largest naira cash-out" in wa.last_text(U)
    assert not rail.pc.created and not rail.ops.calls


def test_telegram_naira_flow_renders(world, rail, monkeypatch):
    from tests.channels_fixtures import tg_user

    monkeypatch.setenv("CHANNELS_CORE_FLOWS", "")  # legacy Telegram: only the naira flow is core
    prof = tg_user(world.repo)
    tg = FakeChannel("tg")
    tid = str(prof["telegram_id"])
    run(tg.tap_id(tid, "v1|naira|start|in"))
    run(tg.text(tid, "15k"))
    assert "₦15,000" in tg.last_text(tid) and "Continue" in json.dumps(tg.offered(tid))
    run(tg.tap(tid, "Continue"))
    assert tg.links(tid)[-1].startswith("https://boardman.test/app/naira/")


def test_worker_not_started_when_off():
    async def go():
        return reconcile.start_worker()

    assert run(go()) is None


def test_report_script_is_read_only(world, rail, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("reconcile_paycrest", ROOT / "scripts" / "reconcile_paycrest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    store.create_order(idempotency_key="r1", direction="offramp", profile_id="p" * 36, status="on_base",
                       details={"bank": {"account_identifier": "0123456789"}})
    assert mod.main(["--report"], bootstrap=False) == 0
    out = capsys.readouterr().out
    assert '"on_base"' in out and "0123456789" not in out and "pk-test" not in out


def test_env_script_keeps_the_rail_off_by_default():
    sh = (ROOT / "scripts" / "set_paycrest_env.sh").read_text()
    assert "read -rs -p \"Paycrest API key" in sh and "read -rs -p \"Paycrest API secret" in sh
    assert "FLAG=0" in sh and "Type REAL MONEY to confirm" in sh
    assert "/webhooks/paycrest" in sh


def test_hermetic_client_has_no_live_default():
    # with no override the real client exists but nothing in the test run calls it
    assert pc_client._override is None
    assert config.api_base() == "https://api.paycrest.io/v2"
