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

from gaming.src.backend.services.clawstation_escrow import (  # noqa: E402
    EscrowError,
    approve_and_create_match,
    approve_and_join_match,
    cancel_match,
    flag_dispute,
    resolve_match,
)

# Valid-looking checksum placeholders for multi-chain config / Web3
_ESCROW = "0xDb76714390ccE1729558DF3c9EC4f45A1690dE78"
_USER = "0xa51fbdcc5fe502d6a74044322ef605e7abfbec5d"
_OPP = "0x95cff0fd86f0f62502178dc0fc0f79472659a16d"


def _mock_supabase(monkeypatch, execute_results):
    """Return a mock supabase where execute() returns results in order."""
    mock = MagicMock()
    execute_iter = iter(execute_results)

    def fake_execute(*_a, **_k):
        return next(execute_iter)

    # Flexible chain: select/eq/in_/limit/maybe_single/insert/update all return mock
    q = mock.schema.return_value.table.return_value
    for meth in ("select", "eq", "in_", "limit", "maybe_single", "insert", "update"):
        getattr(q, meth).return_value = q
    q.execute.side_effect = fake_execute

    t = mock.table.return_value
    for meth in ("select", "eq", "maybe_single"):
        getattr(t, meth).return_value = t
    t.execute.side_effect = fake_execute

    monkeypatch.setattr("gaming.src.backend.services.clawstation_escrow.get_supabase", lambda: mock)
    return mock


def _row(data):
    """Execute result whose ``.data`` is set (list or dict)."""
    r = MagicMock()
    r.data = data
    return r


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("CLAW_ESCROW_ADDRESS_BASE_SEPOLIA", _ESCROW)
    monkeypatch.setenv("CSC_ADDRESS", _ESCROW)
    # Skip real gas tank RPC in unit tests
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_native_gas",
        lambda *a, **k: {"ok": True, "action": "already_funded"},
    )
    # Force chain config escrow
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.get_escrow_address",
        lambda chain_id: _ESCROW,
    )


@pytest.mark.asyncio
async def test_approve_and_create_match_approves_and_calls_create_match(monkeypatch):
    mock_ensure = AsyncMock(return_value={"wallet_id": "user_wallet", "address": _USER})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
        "tx_hash": "0xApproveHash",
    }
    # The service awaits wait_for_transaction_async directly (approve + create)
    mock_circle.wait_for_transaction_async = AsyncMock(
        return_value={"success": True, "tx_hash": "0xCreateHash"}
    )
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_create",
        "tx_hash": "0xCreateHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService",
        lambda **kwargs: mock_circle,
    )

    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": None,
        "status": "accepted",
        "amount_usdc": 5.0,
        "settlement_chain": "base",
    }
    audit_empty = MagicMock()
    audit_empty.data = []
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(
        monkeypatch,
        [challenge_result, audit_empty, insert_result, update_result],
    )

    result = await approve_and_create_match("user_1", "challenge_1", Decimal("5.0"))

    assert result["success"] is True
    assert result["create_tx_id"] == "tx_create"
    # The service calls Circle methods positionally via asyncio.to_thread
    mock_circle.approve_usdc_transfer.assert_called_once_with(
        "user_wallet", 5.0, _ESCROW
    )
    mock_circle.execute_contract_function.assert_called_once()
    call_args = mock_circle.execute_contract_function.call_args
    assert call_args.args[0] == "user_wallet"
    assert call_args.args[1] == _ESCROW
    assert call_args.args[2] == "createMatch(bytes32,uint256)"


