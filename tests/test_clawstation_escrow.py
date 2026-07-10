"""gaming/tests/test_clawstation_escrow.py — Unit tests for the on-chain escrow service."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import gaming.src.backend.services.clawstation_escrow as _escrow_module  # noqa: E402
_escrow_module.ESCROW_ADDRESS = "0xEscrowContractAddress"

from gaming.src.backend.services.clawstation_escrow import (  # noqa: E402
    approve_and_create_match,
    approve_and_join_match,
    cancel_match,
    flag_dispute,
    resolve_match,
)


def _mock_supabase(monkeypatch, execute_results):
    """Return a mock supabase where execute() returns results in order."""
    mock = MagicMock()
    execute_iter = iter(execute_results)

    def fake_execute():
        return next(execute_iter)

    mock.schema.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = fake_execute
    mock.schema.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = fake_execute
    mock.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = fake_execute
    mock.schema.return_value.table.return_value.insert.return_value.execute.side_effect = fake_execute
    mock.schema.return_value.table.return_value.update.return_value.eq.return_value.execute.side_effect = fake_execute

    monkeypatch.setattr("gaming.src.backend.services.clawstation_escrow.get_supabase", lambda: mock)
    return mock


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("CLAW_ESCROW_ADDRESS_BASE_SEPOLIA", "0xEscrowContractAddress")


@pytest.mark.asyncio
async def test_approve_and_create_match_approves_and_calls_create_match(monkeypatch):
    mock_ensure = AsyncMock(return_value={"wallet_id": "user_wallet", "address": "0xUser"})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
        "tx_hash": "0xApproveHash",
    }
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_create",
        "tx_hash": "0xCreateHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService", lambda: mock_circle
    )

    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": None,
        "status": "accepted",
        "amount_usdc": 5.0,
    }
    profile_result = MagicMock()
    profile_result.data = {"circle_wallet_id": "user_wallet"}
    audit_result = MagicMock()
    audit_result.data = None
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(
        monkeypatch,
        [challenge_result, profile_result, audit_result, insert_result, update_result],
    )

    result = await approve_and_create_match("user_1", "challenge_1", Decimal("5.0"))

    assert result["success"] is True
    assert result["create_tx_id"] == "tx_create"
    mock_circle.approve_usdc_transfer.assert_called_once_with(
        wallet_id="user_wallet",
        amount_usdc=5.0,
        spender_address="0xEscrowContractAddress",
    )
    mock_circle.execute_contract_function.assert_called_once()
    call_kwargs = mock_circle.execute_contract_function.call_args.kwargs
    assert call_kwargs["wallet_id"] == "user_wallet"
    assert call_kwargs["contract_address"] == "0xEscrowContractAddress"
    assert call_kwargs["function_signature"] == "createMatch(bytes32,uint256)"


@pytest.mark.asyncio
async def test_approve_and_join_match_approves_and_calls_join_match(monkeypatch):
    mock_ensure = AsyncMock(return_value={"wallet_id": "opp_wallet", "address": "0xOpp"})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
        "tx_hash": "0xApproveHash",
    }
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_join",
        "tx_hash": "0xJoinHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService", lambda: mock_circle
    )

    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": "user_2",
        "status": "creator_locked",
        "amount_usdc": 5.0,
        "creator_lock_tx_id": "tx_create",
    }
    profile_result = MagicMock()
    profile_result.data = {"circle_wallet_id": "opp_wallet"}
    audit_result = MagicMock()
    audit_result.data = None
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(
        monkeypatch,
        [challenge_result, profile_result, audit_result, insert_result, update_result],
    )

    result = await approve_and_join_match("user_2", "challenge_1", Decimal("5.0"))

    assert result["success"] is True
    assert result["join_tx_id"] == "tx_join"
    mock_circle.execute_contract_function.assert_called_once()
    call_kwargs = mock_circle.execute_contract_function.call_args.kwargs
    assert call_kwargs["function_signature"] == "joinMatch(bytes32)"


@pytest.mark.asyncio
async def test_resolve_match_calls_blockchain_resolve(monkeypatch):
    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": "user_2",
        "status": "submitted",
        "amount_usdc": 10.0,
        "winner_id": "user_1",
    }
    audit_result = MagicMock()
    audit_result.data = None
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(monkeypatch, [challenge_result, audit_result, insert_result, insert_result, update_result])

    mock_bl = MagicMock()
    mock_bl.resolve_match_onchain = AsyncMock(
        return_value={
            "tx_hash": "0xResolveHash",
            "block": 12345,
            "gas_used": 100000,
            "explorer_url": "https://sepolia.basescan.org/tx/0xResolveHash",
        }
    )
    monkeypatch.setattr(
        "backend.blockchain_layer.get_blockchain_layer", lambda: mock_bl
    )

    result = await resolve_match("challenge_1", "0xWinnerAddress")

    assert result["success"] is True
    assert result["tx_hash"] == "0xResolveHash"
    mock_bl.resolve_match_onchain.assert_awaited_once_with("challenge_1", "0xWinnerAddress")


@pytest.mark.asyncio
async def test_resolve_match_idempotency_guard(monkeypatch):
    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": "user_2",
        "status": "submitted",
        "amount_usdc": 10.0,
        "winner_id": "user_1",
    }
    audit_result = MagicMock()
    audit_result.data = {"circle_tx_id": "old_tx", "tx_hash": "0xOldHash", "status": "confirmed"}

    _mock_supabase(monkeypatch, [challenge_result, audit_result])

    mock_bl = MagicMock()
    monkeypatch.setattr(
        "backend.blockchain_layer.get_blockchain_layer", lambda: mock_bl
    )

    result = await resolve_match("challenge_1", "0xWinnerAddress")

    assert result["tx_hash"] == "0xOldHash"
    mock_bl.resolve_match_onchain.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_match_calls_blockchain_cancel(monkeypatch):
    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": "user_2",
        "status": "locked",
        "amount_usdc": 10.0,
    }
    audit_result = MagicMock()
    audit_result.data = None
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(monkeypatch, [challenge_result, audit_result, insert_result, insert_result, update_result])

    mock_bl = MagicMock()
    mock_bl.cancel_match_onchain = AsyncMock(
        return_value={
            "tx_hash": "0xCancelHash",
            "block": 12345,
            "gas_used": 100000,
            "explorer_url": "https://sepolia.basescan.org/tx/0xCancelHash",
        }
    )
    monkeypatch.setattr(
        "backend.blockchain_layer.get_blockchain_layer", lambda: mock_bl
    )

    result = await cancel_match("challenge_1")

    assert result["success"] is True
    assert result["tx_hash"] == "0xCancelHash"
    mock_bl.cancel_match_onchain.assert_awaited_once_with("challenge_1")


@pytest.mark.asyncio
async def test_flag_dispute_calls_blockchain_flag(monkeypatch):
    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": "user_2",
        "status": "submitted",
        "amount_usdc": 10.0,
    }
    update_result = MagicMock()

    _mock_supabase(monkeypatch, [challenge_result, update_result])

    mock_bl = MagicMock()
    mock_bl.flag_dispute_onchain = AsyncMock(
        return_value={
            "tx_hash": "0xFlagHash",
            "block": 12345,
            "gas_used": 100000,
            "explorer_url": "https://sepolia.basescan.org/tx/0xFlagHash",
        }
    )
    monkeypatch.setattr(
        "backend.blockchain_layer.get_blockchain_layer", lambda: mock_bl
    )

    result = await flag_dispute("challenge_1")

    assert result["success"] is True
    assert result["tx_hash"] == "0xFlagHash"
    mock_bl.flag_dispute_onchain.assert_awaited_once_with("challenge_1")
