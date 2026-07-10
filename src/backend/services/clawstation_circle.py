"""
gaming/src/backend/services/clawstation_circle.py

ClawStation-specific wrapper around the shared Circle Programmable Wallets
service (``backend/circle_wallet_service.py``).

Responsibilities:
    - Ensure every ClawStation user has a Circle developer-controlled wallet.
    - Cache the wallet id and deposit address in ``public.profiles``.
    - Read USDC balances (Circle API or local cached balance).
    - Provide a background expiry stub for stale pending deposits.

Environment:
    CIRCLE_API_KEY, CIRCLE_CLIENT_KEY, CIRCLE_ENTITY_SECRET,
    CIRCLE_WALLET_SET_ID, USDC_ADDRESS, RPC_URL — consumed by the shared
    ``CircleWalletService``.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from backend.circle_wallet_service import CircleWalletService

logger = logging.getLogger(__name__)

# Stable blockchain label used by Circle for Base Sepolia.
CIRCLE_BLOCKCHAIN = "BASE-SEPOLIA"


class CircleWalletError(Exception):
    """Raised when a Circle wallet operation fails for a ClawStation user."""


class _SupabaseProfileStore:
    """Thin async wrapper around Supabase profile reads/writes.

    Kept local to this module so the service does not depend on the full
    ``backend/`` import graph beyond ``db_layer_blockchain``.
    """

    @staticmethod
    async def _get_supabase():
        from backend.supabase_client import get_supabase

        return get_supabase()

    @staticmethod
    async def get_profile(user_id: str) -> Optional[dict]:
        sb = await _SupabaseProfileStore._get_supabase()
        result = (
            sb.table("profiles")
            .select("id, gaming_deposit_address, circle_wallet_id")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result.data else None

    @staticmethod
    async def set_deposit_address(user_id: str, wallet_id: str, address: str) -> None:
        sb = await _SupabaseProfileStore._get_supabase()
        sb.table("profiles").update(
            {
                "circle_wallet_id": wallet_id,
                "gaming_deposit_address": address.lower(),
            }
        ).eq("id", user_id).execute()


async def ensure_user_wallet(user_id: str) -> dict:
    """Ensure ``user_id`` has a Circle wallet, caching it on ``public.profiles``.

    Returns:
        ``{"wallet_id": str, "address": str, "blockchain": str}``

    Raises:
        CircleWalletError: if the user does not exist or Circle creation fails.
    """
    try:
        UUID(user_id)
    except Exception as exc:
        raise CircleWalletError(f"Invalid user_id: {user_id}") from exc

    profile = await _SupabaseProfileStore.get_profile(user_id)
    if profile is None:
        raise CircleWalletError(f"Profile not found for user {user_id}")

    cached_address = profile.get("gaming_deposit_address")
    cached_wallet_id = profile.get("circle_wallet_id")
    if cached_address and cached_wallet_id:
        logger.info("[Circle] Using cached wallet %s for user %s", cached_wallet_id, user_id)
        return {
            "wallet_id": cached_wallet_id,
            "address": cached_address,
            "blockchain": CIRCLE_BLOCKCHAIN,
        }

    circle = CircleWalletService()
    result = circle.create_custodial_wallet_for_user(
        profile_id=user_id,
        phone_number=None,
    )
    if not result.get("success"):
        raise CircleWalletError(f"Circle wallet creation failed: {result.get('error')}")

    wallet_id = result["wallet_id"]
    address = result["wallet_address"]

    await _SupabaseProfileStore.set_deposit_address(user_id, wallet_id, address)
    logger.info("[Circle] Created wallet %s for user %s", wallet_id, user_id)
    return {
        "wallet_id": wallet_id,
        "address": address,
        "blockchain": CIRCLE_BLOCKCHAIN,
    }


async def get_deposit_address(user_id: str) -> str:
    """Return the cached Circle deposit address for ``user_id`` or create one."""
    wallet = await ensure_user_wallet(user_id)
    return wallet["address"]


async def get_usdc_balance(user_id: str) -> Decimal:
    """Return the user's USDC balance.

    Preference:
        1. Local cached balance from ``public.profiles.wallet_balance_usdc``
           (fast, used for gameplay decisions).
        2. On-chain Circle wallet balance via the Circle API if the cached
           value is missing.
    """
    sb = await _SupabaseProfileStore._get_supabase()
    try:
        result = (
            sb.table("profiles")
            .select("wallet_balance_usdc")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if result.data:
            local = result.data.get("wallet_balance_usdc")
            if local is not None and Decimal(str(local)) > 0:
                return Decimal(str(local))
    except Exception:
        logger.warning("[Circle] Failed to read local balance for %s", user_id, exc_info=True)

    address = await get_deposit_address(user_id)
    circle = CircleWalletService()
    result = circle.get_wallet_balance(address)
    if not result.get("success"):
        raise CircleWalletError(f"Failed to fetch on-chain balance: {result.get('error')}")
    return Decimal(str(result.get("balance_usdc", 0)))


async def expire_pending_deposits() -> int:
    """Background job stub: expire stale pending deposits older than 24 hours.

    ``gaming.wallet_credit_audit`` rows with ``status = 'pending'`` older than
    24 hours are flipped to ``'expired'``. In the current flow, webhook credits
    are inserted with ``status = 'credited'``, so this job typically returns 0
    until an explicit pending-deposit state is introduced.

    Returns:
        Number of rows marked expired.
    """
    from backend.supabase_client import get_supabase

    sb = get_supabase()
    try:
        result = (
            sb.table("wallet_credit_audit")
            .update({"status": "expired"})
            .eq("status", "pending")
            .lt("created_at", "now() - interval '24 hours'")
            .execute()
        )
        expired = len(result.data) if result.data else 0
        logger.info("[DepositExpiry] Expired %s stale pending deposits", expired)
        return expired
    except Exception:
        logger.exception("[DepositExpiry] Failed to expire pending deposits")
        return 0


async def _deposit_expiry_loop(interval_seconds: float = 3600.0) -> None:
    """Run ``expire_pending_deposits`` forever with ``interval_seconds`` sleep."""
    while True:
        try:
            await expire_pending_deposits()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[DepositExpiry] Loop iteration failed")
        await asyncio.sleep(interval_seconds)


def start_deposit_expiry_task(interval_seconds: float = 3600.0) -> asyncio.Task:
    """Create and return the background expiry task.

    The caller (``gaming/src/backend/main.py``) is responsible for awaiting
    the task on shutdown.
    """
    return asyncio.create_task(_deposit_expiry_loop(interval_seconds))
