"""
Non-custodial on-chain escrow for ClawStation (multi-chain).

Wraps Circle developer-controlled wallets and ClawEscrow.sol so Telegram
players can lock stakes, settle matches, and receive payouts without
sideQuest taking custody of funds.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from decimal import Decimal
from typing import Optional

from backend.circle_wallet_service import CircleWalletService
from backend.supabase_client import get_supabase
from gaming.src.backend.services.chains import (
    default_chain_id,
    get_circle_blockchain,
    get_circle_usdc_token_id,
    get_escrow_address,
    get_explorer_tx,
    get_rpc_url,
    get_usdc_address,
    normalize_chain_id,
)
from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge
from gaming.src.backend.services.clawstation_circle import ensure_user_wallet
from gaming.src.backend.services.gas_tank import ensure_native_gas

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6


class EscrowError(Exception):
    """Raised when a ClawEscrow operation fails."""


class EscrowNotConfiguredError(EscrowError):
    """Raised when the escrow contract address or keys are missing."""


def _challenge_chain(challenge: dict) -> str:
    return normalize_chain_id(challenge.get("settlement_chain") or default_chain_id())


def _require_escrow(chain_id: str) -> str:
    try:
        return get_escrow_address(chain_id)
    except ValueError as exc:
        raise EscrowNotConfiguredError(str(exc)) from exc


def _challenge_id_to_bytes32(challenge_id: str) -> str:
    return "0x" + hashlib.sha256(challenge_id.encode()).hexdigest()


def _usdc_to_wei(amount_usd: Decimal) -> int:
    return int(amount_usd * Decimal(10**USDC_DECIMALS))


def _circle(chain_id: str) -> CircleWalletService:
    """Circle client bound to the settlement chain's USDC / RPC / token id."""
    return CircleWalletService(
        blockchain=get_circle_blockchain(chain_id),
        usdc_address=get_usdc_address(chain_id),
        usdc_token_id=get_circle_usdc_token_id(chain_id),
        rpc_url=get_rpc_url(chain_id),
    )


def _get_supabase():
    return get_supabase()


def _load_profile_wallet(profile_id: str, chain_id: str = "base") -> tuple[str, str]:
    """Return (wallet_id, address) for a profile on a given chain.

    Never fall back to the Base ``circle_wallet_id`` for arc/avalanche —
    Circle EOAs are one-blockchain-per-wallet; wrong id runs on BASE-SEPOLIA.
    ``gaming_deposit_address`` may be another chain's address; only use it
    as a hint for base.
    """
    sb = _get_supabase()
    try:
        result = (
            sb.table("profiles")
            .select("circle_wallet_id, gaming_deposit_address, gaming_circle_wallets")
            .eq("id", profile_id)
            .limit(1)
            .execute()
        )
    except Exception:
        result = (
            sb.table("profiles")
            .select("circle_wallet_id, gaming_deposit_address")
            .eq("id", profile_id)
            .limit(1)
            .execute()
        )
    data = result.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        raise EscrowError(f"User {profile_id} has no Circle wallet — run /start first")
    wallets = data.get("gaming_circle_wallets") or {}
    # Per-chain only — Base may use legacy circle_wallet_id as last resort
    wallet_id = wallets.get(chain_id)
    if not wallet_id and chain_id == "base":
        wallet_id = data.get("circle_wallet_id")
    if not wallet_id:
        raise EscrowError(
            f"User {profile_id} has no Circle wallet for chain={chain_id} — "
            "open Wallet / /start so we provision that chain"
        )
    address = ""
    if chain_id == "base":
        address = data.get("gaming_deposit_address") or ""
    return wallet_id, address


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
    return normalize_challenge(result.data)


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


