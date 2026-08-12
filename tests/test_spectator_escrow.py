import asyncio
from decimal import Decimal
import os

import pytest

from backend.services import spectator_escrow


@pytest.mark.asyncio
async def test_deposit_to_pool_success(monkeypatch):
    # Ensure env has escrow address
    monkeypatch.setenv("SPECTATOR_ESCROW_ADDRESS", "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")

    async def fake_ensure_user_wallet(profile_id, chain_id=None):
        return {"wallet_id": "w_test"}

    class FakeCircle:
        async def approve_usdc_transfer(self, wallet_id, amount, escrow_address):
            assert wallet_id == "w_test"
            return {"success": True}

        async def execute_contract_function(self, wallet_id, escrow_address, signature, args):
            assert wallet_id == "w_test"
            return {"success": True, "transaction_id": "tx123", "tx_hash": "0xabc"}

    monkeypatch.setattr(spectator_escrow, "ensure_user_wallet", fake_ensure_user_wallet)
    monkeypatch.setattr(spectator_escrow, "_circle", lambda chain_id: FakeCircle())

    res = await spectator_escrow.deposit_to_pool("profile_1", "match_1", "a", Decimal("1.25"))
    assert res.get("success") is True
    assert "tx_id" in res and res["tx_id"] == "tx123"


@pytest.mark.asyncio
async def test_missing_env_raises(monkeypatch):
    # Ensure escrow address missing
    monkeypatch.delenv("SPECTATOR_ESCROW_ADDRESS", raising=False)
    with pytest.raises(spectator_escrow.SpectatorEscrowError):
        await spectator_escrow.deposit_to_pool("p", "m", "a", Decimal("0.5"))
