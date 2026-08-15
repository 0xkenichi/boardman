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


def _on_chain_usdc(address: str, chain_id: str) -> tuple[Optional[Decimal], Optional[str]]:
    """Read USDC for an address (sync). Returns (balance, error). error set ⇒ do not treat as $0."""
    if not address or not str(address).startswith("0x"):
        return None, "invalid address"
    cid = normalize_chain_id(chain_id)
    circle = _circle_for_chain(cid)
    if not circle.rpc_url:
        circle.rpc_url = get_rpc_url(cid)
    if not circle.usdc_address:
        circle.usdc_address = get_usdc_address(cid)
    result = circle.get_wallet_balance(address)
    if not result.get("success"):
        return None, str(result.get("error") or "rpc failed")
    return Decimal(str(result.get("balance_usdc", 0))), None


async def _on_chain_usdc_async(
    address: str, chain_id: str
) -> tuple[Optional[Decimal], Optional[str]]:
    """Non-blocking balance read for bot handlers / wallet watch."""
    return await asyncio.to_thread(_on_chain_usdc, address, chain_id)


async def ensure_user_wallet(user_id: str, chain_id: Optional[str] = None) -> dict:
    """Ensure a Circle wallet that can *sign* on the requested chain.

    CRITICAL: never silently mint a second wallet for a chain when one already
    exists. Replacing the play address is how users "lose" funds in the UI
    (money stays on the old address; Wallet shows the new empty one).
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
    prev_deposit = (profile.get("gaming_deposit_address") or "").lower()

    # Fast path: reuse stored play address without a Circle round-trip on every /start.
    # Set REMATCH_VALIDATE_WALLET_EVERY=1 to force Circle GET validation.
    import os

    validate_every = os.getenv("REMATCH_VALIDATE_WALLET_EVERY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if wallet_id and prev_deposit.startswith("0x") and not validate_every:
        return {
            "wallet_id": wallet_id,
            "address": prev_deposit,
            "blockchain": blockchain,
            "chain_id": cid,
        }

    # Validate cached wallet is actually on this blockchain
    if wallet_id:
        fetched = await asyncio.to_thread(circle.get_wallet, wallet_id)
        if fetched.get("success") and fetched.get("wallet_address"):
            wb = (fetched.get("blockchain") or "").upper().replace("_", "-")
            want = blockchain.upper().replace("_", "-")
            if wb and want and wb != want and want not in wb and wb not in want:
                # Wrong chain — do NOT invent a new wallet if we already stored
                # an address with funds; raise so ops can fix mapping.
                logger.error(
                    "[Circle] wallet %s is %s, need %s user=%s — NOT auto-creating",
                    wallet_id,
                    wb,
                    want,
                    user_id[:8],
                )
                raise CircleWalletError(
                    f"Saved wallet is on {wb}, need {want}. Contact support — "
                    f"we will not create a second address (protects your funds)."
                )
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
        # Fetch failed — keep wallet_id, do not create a replacement
        logger.error(
            "[Circle] get_wallet failed for %s user=%s: %s — not creating replacement",
            wallet_id,
            user_id[:8],
            fetched.get("error"),
        )
        if prev_deposit:
            return {
                "wallet_id": wallet_id,
                "address": prev_deposit,
                "blockchain": blockchain,
                "chain_id": cid,
            }
        raise CircleWalletError(
            f"Could not load wallet {wallet_id}: {fetched.get('error')}"
        )

    # No wallet_id for this chain yet — create once
    # If profile already has a deposit address with funds, refuse to orphan it
    if prev_deposit:
        bal, err = _on_chain_usdc(prev_deposit, cid)
        if err is None and bal is not None and bal > Decimal("0.009"):
            logger.error(
                "[Circle] refuse new wallet — %s already holds $%s on %s user=%s",
                prev_deposit[:12],
                bal,
                cid,
                user_id[:8],
            )
            raise CircleWalletError(
                f"You already have ${bal:,.2f} at {prev_deposit}. "
                f"We will not create a second play address. /support"
            )

    result = await asyncio.to_thread(
        circle.create_custodial_wallet_for_user,
        user_id,
        None,
    )
    if not result.get("success"):
        raise CircleWalletError(
            f"Circle wallet creation failed on {blockchain}: {result.get('error')}."
        )

    wallet_id = result["wallet_id"]
    address = result["wallet_address"]
    await _SupabaseProfileStore.set_chain_wallet(user_id, cid, wallet_id, address)
    logger.info(
        "[Circle] NEW wallet %s chain=%s user=%s addr=%s (prev_deposit=%s)",
        wallet_id,
        cid,
        user_id[:8],
        address,
        (prev_deposit or "")[:12],
    )
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
    """Stakeable on-chain USDC at the **play** (Circle) address only.

    RPC failure returns 0 only after logging — prefer get_usdc_balance_strict
    for deposit detection.
    """
    bal, err = await get_usdc_balance_strict(user_id, chain_id=chain_id)
    if err:
        logger.warning("[Circle] balance fail user=%s: %s", user_id[:8], err)
        chain = Decimal("0")
    else:
        chain = bal or Decimal("0")
    try:
        from gaming.src.backend.services.play_adjust import get_adjust

        return max(Decimal("0"), chain + get_adjust(user_id))
    except Exception:
        return chain


async def get_usdc_balance_strict(
    user_id: str, chain_id: Optional[str] = None
) -> tuple[Optional[Decimal], Optional[str]]:
    """Strict balance for play wallet. (balance, error) — never invent $0 on error."""
    cid = normalize_chain_id(chain_id or await get_preferred_chain(user_id))
    try:
        address = await get_deposit_address(user_id, chain_id=cid)
    except Exception as exc:
        return None, str(exc)
    return await _on_chain_usdc_async(address, cid)


async def get_ledger_balance_usdc(user_id: str) -> Decimal:
    """Internal profiles.wallet_balance_usdc (legacy). Not stakeable on-chain."""
    try:
        from backend.supabase_client import get_supabase

        r = (
            get_supabase()
            .table("profiles")
            .select("wallet_balance_usdc")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = (r.data or [None])[0] if r.data else None
        if not row:
            return Decimal("0")
        return Decimal(str(row.get("wallet_balance_usdc") or 0))
    except Exception:
        logger.warning("[Circle] ledger balance failed %s", user_id, exc_info=True)
        return Decimal("0")


async def _candidate_addresses(user_id: str, play_address: str) -> list[str]:
    """All addresses we should scan so we never hide funds after wallet rotation."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(a: Optional[str]) -> None:
        if not a:
            return
        al = a.strip().lower()
        if not al.startswith("0x") or al in seen:
            return
        seen.add(al)
        out.append(al)

    _add(play_address)
    try:
        profile = await _SupabaseProfileStore.get_profile(user_id) or {}
        _add(profile.get("gaming_deposit_address"))
        _add(profile.get("wallet_address"))
        _add(profile.get("linked_wallet"))
        # full profile for withdrawal_wallet if present
        from backend.supabase_client import get_supabase

        r = (
            get_supabase()
            .table("profiles")
            .select("wallet_address,linked_wallet,gaming_deposit_address,withdrawal_wallet")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = (r.data or [None])[0] or {}
        for k in (
            "wallet_address",
            "linked_wallet",
            "gaming_deposit_address",
            "withdrawal_wallet",
        ):
            _add(row.get(k))
    except Exception:
        logger.warning("[Circle] candidate address scan failed", exc_info=True)
    return out


async def get_balance_summary(
    user_id: str, chain_id: Optional[str] = None
) -> dict[str, Any]:
    """Unified wallet snapshot — never hide funds on a linked/old address.

    Returns:
      spendable_usdc   — play wallet only (can stake)
      other_usdc       — max/sum on other known addresses (NOT stakeable until moved)
      other_address    — address holding other_usdc (if any)
      ledger_usdc      — internal DB credit
      address          — play deposit address
      chain_id
      balance_error    — if play wallet RPC failed
    """
    cid = normalize_chain_id(chain_id or await get_preferred_chain(user_id))
    address = ""
    spendable = Decimal("0")
    balance_error = None
    try:
        wallet = await ensure_user_wallet(user_id, chain_id=cid)
        address = (wallet.get("address") or "").lower()
        bal, err = _on_chain_usdc(address, cid)
        if err:
            balance_error = err
        else:
            spendable = bal or Decimal("0")
    except Exception as exc:
        balance_error = str(exc)
        logger.warning("[Circle] spendable summary failed %s", user_id, exc_info=True)

    other_usdc = Decimal("0")
    other_address = ""
    try:
        for addr in await _candidate_addresses(user_id, address):
            if address and addr == address.lower():
                continue
            bal, err = _on_chain_usdc(addr, cid)
            if err or bal is None:
                continue
            if bal > other_usdc:
                other_usdc = bal
                other_address = addr
    except Exception:
        logger.warning("[Circle] other-address scan failed", exc_info=True)

    ledger = await get_ledger_balance_usdc(user_id)
    adjust = Decimal("0")
    try:
        from gaming.src.backend.services.play_adjust import get_adjust

        adjust = get_adjust(user_id)
    except Exception:
        pass
    shown = spendable + adjust
    if shown < 0:
        shown = Decimal("0")
    return {
        "spendable_usdc": shown,
        "chain_usdc": spendable,
        "adjust_usdc": adjust,
        "other_usdc": other_usdc,
        "other_address": other_address,
        "ledger_usdc": ledger,
        "address": address,
        "chain_id": cid,
        "balance_error": balance_error,
    }


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