@pytest.mark.asyncio
async def test_approve_and_join_match_approves_and_calls_join_match(monkeypatch):
    mock_ensure = AsyncMock(return_value={"wallet_id": "opp_wallet", "address": _OPP})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
        "tx_hash": "0xApproveHash",
    }
    # The service awaits wait_for_transaction_async directly (approve + join)
    mock_circle.wait_for_transaction_async = AsyncMock(
        return_value={"success": True, "tx_hash": "0xJoinHash"}
    )
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_join",
        "tx_hash": "0xJoinHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService",
        lambda **kwargs: mock_circle,
    )

    challenge_result = MagicMock()
    challenge_result.data = {
        "id": "challenge_1",
        "creator_id": "user_1",
        "opponent_id": "user_2",
        "status": "creator_locked",
        "amount_usdc": 5.0,
        "creator_lock_tx_id": "tx_create",
        "settlement_chain": "base",
    }
    audit_empty = MagicMock()
    audit_empty.data = []
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(
        monkeypatch,
        [challenge_result, audit_empty, insert_result, update_result],
    )

    result = await approve_and_join_match("user_2", "challenge_1", Decimal("5.0"))

    assert result["success"] is True
    assert result["join_tx_id"] == "tx_join"
    mock_circle.execute_contract_function.assert_called_once()
    call_args = mock_circle.execute_contract_function.call_args
    assert call_args.args[0] == "opp_wallet"
    assert call_args.args[1] == _ESCROW
    assert call_args.args[2] == "joinMatch(bytes32)"


# ── wait path (wait_for_transaction_async) ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_match_approve_wait_failure_raises(monkeypatch):
    """Approve tx never confirms -> EscrowError, createMatch is not sent."""
    mock_ensure = AsyncMock(return_value={"wallet_id": "user_wallet", "address": _USER})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
    }
    mock_circle.wait_for_transaction_async = AsyncMock(
        return_value={"success": False, "error": "approve timeout"}
    )
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService",
        lambda **kwargs: mock_circle,
    )

    _mock_supabase(
        monkeypatch,
        [
            _row(
                {
                    "id": "challenge_1",
                    "creator_id": "user_1",
                    "opponent_id": None,
                    "status": "accepted",
                    "amount_usdc": 5.0,
                    "settlement_chain": "base",
                }
            ),
            _row([]),
            MagicMock(),
            MagicMock(),
        ],
    )

    with pytest.raises(EscrowError, match="approve not confirmed"):
        await approve_and_create_match("user_1", "challenge_1", Decimal("5.0"))
    mock_circle.wait_for_transaction_async.assert_awaited_once_with(
        "tx_approve", max_wait_seconds=90
    )
    mock_circle.execute_contract_function.assert_not_called()


@pytest.mark.asyncio
async def test_create_match_create_wait_failure_raises(monkeypatch):
    """createMatch tx never confirms -> EscrowError."""
    mock_ensure = AsyncMock(return_value={"wallet_id": "user_wallet", "address": _USER})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
    }
    mock_circle.wait_for_transaction_async = AsyncMock(
        side_effect=[
            {"success": True, "tx_hash": "0xApproveHash"},
            {"success": False, "error": "create timeout"},
        ]
    )
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_create",
        "tx_hash": "0xCreateHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService",
        lambda **kwargs: mock_circle,
    )

    _mock_supabase(
        monkeypatch,
        [
            _row(
                {
                    "id": "challenge_1",
                    "creator_id": "user_1",
                    "opponent_id": None,
                    "status": "accepted",
                    "amount_usdc": 5.0,
                    "settlement_chain": "base",
                }
            ),
            _row([]),
            MagicMock(),
            MagicMock(),
        ],
    )

    with pytest.raises(EscrowError, match="createMatch not confirmed"):
        await approve_and_create_match("user_1", "challenge_1", Decimal("5.0"))
    mock_circle.wait_for_transaction_async.assert_awaited_with(
        "tx_create", max_wait_seconds=120
    )


