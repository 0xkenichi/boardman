"""
ClawStation Circle wallet helpers (multi-chain).

Same deposit *address* is shown to users; USDC lives per-chain.
Circle may need a wallet id per blockchain for contractExecution —
we store those in profiles.gaming_circle_wallets JSON.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from backend.circle_wallet_service import CircleWalletService
from gaming.src.backend.services.chains import (
    default_chain_id,
    get_chain,
    get_circle_blockchain,
    get_circle_usdc_token_id,
    get_rpc_url,
    get_usdc_address,
    list_chains,
    normalize_chain_id,
)

logger = logging.getLogger(__name__)

CIRCLE_BLOCKCHAIN = "BASE-SEPOLIA"


class CircleWalletError(Exception):
    """Raised when a Circle wallet operation fails for a ClawStation user."""


def _circle_for_chain(chain_id: Optional[str] = None) -> CircleWalletService:
    cid = normalize_chain_id(chain_id or default_chain_id())
    return CircleWalletService(
        blockchain=get_circle_blockchain(cid),
        usdc_address=get_usdc_address(cid),
        usdc_token_id=get_circle_usdc_token_id(cid) or None,
        rpc_url=get_rpc_url(cid),
    )


class _SupabaseProfileStore:
    @staticmethod
    async def _get_supabase():
        from backend.supabase_client import get_supabase

        return get_supabase()

    @staticmethod
    async def get_profile(user_id: str) -> Optional[dict]:
        sb = await _SupabaseProfileStore._get_supabase()
        selects = [
            "id, gaming_deposit_address, circle_wallet_id, "
            "gaming_preferred_chain, gaming_circle_wallets",
            "id, gaming_deposit_address, circle_wallet_id, gaming_circle_wallets",
            "id, gaming_deposit_address, circle_wallet_id",
        ]
        result = None
        for cols in selects:
            try:
                result = (
                    sb.table("profiles")
                    .select(cols)
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
                break
            except Exception:
                result = None
                continue
        if result is None:
            return None
        data = result.data
        if isinstance(data, list):
            return data[0] if data else None
        return data

    @staticmethod
    async def set_deposit_address(user_id: str, wallet_id: str, address: str) -> None:
        sb = await _SupabaseProfileStore._get_supabase()
        sb.table("profiles").update(
            {
                "circle_wallet_id": wallet_id,
                "gaming_deposit_address": address.lower(),
            }
        ).eq("id", user_id).execute()

    @staticmethod
    async def set_chain_wallet(
        user_id: str, chain_id: str, wallet_id: str, address: str
    ) -> None:
        sb = await _SupabaseProfileStore._get_supabase()
        profile = await _SupabaseProfileStore.get_profile(user_id) or {}
        wallets = dict(profile.get("gaming_circle_wallets") or {})
        wallets[chain_id] = wallet_id
        update = {
            "gaming_circle_wallets": wallets,
            "gaming_deposit_address": (address or profile.get("gaming_deposit_address") or "").lower(),
        }
        # Keep legacy circle_wallet_id as primary (base) if unset
        if not profile.get("circle_wallet_id") or chain_id == "base":
            update["circle_wallet_id"] = wallet_id
        try:
            sb.table("profiles").update(update).eq("id", user_id).execute()
        except Exception:
            # Column missing — just set deposit + circle_wallet_id
            sb.table("profiles").update(
                {
                    "circle_wallet_id": wallet_id,
                    "gaming_deposit_address": address.lower(),
                }
            ).eq("id", user_id).execute()

    @staticmethod
    async def set_preferred_chain(user_id: str, chain_id: str) -> None:
        sb = await _SupabaseProfileStore._get_supabase()
        try:
            sb.table("profiles").update(
                {"gaming_preferred_chain": normalize_chain_id(chain_id)}
            ).eq("id", user_id).execute()
        except Exception as exc:
            logger.warning("[Circle] preferred_chain update failed: %s", exc)


async def get_preferred_chain(user_id: str) -> str:
    profile = await _SupabaseProfileStore.get_profile(user_id)
    pref = (profile or {}).get("gaming_preferred_chain")
    if pref:
        try:
            return normalize_chain_id(pref)
        except ValueError:
            pass
    return default_chain_id()


async def set_preferred_chain(user_id: str, chain_id: str) -> str:
    cid = normalize_chain_id(chain_id)
    await _SupabaseProfileStore.set_preferred_chain(user_id, cid)
    return cid


async def ensure_user_wallet(user_id: str, chain_id: Optional[str] = None) -> dict:
    """Ensure a Circle wallet that can *sign* on the requested chain.

    Circle developer EOAs are bound to one blockchain. Reusing the Base
    wallet_id for Arc/Avalanche makes contractExecution run on BASE-SEPOLIA
    (createMatch then fails). We store one Circle wallet id per chain in
    ``gaming_circle_wallets``.
    """
    try:
        UUID(user_id)
    except Exception as exc:
        raise CircleWalletError(f"Invalid user_id: {user_id}") from exc

    cid = normalize_chain_id(chain_id or await get_preferred_chain(user_id) or "arc")
    blockchain = get_circle_blockchain(cid)

    profile = await _SupabaseProfileStore.get_profile(user_id)
    if profile is None:
        raise CircleWalletError(f"Profile not found for user {user_id}")

    wallets_map = dict(profile.get("gaming_circle_wallets") or {})
    # Per-chain wallet only — do NOT fall back to Base wallet for other chains
    wallet_id = wallets_map.get(cid)
    if not wallet_id and cid == "base":
        wallet_id = profile.get("circle_wallet_id")

    circle = _circle_for_chain(cid)

    # Validate cached wallet is actually on this blockchain
    if wallet_id:
        fetched = circle.get_wallet(wallet_id)
        if fetched.get("success") and fetched.get("wallet_address"):
            wb = (fetched.get("blockchain") or "").upper().replace("_", "-")
            want = blockchain.upper().replace("_", "-")
            if wb and want and wb != want and want not in wb and wb not in want:
                logger.warning(
                    "[Circle] wallet %s is %s, need %s — creating chain wallet",
                    wallet_id,
                    wb,
                    want,
                )
                wallet_id = None
            else:
                address = fetched["wallet_address"]
                try:
                    await _SupabaseProfileStore.set_chain_wallet(
                        user_id, cid, wallet_id, address
                    )
                except Exception:
                    pass
                return {
                    "wallet_id": wallet_id,
                    "address": address,
                    "blockchain": fetched.get("blockchain") or blockchain,
                    "chain_id": cid,
                }

    # Create a dedicated Circle wallet on this blockchain
    result = circle.create_custodial_wallet_for_user(
        profile_id=user_id,
        phone_number=None,
    )
    if not result.get("success"):
        raise CircleWalletError(
            f"Circle wallet creation failed on {blockchain}: {result.get('error')}. "
            f"For Arc/Avalanche you need a wallet on that chain — fund the address "
            f"shown after Switch network."
        )

    wallet_id = result["wallet_id"]
    address = result["wallet_address"]
    await _SupabaseProfileStore.set_chain_wallet(user_id, cid, wallet_id, address)
    logger.info("[Circle] Wallet %s chain=%s user=%s addr=%s", wallet_id, cid, user_id, address)
    return {
        "wallet_id": wallet_id,
        "address": address,
        "blockchain": result.get("blockchain") or blockchain,
        "chain_id": cid,
    }


async def get_deposit_address(user_id: str, chain_id: Optional[str] = None) -> str:
    wallet = await ensure_user_wallet(user_id, chain_id=chain_id)
    return wallet["address"]


async def get_usdc_balance(user_id: str, chain_id: Optional[str] = None) -> Decimal:
    """On-chain USDC for the given chain (default: preferred network)."""
    cid = normalize_chain_id(chain_id or await get_preferred_chain(user_id))
    try:
        address = await get_deposit_address(user_id, chain_id=cid)
        circle = _circle_for_chain(cid)
        result = circle.get_wallet_balance(address)
        if result.get("success"):
            return Decimal(str(result.get("balance_usdc", 0)))
        logger.warning("[Circle] balance fail %s %s: %s", user_id, cid, result.get("error"))
    except Exception:
        logger.warning("[Circle] balance exception %s %s", user_id, cid, exc_info=True)
    return Decimal("0")


async def get_all_chain_balances(user_id: str) -> list[dict[str, Any]]:
    """USDC balance per chain.

    Circle uses a **different wallet address per blockchain**. Do not assume
    one deposit address works for signing on every chain.
    """
    out = []
    for c in list_chains():
        cid = c["id"]
        bal = Decimal("0")
        address = ""
        try:
            w = await ensure_user_wallet(user_id, chain_id=cid)
            address = w.get("address") or ""
            bal = await get_usdc_balance(user_id, chain_id=cid)
        except Exception:
            logger.warning("[Circle] balance row failed chain=%s", cid, exc_info=True)
        out.append(
            {
                "id": cid,
                "label": c.get("label", cid),
                "balance_usdc": bal,
                "gas_token": c.get("gas_token"),
                "gas_mode": c.get("gas_mode"),
                "escrow_ready": bool(c.get("escrow_address")),
                "address": address,
                "circle_blockchain": c.get("circle_blockchain"),
            }
        )
    return out


async def expire_pending_deposits() -> int:
    from backend.supabase_client import get_supabase

    sb = get_supabase()
    try:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        result = (
            sb.schema("gaming")
            .table("wallet_credit_audit")
            .update({"status": "expired"})
            .eq("status", "pending")
            .lt("created_at", cutoff)
            .execute()
        )
        expired = len(result.data) if result.data else 0
        logger.info("[DepositExpiry] Expired %s stale pending deposits", expired)
        return expired
    except Exception:
        logger.exception("[DepositExpiry] Failed to expire pending deposits")
        return 0


async def _deposit_expiry_loop(interval_seconds: float = 3600.0) -> None:
    while True:
        try:
            await expire_pending_deposits()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[DepositExpiry] Loop iteration failed")
        await asyncio.sleep(interval_seconds)


def start_deposit_expiry_task(interval_seconds: float = 3600.0) -> asyncio.Task:
    return asyncio.create_task(_deposit_expiry_loop(interval_seconds))
