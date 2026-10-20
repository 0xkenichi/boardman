"""Money audit 2026-10 — naira cash-out (Paycrest offramp).

PoCs for AUDIT_2026-10_money.md:

* M-10  A confirmed cash-out only *checked* the play balance; the Arc burn
        lands 15-30 s later, and in between the same USDC could be spent
        again through the play overlay (a bet, the wallet bridge). Since the
        realms merge the overlay is practice-only and never counts toward the
        real balance; the cash-out keeps the spend lock and the cap
        reservation, and the test pins the realm separation instead.
* M-11  The Base "out" wallet sent its whole balance to Paycrest, not the
        order's amount: USDC sent to that (public) address, or a sibling
        order's refund, went to the bank above the per-order and daily caps.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from gaming.src.backend.services import play_adjust
from gaming.src.backend.services.bridge import cctp
from gaming.src.backend.services.paycrest import store
from gaming.src.channels.core import withdraw_links
from tests.channels_fixtures import PLAY_ADDR, world  # noqa: F401
from tests.paycrest_fakes import rail  # noqa: F401
from tests.test_paycrest import ARC, BASE, _cashout_link, _token


@pytest.fixture()
def live_balance(world, rail, monkeypatch):  # noqa: F811
    """The play balance as the services see it: chain USDC + the overlay."""
    c = "gaming.src.backend.services.clawstation_circle"

    async def _bal(user_id, chain_id=None):
        return max(Decimal("0"), rail.ops.bal(ARC, PLAY_ADDR) + play_adjust.get_adjust(user_id))

    async def _strict(user_id, chain_id=None):
        return rail.ops.bal(ARC, PLAY_ADDR), None

    monkeypatch.setattr(f"{c}.get_usdc_balance", _bal)
    monkeypatch.setattr(f"{c}.get_usdc_balance_strict", _strict)
    return rail


def _drain():
    for _ in range(6):
        cctp.reconcile()


def test_overlay_spends_never_read_the_real_cashout_wallet(monkeypatch):
    """M-10, after the realms merge: the overlay reservation behind bets and
    LP deposits reads the PRACTICE chain only, so it can never be checked
    against (and double-spend) the real USDC a pending cash-out will burn."""
    from gaming.src.backend.api import rematch_web
    from gaming.src.backend.services import realms

    reads: list = []

    async def _strict(user_id, chain_id=None):
        reads.append(chain_id)
        return Decimal("40"), None

    monkeypatch.setattr("gaming.src.backend.services.clawstation_circle.get_usdc_balance_strict", _strict)
    asyncio.run(rematch_web._reserve_play_stake("p_realm", Decimal("5"), "k1"))
    assert reads and all(realms.is_practice_chain(c) for c in reads), reads
    assert not any(realms.is_real_chain(c) for c in reads)
    assert play_adjust.get_adjust("p_realm") == Decimal("-5")


def test_cashout_sends_only_the_order_amount(world, live_balance):
    rail = live_balance
    _prof, _wa, _q, url = _cashout_link(world, rail)
    asyncio.run(withdraw_links.confirm(_token(url), pin="246810", pin_confirm="246810", amount="20"))
    out_addr = store.list_orders(direction="offramp")[-1]["details"]["out_address"]
    rail.ops.credit(BASE, out_addr, Decimal("400"))  # anyone can send USDC to it
    _drain()
    assert Decimal(rail.pc.created[-1]["amount"]) <= Decimal("20")
    sent = sum((t["amount"] for t in rail.ops.txs.values() if t["op"] == "transfer"), Decimal("0"))
    assert sent <= Decimal("20")


def test_a_webhook_that_failed_to_apply_is_processed_on_retry(world, rail, monkeypatch):  # noqa: F811
    """M-12: the delivery was marked seen (and the status echoed) before the
    transition ran; one DB blip on 'settled' left the on-ramp stuck: the
    retry was a 'duplicate' and the poller saw matching statuses."""
    from fastapi.testclient import TestClient

    from gaming.src.backend.main import create_app
    from gaming.src.backend.services.paycrest import onramp
    from tests.paycrest_fakes import signed, webhook_body
    from tests.test_paycrest import KYC, MASTER, REFUND, _onramp_link

    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    api = TestClient(create_app(), raise_server_exceptions=False)
    _prof, _wa, _q, url = _onramp_link(world, rail)
    onramp.submit(_token(url), kyc=KYC, refund=REFUND)
    order = store.get_order_by_paycrest_id("pc-1")
    rail.ops.credit(BASE, rail.pc.created[-1]["destination"]["recipient"]["address"], Decimal("12.50"))

    real = store.transition
    blips = {"n": 0}

    def _blip(order_id, to, **kw):
        if to == "settled" and blips["n"] == 0:
            blips["n"] += 1
            raise RuntimeError("database is locked")
        return real(order_id, to, **kw)

    monkeypatch.setattr(store, "transition", _blip)
    body = webhook_body("pc-1", "settled", txHash="0xpaid")
    assert api.post("/webhooks/paycrest", content=body, headers=signed(body)).status_code == 500
    retry = api.post("/webhooks/paycrest", content=body, headers=signed(body))
    assert retry.json().get("outcome") == "settled", retry.text
    assert store.get_order(order["id"])["status"] in ("settled", "bridging")


def test_failed_bridge_start_gives_the_cap_back(world, live_balance, monkeypatch):
    from gaming.src.backend.services import safety

    rail = live_balance
    prof, _wa, _q, url = _cashout_link(world, rail)

    def _boom(**_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(cctp, "start", _boom)
    out = asyncio.run(withdraw_links.confirm(_token(url), pin="246810", pin_confirm="246810", amount="20"))
    assert not out["ok"]
    assert play_adjust.get_adjust(prof["id"]) == Decimal("0")
    assert safety._daily_total(prof["id"]) == Decimal("0")