@pytest.mark.asyncio
async def test_create_match_skips_wait_when_approve_has_no_transaction_id(monkeypatch):
    """No approve transaction_id -> wait skipped; only the create tx is polled."""
    mock_ensure = AsyncMock(return_value={"wallet_id": "user_wallet", "address": _USER})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {"success": True}  # already confirmed
    mock_circle.wait_for_transaction_async = AsyncMock(
        return_value={"success": True, "tx_hash": "0xCreateHash"}
    )
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_create",
        "tx_hash": "0xCreateHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService",
        lambda **kwargs: mock_circle,
    )

    _mock_supabase(
        monkeypatch,
        [
            _row(
                {
                    "id": "challenge_1",
                    "creator_id": "user_1",
                    "opponent_id": None,
                    "status": "accepted",
                    "amount_usdc": 5.0,
                    "settlement_chain": "base",
                }
            ),
            _row([]),
            MagicMock(),
            MagicMock(),
        ],
    )

    result = await approve_and_create_match("user_1", "challenge_1", Decimal("5.0"))

    assert result["success"] is True
    assert result["create_tx_id"] == "tx_create"
    # Only the create wait is polled — the approve wait is skipped
    mock_circle.wait_for_transaction_async.assert_awaited_once_with(
        "tx_create", max_wait_seconds=120
    )


@pytest.mark.asyncio
async def test_join_match_join_wait_failure_raises(monkeypatch):
    """joinMatch tx never confirms -> EscrowError."""
    mock_ensure = AsyncMock(return_value={"wallet_id": "opp_wallet", "address": _OPP})
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.ensure_user_wallet", mock_ensure
    )

    mock_circle = MagicMock()
    mock_circle.approve_usdc_transfer.return_value = {
        "success": True,
        "transaction_id": "tx_approve",
    }
    mock_circle.wait_for_transaction_async = AsyncMock(
        side_effect=[
            {"success": True, "tx_hash": "0xApproveHash"},
            {"success": False, "error": "join timeout"},
        ]
    )
    mock_circle.execute_contract_function.return_value = {
        "success": True,
        "transaction_id": "tx_join",
        "tx_hash": "0xJoinHash",
    }
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.CircleWalletService",
        lambda **kwargs: mock_circle,
    )

    _mock_supabase(
        monkeypatch,
        [
            _row(
                {
                    "id": "challenge_1",
                    "creator_id": "user_1",
                    "opponent_id": "user_2",
                    "status": "creator_locked",
                    "amount_usdc": 5.0,
                    "creator_lock_tx_id": "tx_create",
                    "settlement_chain": "base",
                }
            ),
            _row([]),
            MagicMock(),
            MagicMock(),
        ],
    )

    with pytest.raises(EscrowError, match="joinMatch not confirmed"):
        await approve_and_join_match("user_2", "challenge_1", Decimal("5.0"))
    mock_circle.wait_for_transaction_async.assert_awaited_with(
        "tx_join", max_wait_seconds=120
    )


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
        "settlement_chain": "base",
    }
    audit_empty = MagicMock()
    audit_empty.data = []
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(monkeypatch, [challenge_result, audit_empty, insert_result, insert_result, update_result])

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
        "backend.blockchain_layer.get_blockchain_layer_for_chain", lambda chain: mock_bl
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
        "settlement_chain": "base",
    }
    audit_result = MagicMock()
    audit_result.data = [{"circle_tx_id": "old_tx", "tx_hash": "0xOldHash", "status": "confirmed"}]

    _mock_supabase(monkeypatch, [challenge_result, audit_result])

    mock_bl = MagicMock()
    monkeypatch.setattr(
        "backend.blockchain_layer.get_blockchain_layer_for_chain", lambda chain: mock_bl
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
        "settlement_chain": "base",
    }
    audit_empty = MagicMock()
    audit_empty.data = []
    insert_result = MagicMock()
    update_result = MagicMock()

    _mock_supabase(monkeypatch, [challenge_result, audit_empty, insert_result, insert_result, update_result])

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
        "backend.blockchain_layer.get_blockchain_layer_for_chain", lambda chain: mock_bl
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
        "settlement_chain": "base",
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
        "backend.blockchain_layer.get_blockchain_layer_for_chain", lambda chain: mock_bl
    )

    result = await flag_dispute("challenge_1")

    assert result["success"] is True
    assert result["tx_hash"] == "0xFlagHash"
    mock_bl.flag_dispute_onchain.assert_awaited_once_with("challenge_1")
