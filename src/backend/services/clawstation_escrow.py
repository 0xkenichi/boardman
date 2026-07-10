"""
gaming/src/backend/services/clawstation_escrow.py
────────────────────────────────────────────────
Non-custodial on-chain escrow integration for ClawStation.

Wraps Circle developer-controlled wallets and the deployed ClawEscrow.sol
contract so Telegram-bot players can lock stakes, settle matches, and receive
payouts without sideQuest ever taking custody of the funds.
"""
from __future__ import annotations

import hashlib
import logging
import os
from decimal import Decimal
from typing import Optional

from backend.circle_wallet_service import CircleWalletService
from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6
ESCROW_ADDRESS = os.getenv(
    "CLAW_ESCROW_ADDRESS_BASE_SEPOLIA",
    os.getenv("CSC_ADDRESS", ""),
)


class EscrowError(Exception):
    """Raised when a ClawEscrow operation fails."""


class EscrowNotConfiguredError(EscrowError):
    """Raised when the escrow contract address or keys are missing."""


def _require_env() -> None:
    if not ESCROW_ADDRESS or ESCROW_ADDRESS in ("0x...", "0x0000", ""):
        raise EscrowNotConfiguredError(
            "CLAW_ESCROW_ADDRESS_BASE_SEPOLIA / CSC_ADDRESS is not configured"
        )


def _challenge_id_to_bytes32(challenge_id: str) -> str:
    """Hash a challenge UUID into a 0x-prefixed 64-char bytes32 hex string."""
    return "0x" + hashlib.sha256(challenge_id.encode()).hexdigest()


def _usdc_to_wei(amount_usd: Decimal) -> int:
    return int(amount_usd * Decimal(10**USDC_DECIMALS))


def _circle() -> CircleWalletService:
    return CircleWalletService()


def _get_supabase():
    return get_supabase()


def _load_profile_wallet_id(profile_id: str) -> str:
    sb = _get_supabase()
    result = (
        sb.table("profiles")
        .select("circle_wallet_id")
        .eq("id", profile_id)
        .maybe_single()
        .execute()
    )
    if not result.data or not result.data.get("circle_wallet_id"):
        raise EscrowError(f"User {profile_id} has no Circle wallet")
    return result.data["circle_wallet_id"]


def _load_challenge(challenge_id: str) -> dict:
    sb = _get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise EscrowError(f"Challenge {challenge_id} not found")
    return result.data


def _record_audit(
    challenge_id: str,
    profile_id: Optional[str],
    movement: str,
    amount: Decimal,
    idempotency_key: str,
    circle_tx_id: Optional[str] = None,
    tx_hash: Optional[str] = None,
    status: str = "pending",
    metadata: Optional[dict] = None,
) -> None:
    """Insert an immutable audit row."""
    sb = _get_supabase()
    sb.schema("gaming").table("escrow_audit").insert(
        {
            "challenge_id": challenge_id,
            "profile_id": profile_id,
            "movement": movement,
            "amount_usdc": float(amount),
            "circle_tx_id": circle_tx_id,
            "tx_hash": tx_hash,
            "idempotency_key": idempotency_key,
            "status": status,
            "metadata": metadata or {},
        }
    ).execute()


def _find_existing_audit(challenge_id: str, movement: str) -> Optional[dict]:
    sb = _get_supabase()
    result = (
        sb.schema("gaming")
        .table("escrow_audit")
        .select("*")
        .eq("challenge_id", challenge_id)
        .eq("movement", movement)
        .eq("status", "confirmed")
        .maybe_single()
        .execute()
    )
    return result.data


def _update_challenge(challenge_id: str, update: dict) -> None:
    sb = _get_supabase()
    sb.schema("gaming").table("challenges").update(update).eq("id", challenge_id).execute()