def _find_existing_audit(
    challenge_id: str,
    movement: str,
    profile_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Optional[dict]:
    sb = _get_supabase()
    q = (
        sb.schema("gaming")
        .table("escrow_audit")
        .select("*")
        .eq("challenge_id", challenge_id)
        .eq("movement", movement)
    )
    if profile_id:
        q = q.eq("profile_id", profile_id)
    if idempotency_key:
        q = q.eq("idempotency_key", idempotency_key)
    result = q.in_("status", ["pending", "confirmed"]).limit(1).execute()
    rows = result.data or []
    return rows[0] if rows else None


def _update_challenge(challenge_id: str, update: dict) -> None:
    sb = _get_supabase()
    sb.schema("gaming").table("challenges").update(denormalize_challenge(update)).eq(
        "id", challenge_id
    ).execute()


async def _prepare_wallet(user_id: str, chain_id: str) -> tuple[str, str]:
    """Ensure Circle wallet + native gas on the settlement chain.

    Always uses ``ensure_user_wallet(chain_id)`` so Arc/Avalanche never
    sign with a Base wallet id (that was the createMatch FAILED bug).
    """
    wallet = await ensure_user_wallet(user_id, chain_id=chain_id)
    wallet_id = wallet["wallet_id"]
    address = wallet.get("address") or ""
    want = get_circle_blockchain(chain_id).upper().replace("_", "-")
    got = (wallet.get("blockchain") or "").upper().replace("_", "-")
    if got and want and got != want and want not in got and got not in want:
        raise EscrowError(
            f"Wallet chain mismatch for {chain_id}: wallet is on {got}, need {want}. "
            "Refusing to lock — open Wallet to re-provision this chain."
        )
    # Sanity: mapped id for this chain must match what ensure returned
    try:
        mapped_id, _ = _load_profile_wallet(user_id, chain_id)
        if mapped_id and mapped_id != wallet_id:
            logger.warning(
                "[Escrow] chain wallet mismatch user=%s chain=%s ensure=%s map=%s — using ensure",
                user_id,
                chain_id,
                wallet_id,
                mapped_id,
            )
    except EscrowError:
        pass
    # Only top up when we have a real checksummable address (skip unit-test stubs).
    if address and address.startswith("0x") and len(address) == 42:
        gas = ensure_native_gas(chain_id, address)
        if not gas.get("ok") and gas.get("action") not in (
            "skipped_usdc_gas_chain",
            "already_funded",
            "bad_address",
        ):
            logger.warning("[Escrow] Gas tank issue for %s on %s: %s", user_id, chain_id, gas)
            if gas.get("action") in ("admin_low", "no_admin_key", "tx_failed"):
                raise EscrowError(
                    f"Not enough gas on {chain_id} for your wallet. "
                    f"Platform gas tank: {gas.get('error') or gas.get('action')}"
                )
    return wallet_id, address


async def approve_and_create_match(
    user_id: str,
    challenge_id: str,
    stake_usd: Decimal,
) -> dict:
    """Challenger: approve USDC + createMatch on the challenge settlement chain."""
    import time as _time

    t0 = _time.monotonic()
    challenge = _load_challenge(challenge_id)
    chain_id = _challenge_chain(challenge)
    escrow_address = _require_escrow(chain_id)

    if challenge["creator_id"] != user_id:
        raise EscrowError("Only the challenge creator can lock the creator stake")
    if challenge.get("creator_lock_tx_id"):
        raise EscrowError("Creator stake already locked")

    wallet_id, _ = await _prepare_wallet(user_id, chain_id)
    stake_wei = _usdc_to_wei(stake_usd)
    match_id = _challenge_id_to_bytes32(challenge_id)

    idempotency_key = f"approve-create-{challenge_id}"
    existing = _find_existing_audit(
        challenge_id, "lock_in", profile_id=user_id, idempotency_key=idempotency_key
    )
    if existing:
        return {
            "success": True,
            "create_tx_id": existing["circle_tx_id"],
            "tx_hash": existing.get("tx_hash", ""),
            "match_id": match_id,
            "stake_wei": stake_wei,
            "chain_id": chain_id,
            "explorer_url": get_explorer_tx(chain_id, existing.get("tx_hash") or ""),
        }

    circle = _circle(chain_id)

    # All Circle HTTP + wait polling runs off the event loop so Telegram stays responsive
    logger.info("[Escrow] Approving USDC user=%s chain=%s match=%s", user_id, chain_id, challenge_id)
    approve_result = await asyncio.to_thread(
        circle.approve_usdc_transfer,
        wallet_id,
        float(stake_usd),
        escrow_address,
    )
    if not approve_result.get("success"):
        raise EscrowError(f"USDC approve failed: {approve_result.get('error')}")

    approve_tx_id = approve_result.get("transaction_id")
    approve_waited = 0
    if approve_tx_id:
        approve_wait = await circle.wait_for_transaction_async(
            approve_tx_id, max_wait_seconds=90
        )
        if not approve_wait.get("success"):
            raise EscrowError(f"USDC approve not confirmed: {approve_wait.get('error')}")
        approve_waited = int(approve_wait.get("time_waited") or 0)

    logger.info("[Escrow] createMatch user=%s chain=%s match=%s", user_id, chain_id, challenge_id)
    create_result = await asyncio.to_thread(
        circle.execute_contract_function,
        wallet_id,
        escrow_address,
        "createMatch(bytes32,uint256)",
        [match_id, str(stake_wei)],
    )
    if not create_result.get("success"):
        raise EscrowError(f"createMatch failed: {create_result.get('error')}")

    create_tx_id = create_result.get("transaction_id")
    tx_hash = create_result.get("tx_hash") or ""
    create_waited = 0
    if create_tx_id:
        create_wait = await circle.wait_for_transaction_async(
            create_tx_id, max_wait_seconds=120
        )
        if not create_wait.get("success"):
            raise EscrowError(f"createMatch not confirmed: {create_wait.get('error')}")
        tx_hash = create_wait.get("tx_hash") or tx_hash
        create_waited = int(create_wait.get("time_waited") or 0)

    elapsed = round(_time.monotonic() - t0, 1)
    logger.info(
        "[Escrow] createMatch done user=%s chain=%s elapsed=%ss approve_wait=%ss create_wait=%ss",
        user_id,
        chain_id,
        elapsed,
        approve_waited,
        create_waited,
    )

    _record_audit(
        challenge_id=challenge_id,
        profile_id=user_id,
        movement="lock_in",
        amount=stake_usd,
        idempotency_key=idempotency_key,
        circle_tx_id=create_tx_id,
        tx_hash=tx_hash,
        status="confirmed" if tx_hash else "pending",
        metadata={
            "side": "creator",
            "match_id": match_id,
            "chain": chain_id,
            "elapsed_sec": elapsed,
            "approve_wait_sec": approve_waited,
            "create_wait_sec": create_waited,
        },
    )
    _update_challenge(
        challenge_id,
        {
            "status": "creator_locked",
            "creator_lock_tx_id": create_tx_id,
            "creator_lock_tx_hash": tx_hash,
        },
    )

    return {
        "success": True,
        "create_tx_id": create_tx_id,
        "tx_hash": tx_hash,
        "match_id": match_id,
        "stake_wei": stake_wei,
        "chain_id": chain_id,
        "explorer_url": get_explorer_tx(chain_id, tx_hash),
    }


async def approve_and_join_match(
    user_id: str,
    challenge_id: str,
    stake_usd: Decimal,
) -> dict:
    """Opponent: approve USDC + joinMatch on the challenge settlement chain."""
    import time as _time

    t0 = _time.monotonic()
    challenge = _load_challenge(challenge_id)
    chain_id = _challenge_chain(challenge)
    escrow_address = _require_escrow(chain_id)

    if challenge.get("opponent_id") and challenge["opponent_id"] != user_id:
        raise EscrowError("Another user is already the opponent for this challenge")
    if challenge["status"] not in ("accepted", "creator_locked"):
        raise EscrowError(f"Challenge status {challenge['status']} does not allow joining")
    if challenge.get("opponent_lock_tx_id"):
        raise EscrowError("Opponent stake already locked")

    if not challenge.get("creator_lock_tx_id") and challenge.get("status") not in (
        "creator_locked",
        "locked",
    ):
        raise EscrowError("Creator must lock stake before opponent can join")

    wallet_id, _ = await _prepare_wallet(user_id, chain_id)
    stake_wei = _usdc_to_wei(stake_usd)
    match_id = _challenge_id_to_bytes32(challenge_id)

    idempotency_key = f"approve-join-{challenge_id}"
    existing = _find_existing_audit(
        challenge_id, "lock_in", profile_id=user_id, idempotency_key=idempotency_key
    )
    if existing:
        return {
            "success": True,
            "join_tx_id": existing["circle_tx_id"],
            "tx_hash": existing.get("tx_hash", ""),
            "match_id": match_id,
            "stake_wei": stake_wei,
            "chain_id": chain_id,
            "explorer_url": get_explorer_tx(chain_id, existing.get("tx_hash") or ""),
        }

    circle = _circle(chain_id)

    logger.info("[Escrow] Approving USDC opponent=%s chain=%s", user_id, chain_id)
    approve_result = await asyncio.to_thread(
        circle.approve_usdc_transfer,
        wallet_id,
        float(stake_usd),
        escrow_address,
    )
    if not approve_result.get("success"):
        raise EscrowError(f"USDC approve failed: {approve_result.get('error')}")

    approve_tx_id = approve_result.get("transaction_id")
    approve_waited = 0
    if approve_tx_id:
        approve_wait = await circle.wait_for_transaction_async(
            approve_tx_id, max_wait_seconds=90
        )
        if not approve_wait.get("success"):
            raise EscrowError(f"USDC approve not confirmed: {approve_wait.get('error')}")
        approve_waited = int(approve_wait.get("time_waited") or 0)

    logger.info("[Escrow] joinMatch user=%s chain=%s", user_id, chain_id)
    join_result = await asyncio.to_thread(
        circle.execute_contract_function,
        wallet_id,
        escrow_address,
        "joinMatch(bytes32)",
        [match_id],
    )
    if not join_result.get("success"):
        raise EscrowError(f"joinMatch failed: {join_result.get('error')}")

    join_tx_id = join_result.get("transaction_id")
    tx_hash = join_result.get("tx_hash") or ""
    join_waited = 0
    if join_tx_id:
        join_wait = await circle.wait_for_transaction_async(
            join_tx_id, max_wait_seconds=120
        )
        if not join_wait.get("success"):
            raise EscrowError(f"joinMatch not confirmed: {join_wait.get('error')}")
        tx_hash = join_wait.get("tx_hash") or tx_hash
        join_waited = int(join_wait.get("time_waited") or 0)

    elapsed = round(_time.monotonic() - t0, 1)
    logger.info(
        "[Escrow] joinMatch done user=%s chain=%s elapsed=%ss approve_wait=%ss join_wait=%ss",
        user_id,
        chain_id,
        elapsed,
        approve_waited,
        join_waited,
    )

    _record_audit(
        challenge_id=challenge_id,
        profile_id=user_id,
        movement="lock_in",
        amount=stake_usd,
        idempotency_key=idempotency_key,
        circle_tx_id=join_tx_id,
        tx_hash=tx_hash,
        status="confirmed" if tx_hash else "pending",
        metadata={
            "side": "opponent",
            "match_id": match_id,
            "chain": chain_id,
            "elapsed_sec": elapsed,
            "approve_wait_sec": approve_waited,
            "join_wait_sec": join_waited,
        },
    )
    _update_challenge(
        challenge_id,
        {
            "status": "locked",
            "opponent_id": user_id,
            "opponent_lock_tx_id": join_tx_id,
            "opponent_lock_tx_hash": tx_hash,
        },
    )

    return {
        "success": True,
        "join_tx_id": join_tx_id,
        "tx_hash": tx_hash,
        "match_id": match_id,
        "stake_wei": stake_wei,
        "chain_id": chain_id,
        "explorer_url": get_explorer_tx(chain_id, tx_hash),
    }


async def resolve_match(challenge_id: str, winner_address: str) -> dict:
    """Resolver wallet pays the winner (minus 7% fee) on the challenge chain."""
    challenge = _load_challenge(challenge_id)
    chain_id = _challenge_chain(challenge)
    _require_escrow(chain_id)

    if challenge.get("status") not in ("submitted", "disputed", "locked"):
        raise EscrowError(f"Challenge status {challenge.get('status')} cannot be resolved")

    existing = _find_existing_audit(challenge_id, "payout")
    if existing:
        return {
            "success": True,
            "tx_hash": existing.get("tx_hash", ""),
            "block": None,
            "gas_used": None,
            "explorer_url": get_explorer_tx(chain_id, existing.get("tx_hash") or ""),
            "chain_id": chain_id,
        }

    try:
        from backend.blockchain_layer import get_blockchain_layer_for_chain

        bl = get_blockchain_layer_for_chain(chain_id)
        result = await bl.resolve_match_onchain(challenge_id, winner_address)

        winner_id = challenge.get("winner_id")
        amount = Decimal(str(challenge["amount_usdc"]))
        payout = amount * Decimal("2") * Decimal("0.93")
        fee = amount * Decimal("2") * Decimal("0.07")

        gas_used = result.get("gas_used")
        _record_audit(
            challenge_id=challenge_id,
            profile_id=winner_id,
            movement="payout",
            amount=payout,
            idempotency_key=f"resolve-{challenge_id}",
            circle_tx_id=result.get("tx_hash"),
            tx_hash=result.get("tx_hash"),
            status="confirmed",
            metadata={
                "fee_usdc": float(fee),
                "total_pot_usdc": float(amount * 2),
                "chain": chain_id,
                "gas_used": gas_used,
                "block": result.get("block"),
            },
        )
        _record_audit(
            challenge_id=challenge_id,
            profile_id=None,
            movement="fee",
            amount=fee,
            idempotency_key=f"fee-{challenge_id}",
            status="confirmed",
            metadata={
                "winner_id": winner_id,
                "chain": chain_id,
                "gas_used": gas_used,
            },
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
            "explorer_url": result.get("explorer_url") or get_explorer_tx(chain_id, result.get("tx_hash") or ""),
            "chain_id": chain_id,
        }
    except Exception as exc:
        logger.exception("[Escrow] resolve_match failed for %s", challenge_id)
        raise EscrowError(f"resolve_match failed: {exc}") from exc


async def cancel_match(challenge_id: str) -> dict:
    """Cancel a match and refund both players (resolver)."""
    challenge = _load_challenge(challenge_id)
    chain_id = _challenge_chain(challenge)
    _require_escrow(chain_id)

    if challenge.get("status") in ("resolved", "cancelled", "expired"):
        raise EscrowError(f"Challenge status {challenge.get('status')} cannot be cancelled")

    existing = _find_existing_audit(challenge_id, "refund")
    if existing:
        return {"success": True, "tx_hash": existing.get("tx_hash", ""), "chain_id": chain_id}

    try:
        from backend.blockchain_layer import get_blockchain_layer_for_chain

        bl = get_blockchain_layer_for_chain(chain_id)
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
                status="confirmed",
                metadata={
                    "side": side,
                    "chain": chain_id,
                    "gas_used": result.get("gas_used"),
                    "block": result.get("block"),
                },
            )
        _update_challenge(challenge_id, {"status": "cancelled"})

        return {
            "success": True,
            "tx_hash": result.get("tx_hash"),
            "block": result.get("block"),
            "gas_used": result.get("gas_used"),
            "explorer_url": result.get("explorer_url"),
            "chain_id": chain_id,
        }
    except Exception as exc:
        logger.exception("[Escrow] cancel_match failed for %s", challenge_id)
        raise EscrowError(f"cancel_match failed: {exc}") from exc


