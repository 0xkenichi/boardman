"""Tournament prizes: each (cup, place) is paid once, with a deterministic key."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from gaming.src.backend.services import tournament_money as tm


class FakeCircle:
    def __init__(self, fail_first: bool = False):
        self.calls: list[tuple[str, str, float, str]] = []
        self.fail_first = fail_first
        self.by_key: dict[str, dict] = {}

    def transfer_usdc(self, wallet_id, to_address, amount_usdc, *, idempotency_key=None):
        self.calls.append((wallet_id, to_address, amount_usdc, idempotency_key))
        if self.fail_first and len(self.calls) == 1:
            return {"success": False, "error": "circle 503"}
        # Circle dedups on the key: the same key returns the same transfer.
        if idempotency_key in self.by_key:
            return self.by_key[idempotency_key]
        out = {"success": True, "transaction_id": f"tx{len(self.by_key)}", "tx_hash": f"0xh{len(self.by_key)}"}
        self.by_key[idempotency_key] = out
        return out

    def wait_for_transaction(self, transaction_id, max_wait_seconds=120):
        return {"success": True, "tx_hash": "0xentry"}


@pytest.fixture()
def circle(monkeypatch):
    fake = FakeCircle()
    monkeypatch.setenv("TOURNAMENT_POT_WALLET_ID", "pot-wallet")
    monkeypatch.setenv("TOURNAMENT_MONEY_MODE", "transfer")
    monkeypatch.setattr(tm, "_circle_for_arc", lambda: (fake, "arc"))

    async def _wallet(pid, chain_id="arc"):
        return {"address": f"0xaddr_{pid}", "wallet_id": f"w_{pid}"}

    import gaming.src.backend.services.clawstation_circle as cc

    monkeypatch.setattr(cc, "ensure_user_wallet", _wallet)
    return fake


def _block():
    return {
        "places": [
            {"place": 1, "profile_id": "alice", "amount_usdc": "10.00"},
            {"place": 2, "profile_id": "bob", "amount_usdc": "4.50"},
            {"place": 3, "profile_id": "carol", "amount_usdc": "0"},
        ]
    }


def test_rerun_never_pays_a_place_twice(circle):
    first = asyncio.run(tm.pay_payouts(_block(), cup_code="CUP1"))
    assert first["paid"] is True
    assert len(circle.calls) == 2
    # Ops re-runs with the ORIGINAL (unpaid) block — the table still knows.
    again = asyncio.run(tm.pay_payouts(_block(), cup_code="CUP1"))
    assert len(circle.calls) == 2
    assert all(p["paid"] for p in again["places"])
    # Re-running with the returned block skips without even claiming.
    asyncio.run(tm.pay_payouts(first, cup_code="CUP1"))
    assert len(circle.calls) == 2


def test_concurrent_callers_pay_once(circle):
    async def both():
        return await asyncio.gather(
            tm.pay_payouts(_block(), cup_code="CUP2"), tm.pay_payouts(_block(), cup_code="CUP2")
        )

    asyncio.run(both())
    assert len(circle.calls) == 2  # one per non-zero place


def test_idempotency_key_is_deterministic_per_place(circle):
    asyncio.run(tm.pay_payouts(_block(), cup_code="CUP3"))
    keys = [c[3] for c in circle.calls]
    assert keys[0] == tm.payout_idempotency_key("CUP3", 1, "alice", Decimal("10.00"))
    assert keys[0] != keys[1]
    assert tm.payout_idempotency_key("CUP3", 1, "alice", Decimal("10")) == keys[0]


def test_failed_place_retries_with_the_same_key(monkeypatch, circle):
    circle.fail_first = True
    out = asyncio.run(tm.pay_payouts(_block(), cup_code="CUP4"))
    assert out["paid"] is False
    asyncio.run(tm.pay_payouts(_block(), cup_code="CUP4"))
    alice_keys = {c[3] for c in circle.calls if c[1] == "0xaddr_alice"}
    assert len(alice_keys) == 1
    assert len(circle.by_key) == 2  # alice once, bob once


def test_client_without_idempotency_support_is_refused(monkeypatch):
    class OldCircle:
        def transfer_usdc(self, wallet_id, to_address, amount_usdc):
            raise AssertionError("must not be called without a key")

    monkeypatch.setenv("TOURNAMENT_POT_WALLET_ID", "pot-wallet")
    monkeypatch.setattr(tm, "_circle_for_arc", lambda: (OldCircle(), "arc"))

    async def _wallet(pid, chain_id="arc"):
        return {"address": "0xa"}

    import gaming.src.backend.services.clawstation_circle as cc

    monkeypatch.setattr(cc, "ensure_user_wallet", _wallet)
    out = asyncio.run(tm.pay_payouts(_block(), cup_code="CUP5"))
    assert out["paid"] is False
    assert "idempotency" in out["places"][0]["pay_note"]


def test_lock_entry_waits_with_the_real_parameter(monkeypatch, circle):
    async def _ok(*a, **k):
        return None

    monkeypatch.setattr(tm, "assert_can_pay_entry", _ok)
    monkeypatch.setenv("TOURNAMENT_POT_ADDRESS", "0xpot")
    out = asyncio.run(tm.lock_entry("alice", Decimal("2"), cup_code="CUP6"))
    assert out["tx_hash"] == "0xentry"  # wait_for_transaction(max_wait_seconds=...) ran