async def approve_and_create_match(
    user_id: str,
    challenge_id: str,
    stake_usd: Decimal,
) -> dict:
    """
    Approve USDC for the escrow contract and call ClawEscrow.createMatch.

    This is the challenger (player1) action. It must run before the opponent
    can join. The actual transaction is signed by the user's Circle wallet.
    """
    _require_env()
    await ensure_user_wallet(user_id)

    challenge = _load_challenge(challenge_id)
    if challenge["creator_id"] != user_id:
        raise EscrowError("Only the challenge creator can lock the creator stake")
    if challenge.get("creator_lock_tx_id"):
        raise EscrowError("Creator stake already locked")

    wallet_id = _load_profile_wallet_id(user_id)
    stake_wei = _usdc_to_wei(stake_usd)
    match_id = _challenge_id_to_bytes32(challenge_id)

    idempotency_key = f"approve-create-{challenge_id}"
    existing = _find_existing_audit(challenge_id, "lock_in")
    if existing:
        return {
            "success": True,
            "create_tx_id": existing["circle_tx_id"],
            "tx_hash": existing.get("tx_hash", ""),
            "match_id": match_id,
            "stake_wei": stake_wei,
        }

    # 1. Approve the escrow contract to pull the stake.
    logger.info("[Escrow] Approving USDC for user %s match %s", user_id, challenge_id)
    approve_result = _circle().approve_usdc_transfer(
        wallet_id=wallet_id,
        amount_usdc=float(stake_usd),
        spender_address=ESCROW_ADDRESS,
    )
    if not approve_result.get("success"):
        raise EscrowError(f"USDC approve failed: {approve_result.get('error')}")

    # 2. Call createMatch(matchId, stake).
    logger.info("[Escrow] Creating match %s for user %s", challenge_id, user_id)
    create_result = _circle().execute_contract_function(
        wallet_id=wallet_id,
        contract_address=ESCROW_ADDRESS,
        function_signature="createMatch(bytes32,uint256)",
        args=[match_id, str(stake_wei)],
    )
    if not create_result.get("success"):
        raise EscrowError(f"createMatch failed: {create_result.get('error')}")

    _record_audit(
        challenge_id=challenge_id,
        profile_id=user_id,
        movement="lock_in",
        amount=stake_usd,
        idempotency_key=idempotency_key,
        circle_tx_id=create_result.get("transaction_id"),
        tx_hash=create_result.get("tx_hash"),
        status="pending",
        metadata={"side": "creator", "match_id": match_id},
    )
    _update_challenge(
        challenge_id,
        {
            "status": "creator_locked",
            "creator_lock_tx_id": create_result.get("transaction_id"),
            "creator_lock_tx_hash": create_result.get("tx_hash"),
        },
    )

    return {
        "success": True,
        "create_tx_id": create_result.get("transaction_id"),
        "tx_hash": create_result.get("tx_hash"),
        "match_id": match_id,
        "stake_wei": stake_wei,
    }


