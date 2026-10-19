"""Money audit 2026-10 — play-wallet withdrawals (web link, Telegram, WhatsApp).

PoCs for AUDIT_2026-10_money.md:

* M-08  The daily withdraw cap was checked before the transfer and counted
        after it, in this process's memory: concurrent withdrawals each passed
        the check, and a restart or a second worker reset every cap to zero.
* M-09  A Supabase failure in the audit write after a successful Circle
        transfer raised out of execute_transfer_sync: the money left but the
        caller told the player "nothing was sent".
"""
from __future__ import annotations

import asyncio
import threading
import time
from decimal import Decimal

import pytest

from tests.channels_fixtures import DEST, world  # noqa: F401


@pytest.fixture()
def rich(world, monkeypatch):  # noqa: F811
    world.balance = Decimal("200")
    real = __import__("gaming.src.backend.services.withdrawals", fromlist=["x"]).execute_transfer_sync

    def _slow(sender_id, wallet_id, address, amount, recipient_id, chain_id):
        time.sleep(0.2)  # Circle round trip
        world.balance -= Decimal(str(amount))
        world.transfers.append((sender_id, address, amount, recipient_id))
        return {"success": True, "transaction_id": "tx", "tx_hash": "0x" + "e" * 64, "status": "PENDING"}

    monkeypatch.setattr("gaming.src.backend.services.withdrawals.execute_transfer_sync", _slow)
    assert real is not None
    return world


def _withdraw(amount: str):
    from gaming.src.backend.services.withdrawals import perform_withdrawal

    return asyncio.run(perform_withdrawal("p_cap", recipient_address=DEST, amount=Decimal(amount)))


def test_concurrent_withdrawals_cannot_pass_the_daily_cap(rich):
    gate = threading.Barrier(3)
    outs = []

    def _go():
        gate.wait()
        outs.append(_withdraw("40"))

    ts = [threading.Thread(target=_go) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    sent = sum((Decimal(str(t[2])) for t in rich.transfers), Decimal("0"))
    assert sent <= Decimal("100"), [o.code for o in outs]


def test_the_daily_cap_survives_a_restart(rich, monkeypatch):
    from gaming.src.backend.services import safety

    assert _withdraw("50").ok
    assert _withdraw("40").ok
    # A redeploy / second worker: nothing in this process's memory.
    monkeypatch.setattr(safety, "_daily_withdraw", {})
    out = _withdraw("40")
    assert not out.ok and out.code == "gate", out
    assert len(rich.transfers) == 2


def test_a_failed_transfer_gives_the_cap_back(rich, monkeypatch):
    from gaming.src.backend.services import withdrawals

    ok = withdrawals.execute_transfer_sync

    def _fail(*_a, **_k):
        return {"success": False, "error": "circle 503"}

    monkeypatch.setattr(withdrawals, "execute_transfer_sync", _fail)
    assert not _withdraw("50").ok
    assert not _withdraw("50").ok
    monkeypatch.setattr(withdrawals, "execute_transfer_sync", ok)
    assert _withdraw("50").ok and _withdraw("50").ok


def test_audit_failure_after_the_transfer_still_reports_it_sent(monkeypatch):
    from gaming.src.backend.services import withdrawals

    class _Circle:
        def transfer_usdc(self, *_a, **_k):
            return {"success": True, "transaction_id": "tx9", "tx_hash": "0x9"}

    def _down():
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    monkeypatch.setattr("gaming.src.backend.services.clawstation_circle._circle_for_chain", lambda _c: _Circle())
    monkeypatch.setattr("backend.supabase_client.get_supabase", _down)
    out = withdrawals.execute_transfer_sync("p", "w", DEST, Decimal("5"), None, "arc")
    assert out["success"] is True and out["tx_hash"] == "0x9"