async def flag_dispute(challenge_id: str) -> dict:
    """Flag a match as disputed on-chain."""
    challenge = _load_challenge(challenge_id)
    chain_id = _challenge_chain(challenge)
    _require_escrow(chain_id)

    if challenge.get("status") not in ("submitted", "locked", "creator_locked", "playing"):
        raise EscrowError(f"Challenge status {challenge.get('status')} cannot be disputed")

    try:
        from backend.blockchain_layer import get_blockchain_layer_for_chain

        bl = get_blockchain_layer_for_chain(chain_id)
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
            "chain_id": chain_id,
        }
    except Exception as exc:
        logger.exception("[Escrow] flag_dispute failed for %s", challenge_id)
        raise EscrowError(f"flag_dispute failed: {exc}") from exc


def get_onchain_status(challenge_id: str) -> dict:
    challenge = _load_challenge(challenge_id)
    chain_id = _challenge_chain(challenge)
    _require_escrow(chain_id)
    try:
        from backend.blockchain_layer import get_blockchain_layer_for_chain

        bl = get_blockchain_layer_for_chain(chain_id)
        status = bl.get_match_status(challenge_id)
        status["chain_id"] = chain_id
        return status
    except Exception as exc:
        logger.exception("[Escrow] get_onchain_status failed for %s", challenge_id)
        raise EscrowError(f"get_onchain_status failed: {exc}") from exc
