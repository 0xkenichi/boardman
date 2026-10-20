"""
Spectator escrow wrapper — approve + deposit to a separate spectator pool contract.

This is a lightweight wrapper modeled after `clawstation_escrow` but focused on
depositing spectator bets into a separate contract (if `SPECTATOR_ONCHAIN=1`).
If the on-chain flow fails, callers should fall back to the existing internal
`debit_wallet` path.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import os
from decimal import Decimal
from typing import Any, Optional

from backend.circle_wallet_service import CircleWalletService
from backend.supabase_client import get_supabase
from gaming.src.backend.services.chains import (
    get_circle_blockchain,
    get_usdc_address,
    get_circle_usdc_token_id,
    get_rpc_url,
    normalize_chain_id,
    default_chain_id,
    get_explorer_tx,
)
from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6


class SpectatorEscrowError(Exception):
    pass


def _circle(chain_id: str) -> CircleWalletService:
    return CircleWalletService(
        blockchain=get_circle_blockchain(chain_id),
        usdc_address=get_usdc_address(chain_id),
        usdc_token_id=get_circle_usdc_token_id(chain_id),
        rpc_url=get_rpc_url(chain_id),
    )


def _match_bytes32(match_id: str) -> str:
    return "0x" + hashlib.sha256(match_id.encode()).hexdigest()


def _side_index(side: str) -> int:
    """0 = agent A, 1 = agent B, 2 = draw (SpectatorPool deposit side)."""
    s = str(side or "").strip().lower()
    if s in ("a", "0", "raja", "white"):
        return 0
    if s in ("draw", "d", "tie", "2"):
        return 2
    return 1


async def _call_off_loop(fn, *args, **kwargs):
    """Run a Circle wallet call without blocking the event loop.

    CircleWalletService methods are synchronous (blocking HTTP); awaiting
    their dict result raised ``TypeError`` on every call. Run them in a
    worker thread instead, and still accept an async implementation (test
    doubles) by awaiting the coroutine it returns.
    """
    res = await asyncio.to_thread(fn, *args, **kwargs)
    if inspect.isawaitable(res):
        res = await res
    return res


async def deposit_to_pool(profile_id: str, match_id: str, side: str, amount: Decimal) -> dict[str, Any]:
    """Approve USDC and deposit to the spectator pool contract.

    Returns dict with keys: success(bool), tx_id, tx_hash, explorer_url.
    Raises SpectatorEscrowError on unrecoverable failure.
    """
    mid = (match_id or "").strip()
    if not mid or mid.lower() in {"arena", "live"}:
        raise SpectatorEscrowError(
            "spectator on-chain requires a live match_id, not 'arena'"
        )

    from gaming.src.backend.services.realms import assert_practice

    # Spectator pools are arena money: practice chains only (realms.py).
    chain_id = assert_practice(
        normalize_chain_id(os.getenv("SPECTATOR_CHAIN") or default_chain_id()), path="spectator pool deposit"
    )
    escrow_address = os.getenv("SPECTATOR_ESCROW_ADDRESS")
    if not escrow_address:
        raise SpectatorEscrowError("SPECTATOR_ESCROW_ADDRESS not configured")

    # Ensure user's Circle wallet on the settlement chain
    try:
        wallet = await ensure_user_wallet(profile_id, chain_id=chain_id)
    except Exception as exc:
        raise SpectatorEscrowError(f"ensure_user_wallet failed: {exc}") from exc
    wallet_id = wallet.get("wallet_id")

    circle = _circle(chain_id)

    # Approve token transfer to spectator contract
    logger.info("[SpectatorEscrow] Approving USDC for user=%s amount=%s to %s", profile_id, amount, escrow_address)
    approve = await _call_off_loop(
        circle.approve_usdc_transfer, wallet_id, float(amount), escrow_address
    )
    if not approve.get("success"):
        raise SpectatorEscrowError(f"approve failed: {approve.get('error')}")
    # Wait for the approve to land, or the deposit reverts on allowance.
    approve_tx_id = approve.get("transaction_id")
    waiter = getattr(circle, "wait_for_transaction_async", None)
    if approve_tx_id and waiter is not None:
        approve_wait = await waiter(approve_tx_id, max_wait_seconds=90)
        if not approve_wait.get("success"):
            raise SpectatorEscrowError(f"approve not confirmed: {approve_wait.get('error')}")

    # Execute deposit contract call. ABI expected: deposit(bytes32,uint256,uint8)
    match_bytes = _match_bytes32(match_id)
    side_idx = _side_index(side)  # v1 mapped "draw" to side B
    wei = int(amount * Decimal(10 ** USDC_DECIMALS))

    # Try to execute contract function; this uses Circle's execute_contract_function wrapper
    logger.info("[SpectatorEscrow] deposit_to_pool user=%s match=%s side=%s wei=%s", profile_id, match_id, side_idx, wei)
    res = await _call_off_loop(
        circle.execute_contract_function,
        wallet_id,
        escrow_address,
        "deposit(bytes32,uint256,uint8)",
        [match_bytes, str(wei), side_idx],
    )
    if not res.get("success"):
        raise SpectatorEscrowError(f"deposit failed: {res.get('error')}")

    tx_id = res.get("transaction_id")
    tx_hash = res.get("tx_hash") or ""
    explorer = get_explorer_tx(chain_id, tx_hash) if tx_hash else ""
    return {"success": True, "tx_id": tx_id, "tx_hash": tx_hash, "explorer_url": explorer}
