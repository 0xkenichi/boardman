"""
Spectator escrow wrapper — approve + deposit to a separate spectator pool contract.

This is a lightweight wrapper modeled after `clawstation_escrow` but focused on
depositing spectator bets into a separate contract (if `SPECTATOR_ONCHAIN=1`).
If the on-chain flow fails, callers should fall back to the existing internal
`debit_wallet` path.
"""
from __future__ import annotations

import hashlib
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

    chain_id = normalize_chain_id(os.getenv("SPECTATOR_CHAIN") or default_chain_id())
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
    approve = await circle.approve_usdc_transfer(wallet_id, float(amount), escrow_address)
    if not approve.get("success"):
        raise SpectatorEscrowError(f"approve failed: {approve.get('error')}")

    # Execute deposit contract call. ABI expected: deposit(bytes32,uint256,uint8)
    match_bytes = _match_bytes32(match_id)
    side_idx = 0 if str(side).lower() in ("a", "raja", "white") else 1
    wei = int(amount * Decimal(10 ** USDC_DECIMALS))

    # Try to execute contract function; this uses Circle's execute_contract_function wrapper
    logger.info("[SpectatorEscrow] deposit_to_pool user=%s match=%s side=%s wei=%s", profile_id, match_id, side_idx, wei)
    res = await circle.execute_contract_function(wallet_id, escrow_address, "deposit(bytes32,uint256,uint8)", [match_bytes, str(wei), side_idx])
    if not res.get("success"):
        raise SpectatorEscrowError(f"deposit failed: {res.get('error')}")

    tx_id = res.get("transaction_id")
    tx_hash = res.get("tx_hash") or ""
    explorer = get_explorer_tx(chain_id, tx_hash) if tx_hash else ""
    return {"success": True, "tx_id": tx_id, "tx_hash": tx_hash, "explorer_url": explorer}