async def approve_and_join_match(
    user_id: str,
    challenge_id: str,
    stake_usd: Decimal,
) -> dict:
    """
    Approve USDC for the escrow contract and call ClawEscrow.joinMatch.

    This is the opponent (player2) action. The match must already be created
    on-chain by the challenger.
    """
    _require_env()
    await ensure_user_wallet(user_id)

    challenge = _load_challenge(challenge_id)
    if challenge.get("opponent_id") and challenge["opponent_id"] != user_id:
        raise EscrowError("Another user is already the opponent for this challenge")
    if challenge["status"] not in ("accepted", "creator_locked"):
        raise EscrowError(f"Challenge status {challenge['status']} does not allow joining")
    if challenge.get("opponent_lock_tx_id"):
        raise EscrowError("Opponent stake already locked")

    wallet_id = _load_profile_wallet_id(user_id)
    stake_wei = _usdc_to_wei(stake_usd)
    match_id = _challenge_id_to_bytes32(challenge_id)

    idempotency_key = f"approve-join-{challenge_id}"
    existing = _find_existing_audit(challenge_id, "lock_in")
    if existing and challenge.get("creator_lock_tx_id"):
        return {
            "success": True,
            "join_tx_id": existing["circle_tx_id"],
            "tx_hash": existing.get("tx_hash", ""),
            "match_id": match_id,
            "stake_wei": stake_wei,
        }

    # 1. Approve the escrow contract to pull the stake.
    logger.info("[Escrow] Approving USDC for user %s match %s", user_id, challenge_id)
    approve_result = _circle().approve_usdc_transfer(
        wallet_id=wallet_id,
        amount_usdc=float(stake_usd),
        spender_address=ESCROW_ADDRESS,
    )
    if not approve_result.get("success"):
        raise EscrowError(f"USDC approve failed: {approve_result.get('error')}")

    # 2. Call joinMatch(matchId).
    logger.info("[Escrow] Joining match %s for user %s", challenge_id, user_id)
    join_result = _circle().execute_contract_function(
        wallet_id=wallet_id,
        contract_address=ESCROW_ADDRESS,
        function_signature="joinMatch(bytes32)",
        args=[match_id],
    )
    if not join_result.get("success"):
        raise EscrowError(f"joinMatch failed: {join_result.get('error')}")

    _record_audit(
        challenge_id=challenge_id,
        profile_id=user_id,
        movement="lock_in",
        amount=stake_usd,
        idempotency_key=idempotency_key,
        circle_tx_id=join_result.get("transaction_id"),
        tx_hash=join_result.get("tx_hash"),
        status="pending",
        metadata={"side": "opponent", "match_id": match_id},
    )
    _update_challenge(
        challenge_id,
        {
            "status": "locked",
            "opponent_id": user_id,
            "opponent_lock_tx_id": join_result.get("transaction_id"),
            "opponent_lock_tx_hash": join_result.get("tx_hash"),
        },
    )

    return {
        "success": True,
        "join_tx_id": join_result.get("transaction_id"),
        "tx_hash": join_result.get("tx_hash"),
        "match_id": match_id,
        "stake_wei": stake_wei,
    }


async def resolve_match(
    challenge_id: str,
    winner_address: str,
) -> dict:
    """
    Resolve a locked match and pay the winner (minus platform fee).

    This transaction is signed by the resolver/admin wallet via the shared
    blockchain layer, not a Circle user wallet.
    """
    _require_env()
    challenge = _load_challenge(challenge_id)
    if challenge.get("status") not in ("submitted", "disputed"):
        raise EscrowError(f"Challenge status {challenge.get('status')} cannot be resolved")

    existing = _find_existing_audit(challenge_id, "payout")
    if existing:
        logger.info("[Escrow] Resolve already executed for %s; idempotency guard", challenge_id)
        return {
            "success": True,
            "tx_hash": existing.get("tx_hash", ""),
            "block": None,
            "gas_used": None,
            "explorer_url": None,
        }

    try:
        from backend.blockchain_layer import get_blockchain_layer

        bl = get_blockchain_layer()
        result = await bl.resolve_match_onchain(challenge_id, winner_address)

        winner_id = challenge.get("winner_id")
        amount = Decimal(str(challenge["amount_usdc"]))
        payout = amount * Decimal("2") * Decimal("0.93")  # 7% fee
        fee = amount * Decimal("2") * Decimal("0.07")

        _record_audit(
            challenge_id=challenge_id,
            profile_id=winner_id,
            movement="payout",
            amount=payout,
            idempotency_key=f"resolve-{challenge_id}",
            circle_tx_id=result.get("tx_hash"),
            tx_hash=result.get("tx_hash"),
            status="pending",
            metadata={"fee_usdc": float(fee), "total_pot_usdc": float(amount * 2)},
        )
        _record_audit(
            challenge_id=challenge_id,
            profile_id=None,
            movement="fee",
            amount=fee,
            idempotency_key=f"fee-{challenge_id}",
            status="pending",
            metadata={"winner_id": winner_id},
        )
        _update_challenge(
            challenge_id,
            {"status": "resolved", "resolved_tx_hash": result.get("tx_hash")},
        )

        return {
            "success": True,
            "tx_hash": result.get("tx_hash"),
            "block": result.get("block"),
            "gas_used": result.get("gas_used"),
            "explorer_url": result.get("explorer_url"),
        }
    except Exception as exc:
        logger.exception("[Escrow] resolve_match failed for %s", challenge_id)
        raise EscrowError(f"resolve_match failed: {exc}") from exc


