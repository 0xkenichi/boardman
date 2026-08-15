"""
gaming/src/backend/api/webhooks.py

Inbound webhook handlers for external providers.

``POST /webhooks/circle`` receives Circle Programmable Wallet transaction
events. It verifies the webhook signature, parses inbound USDC transfers to
ClawStation deposit addresses, credits the user's internal balance exactly
once, and records the credit in ``gaming.wallet_credit_audit``.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from decimal import Decimal
from typing import Optional

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

CIRCLE_WEBHOOK_SECRET_ENV = "CIRCLE_WEBHOOK_SECRET"
DATABASE_URL_ENV = "DATABASE_URL"


class WebhookError(Exception):
    """Raised when a webhook cannot be processed."""

    def __init__(self, message: str, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


def _constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_circle_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Verify a Circle webhook using HMAC-SHA256.

    Circle sends the signature in the ``x-circle-signature`` header, typically
    prefixed with ``v1=``. The secret is read from ``CIRCLE_WEBHOOK_SECRET``.

    A missing secret **fails closed** — the webhook credits user balances, so
    an unverified request must never be accepted. Local dev can opt out
    explicitly with ``CIRCLE_WEBHOOK_SKIP_VERIFY=1``.
    """
    secret = os.getenv(CIRCLE_WEBHOOK_SECRET_ENV)
    if not secret:
        if os.getenv("CIRCLE_WEBHOOK_SKIP_VERIFY") == "1":
            logger.warning(
                "[%s] not set; CIRCLE_WEBHOOK_SKIP_VERIFY=1 — skipping verification (dev only)",
                CIRCLE_WEBHOOK_SECRET_ENV,
            )
            return True
        logger.error(
            "[%s] not set; rejecting unverified Circle webhook (set the secret or "
            "CIRCLE_WEBHOOK_SKIP_VERIFY=1 for local dev)",
            CIRCLE_WEBHOOK_SECRET_ENV,
        )
        return False

    if not signature_header:
        return False

    expected = "v1=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        "sha256",
    ).hexdigest()

    # Allow signatures with or without the v1= prefix.
    return _constant_time_compare(signature_header, expected) or _constant_time_compare(
        signature_header, expected[3:]
    )


def _parse_usdc_transfer(payload: dict) -> Optional[dict]:
    """Extract user_id and amount from a Circle webhook payload.

    Expected shape (simplified):
        {
            "type": "transfer",
            "data": {
                "walletId": "...",
                "transaction": {
                    "txHash": "0x...",
                    "amount": [{"amount": "1000000", "token": {"symbol": "USDC"}}]
                },
                "status": "CONFIRMED"
            }
        }

    Returns:
        ``{"tx_hash": str, "amount_usdc": Decimal, "wallet_address": str}``
        or ``None`` if the event is not a confirmed inbound USDC transfer.
    """
    event_type = payload.get("type", "")
    if event_type not in {"transfer", "transactions.outbound", "transactions.inbound"}:
        return None

    data = payload.get("data", {})
    tx = data.get("transaction", data)
    if not tx:
        return None

    status = (tx.get("status") or data.get("status", "")).upper()
    if status not in {"CONFIRMED", "COMPLETE", "SUCCESS", "SETTLED"}:
        return None

    amounts = tx.get("amount", tx.get("amounts", []))
    if not isinstance(amounts, list):
        amounts = [amounts]

    usdc_amount = None
    for amt in amounts:
        if not isinstance(amt, dict):
            continue
        token = amt.get("token", {})
        symbol = (token.get("symbol") or amt.get("tokenSymbol", "")).upper()
        if symbol == "USDC":
            raw = amt.get("amount", "0")
            try:
                usdc_amount = Decimal(str(raw)) / Decimal("1_000_000")
            except Exception:
                logger.warning("[CircleWebhook] Non-numeric USDC amount: %s", raw)
                return None
            break

    if usdc_amount is None or usdc_amount <= 0:
        return None

    tx_hash = tx.get("txHash") or data.get("txHash") or data.get("id")
    if not tx_hash:
        return None

    wallet_address = (
        tx.get("destinationAddress")
        or data.get("destinationAddress")
        or data.get("walletAddress")
        or ""
    )

    return {
        "tx_hash": str(tx_hash),
        "amount_usdc": usdc_amount,
        "wallet_address": wallet_address.lower() if wallet_address else "",
    }


async def _find_user_by_deposit_address(address: str) -> Optional[str]:
    """Return the profile id that owns ``address`` (case-insensitive)."""
    from backend.supabase_client import get_supabase

    if not address:
        return None
    sb = get_supabase()
    result = (
        sb.table("profiles")
        .select("id")
        .ilike("gaming_deposit_address", address)
        .maybe_single()
        .execute()
    )
    data = getattr(result, "data", None)
    return data["id"] if data else None