async def cancel_match(challenge_id: str) -> dict:
    """Cancel a match and refund both players. Admin/resolver only."""
    _require_env()
    challenge = _load_challenge(challenge_id)
    if challenge.get("status") in ("resolved", "cancelled", "expired"):
        raise EscrowError(f"Challenge status {challenge.get('status')} cannot be cancelled")

    existing = _find_existing_audit(challenge_id, "refund")
    if existing:
        return {"success": True, "tx_hash": existing.get("tx_hash", "")}

    try:
        from backend.blockchain_layer import get_blockchain_layer

        bl = get_blockchain_layer()
        result = await bl.cancel_match_onchain(challenge_id)

        amount = Decimal(str(challenge["amount_usdc"]))
        for side, profile_id in (
            ("creator", challenge["creator_id"]),
            ("opponent", challenge.get("opponent_id")),
        ):
            if not profile_id:
                continue
            _record_audit(
                challenge_id=challenge_id,
                profile_id=profile_id,
                movement="refund",
                amount=amount,
                idempotency_key=f"cancel-{side}-{challenge_id}",
                circle_tx_id=result.get("tx_hash"),
                tx_hash=result.get("tx_hash"),
                status="pending",
                metadata={"side": side},
            )
        _update_challenge(challenge_id, {"status": "cancelled"})

        return {
            "success": True,
            "tx_hash": result.get("tx_hash"),
            "block": result.get("block"),
            "gas_used": result.get("gas_used"),
            "explorer_url": result.get("explorer_url"),
        }
    except Exception as exc:
        logger.exception("[Escrow] cancel_match failed for %s", challenge_id)
        raise EscrowError(f"cancel_match failed: {exc}") from exc


async def flag_dispute(challenge_id: str) -> dict:
    """Flag a match as disputed on-chain. Admin/resolver only."""
    _require_env()
    challenge = _load_challenge(challenge_id)
    if challenge.get("status") not in ("submitted", "locked", "creator_locked"):
        raise EscrowError(f"Challenge status {challenge.get('status')} cannot be disputed")

    try:
        from backend.blockchain_layer import get_blockchain_layer

        bl = get_blockchain_layer()
        result = await bl.flag_dispute_onchain(challenge_id)
        _update_challenge(
            challenge_id,
            {
                "status": "disputed",
                "dispute_raised_at": "now()",
            },
        )
        return {
            "success": True,
            "tx_hash": result.get("tx_hash"),
            "block": result.get("block"),
            "gas_used": result.get("gas_used"),
            "explorer_url": result.get("explorer_url"),
        }
    except Exception as exc:
        logger.exception("[Escrow] flag_dispute failed for %s", challenge_id)
        raise EscrowError(f"flag_dispute failed: {exc}") from exc


def get_onchain_status(challenge_id: str) -> dict:
    """Read the on-chain match state from ClawEscrow.sol."""
    _require_env()
    try:
        from backend.blockchain_layer import get_blockchain_layer

        bl = get_blockchain_layer()
        return bl.get_match_status(challenge_id)
    except Exception as exc:
        logger.exception("[Escrow] get_onchain_status failed for %s", challenge_id)
        raise EscrowError(f"get_onchain_status failed: {exc}") from exc