async def _credit_via_asyncpg(user_id: str, amount_usdc: Decimal, tx_hash: str) -> bool:
    """Credit the user inside a Postgres transaction with ``FOR UPDATE``.

    Returns:
        ``True`` if the credit was applied, ``False`` if ``tx_hash`` was already
        processed (duplicate webhook).

    Raises:
        WebhookError: on DB connection or unexpected errors.
    """
    dsn = os.getenv(DATABASE_URL_ENV)
    if not dsn:
        raise WebhookError(
            f"{DATABASE_URL_ENV} not configured; cannot run transactional credit",
            status_code=503,
        )

    conn: Optional[asyncpg.Connection] = None
    try:
        conn = await asyncpg.connect(dsn)
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id FROM public.profiles WHERE id = $1 FOR UPDATE",
                user_id,
            )
            if row is None:
                raise WebhookError(f"User {user_id} not found", status_code=404)

            existing = await conn.fetchval(
                "SELECT id FROM gaming.wallet_credit_audit WHERE tx_hash = $1",
                tx_hash,
            )
            if existing:
                logger.info("[CircleWebhook] Duplicate tx_hash %s ignored", tx_hash)
                return False

            await conn.execute(
                "INSERT INTO gaming.wallet_credit_audit (user_id, tx_hash, amount_usdc, status) "
                "VALUES ($1, $2, $3, 'credited')",
                user_id,
                tx_hash,
                amount_usdc,
            )
            await conn.execute(
                "SELECT credit_wallet($1::uuid, $2::numeric)",
                user_id,
                amount_usdc,
            )
        return True
    except WebhookError:
        raise
    except Exception as exc:
        logger.exception("[CircleWebhook] Transactional credit failed")
        raise WebhookError(f"Credit transaction failed: {exc}", status_code=500) from exc
    finally:
        if conn is not None:
            await conn.close()


async def _credit_via_supabase(user_id: str, amount_usdc: Decimal, tx_hash: str) -> bool:
    """Best-effort credit path when direct Postgres is unavailable.

    Calls the existing ``credit_wallet`` Postgres RPC and inserts the audit
    row. Idempotency relies on the ``UNIQUE`` constraint on ``tx_hash``. The
    insert is attempted first; if it conflicts, the webhook is a duplicate no-op.
    """
    from backend.supabase_client import get_supabase

    sb = get_supabase()
    try:
        existing = (
            sb.table("wallet_credit_audit")
            .select("id")
            .eq("tx_hash", tx_hash)
            .maybe_single()
            .execute()
        )
        if existing.data:
            logger.info("[CircleWebhook] Duplicate tx_hash %s ignored", tx_hash)
            return False

        sb.table("wallet_credit_audit").insert(
            {
                "user_id": user_id,
                "tx_hash": tx_hash,
                "amount_usdc": float(amount_usdc),
                "status": "credited",
            }
        ).execute()

        sb.rpc("credit_wallet", {"p_user_id": user_id, "p_amount": float(amount_usdc)}).execute()
        logger.info(
            "[CircleWebhook] Credited %s USDC to user %s via RPC (tx=%s)",
            amount_usdc,
            user_id,
            tx_hash,
        )
        return True
    except Exception as exc:
        logger.exception("[CircleWebhook] Supabase credit path failed")
        raise WebhookError(f"Credit failed: {exc}", status_code=500) from exc


async def _apply_credit(user_id: str, amount_usdc: Decimal, tx_hash: str) -> bool:
    """Credit the user idempotently, preferring the transactional path."""
    if os.getenv(DATABASE_URL_ENV):
        return await _credit_via_asyncpg(user_id, amount_usdc, tx_hash)
    return await _credit_via_supabase(user_id, amount_usdc, tx_hash)


@router.post("/webhooks/circle")
async def circle_webhook(
    request: Request,
    x_circle_signature: Optional[str] = Header(default=None),
):
    """Handle Circle Programmable Wallet webhooks for inbound USDC deposits."""
    raw_body = await request.body()

    if not verify_circle_signature(raw_body, x_circle_signature):
        raise HTTPException(status_code=401, detail="Invalid Circle webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    transfer = _parse_usdc_transfer(payload)
    if not transfer:
        logger.info("[CircleWebhook] Ignoring non-credit event")
        return {"status": "ignored"}

    user_id = await _find_user_by_deposit_address(transfer["wallet_address"])
    if not user_id:
        logger.warning(
            "[CircleWebhook] No user for deposit address %s",
            transfer["wallet_address"],
        )
        return {"status": "unattributed"}

    credited = await _apply_credit(user_id, transfer["amount_usdc"], transfer["tx_hash"])
    if credited:
        # Telegram deposit confirmation (also logs if watcher already did)
        try:
            from gaming.src.backend.services.clawstation_circle import get_preferred_chain, get_usdc_balance
            from gaming.src.backend.services.wallet_activity import notify_deposit, set_snapshot

            chain = await get_preferred_chain(user_id)
            try:
                new_bal = await get_usdc_balance(user_id, chain_id=chain)
            except Exception:
                new_bal = transfer["amount_usdc"]
            set_snapshot(user_id, chain, new_bal)
            await notify_deposit(
                user_id,
                transfer["amount_usdc"],
                new_bal,
                chain,
                tx_hash=transfer["tx_hash"],
                log=False,  # credit audit already written by _apply_credit
            )
        except Exception:
            logger.exception("[CircleWebhook] deposit notify failed for %s", user_id)

    return {
        "status": "credited" if credited else "already_processed",
        "tx_hash": transfer["tx_hash"],
        "amount_usdc": str(transfer["amount_usdc"]),
    }
