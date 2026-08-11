"""
Tournament pot money — Model A entry pool.

Modes (TOURNAMENT_MONEY_MODE):
  transfer  — Circle USDC player → pot address on join; pot wallet → winners on final
  commit    — require spendable balance, record commitment (ops settles offline if no pot wallet)

Env:
  TOURNAMENTS_MONEY_LIVE=1
  TOURNAMENT_POT_ADDRESS=0x...     # receive entries (default BOARDMAN_OPS_USDC_ADDRESS)
  TOURNAMENT_POT_WALLET_ID=...    # Circle wallet id that holds pot (for refunds + payouts)
  TOURNAMENT_MONEY_MODE=transfer|commit
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TournamentMoneyError(Exception):
    pass


def money_mode() -> str:
    m = (os.getenv("TOURNAMENT_MONEY_MODE") or "transfer").strip().lower()
    if m in ("ledger", "commit", "soft"):
        return "commit"
    return "transfer"


def pot_address() -> str:
    return (
        os.getenv("TOURNAMENT_POT_ADDRESS")
        or os.getenv("BOARDMAN_OPS_USDC_ADDRESS")
        or os.getenv("FEE_RECIPIENT_ADDRESS")
        or ""
    ).strip()


def pot_wallet_id() -> str:
    return (os.getenv("TOURNAMENT_POT_WALLET_ID") or "").strip()


def _circle_for_arc():
    from gaming.src.backend.services.chains import (
        get_circle_blockchain,
        get_circle_usdc_token_id,
        get_rpc_url,
        get_usdc_address,
        default_chain_id,
        normalize_chain_id,
    )
    from backend.circle_wallet_service import CircleWalletService

    cid = normalize_chain_id(os.getenv("BOARDMAN_SETTLEMENT_RAIL") or default_chain_id() or "arc")
    return CircleWalletService(
        blockchain=get_circle_blockchain(cid),
        usdc_address=get_usdc_address(cid),
        usdc_token_id=get_circle_usdc_token_id(cid),
        rpc_url=get_rpc_url(cid),
    ), cid


async def assert_can_pay_entry(profile_id: str, amount: Decimal) -> None:
    """Raise if spendable play balance < entry."""
    if amount <= 0:
        return
    from gaming.src.backend.services.clawstation_circle import get_balance_summary

    s = await get_balance_summary(profile_id, chain_id="arc")
    if s.get("balance_error"):
        raise TournamentMoneyError(
            f"Could not read play balance: {s.get('balance_error')}. Try again."
        )
    spend = Decimal(str(s.get("spendable_usdc") or 0))
    if spend < amount:
        raise TournamentMoneyError(
            f"Need ${amount:.2f} entry. Play balance ${spend:.2f}. "
            f"Tap Get money, then join again."
        )


async def lock_entry(
    profile_id: str,
    amount: Decimal,
    *,
    cup_code: str,
) -> dict[str, Any]:
    """
    Pull entry into pot (or commit).
    Returns {tx_hash, mode, amount_usdc}.
    """
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        return {"tx_hash": "free-entry", "mode": "free", "amount_usdc": 0.0}

    await assert_can_pay_entry(profile_id, amount)
    mode = money_mode()
    dest = pot_address()

    if mode == "commit" or not dest:
        # Soft lock: balance checked; ops / later transfer
        ref = f"commit:{cup_code}:{profile_id[:8]}:{amount}"
        logger.info("[TourMoney] commit entry %s profile=%s $%s", cup_code, profile_id[:8], amount)
        return {
            "tx_hash": ref,
            "mode": "commit",
            "amount_usdc": float(amount),
            "note": "Balance reserved (commit mode) — set TOURNAMENT_POT_ADDRESS + transfer for on-chain",
        }

    from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

    wallet = await ensure_user_wallet(profile_id, chain_id="arc")
    wid = wallet.get("wallet_id")
    if not wid:
        raise TournamentMoneyError("No Circle wallet for entry lock — open Wallet once then retry.")

    circle, _cid = _circle_for_arc()
    result = circle.transfer_usdc(wid, dest, float(amount))
    if not result.get("success"):
        raise TournamentMoneyError(
            f"Entry transfer failed: {result.get('error') or 'unknown'}"
        )
    tx_id = result.get("transaction_id") or ""
    tx_hash = result.get("tx_hash") or tx_id or f"pending:{tx_id}"
    # Best-effort wait
    if tx_id and hasattr(circle, "wait_for_transaction"):
        try:
            st = circle.wait_for_transaction(tx_id, timeout_seconds=90)
            if st.get("success") and st.get("tx_hash"):
                tx_hash = st["tx_hash"]
        except Exception:
            logger.warning("[TourMoney] wait transfer incomplete tx_id=%s", tx_id)

    logger.info(
        "[TourMoney] locked entry cup=%s profile=%s $%s tx=%s",
        cup_code,
        profile_id[:8],
        amount,
        str(tx_hash)[:18],
    )
    return {
        "tx_hash": str(tx_hash),
        "mode": "transfer",
        "amount_usdc": float(amount),
        "to": dest,
    }


async def refund_entry(
    profile_id: str,
    amount: Decimal,
    *,
    cup_code: str,
    entry_tx_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Return entry if player leaves while cup open."""
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        return {"tx_hash": "free-refund", "mode": "free"}

    if (entry_tx_hash or "").startswith("commit:"):
        logger.info("[TourMoney] commit refund cup=%s profile=%s", cup_code, profile_id[:8])
        return {"tx_hash": f"commit-refund:{cup_code}", "mode": "commit"}

    pot_wid = pot_wallet_id()
    if not pot_wid:
        logger.warning(
            "[TourMoney] cannot auto-refund $%s for %s — set TOURNAMENT_POT_WALLET_ID",
            amount,
            profile_id[:8],
        )
        return {
            "tx_hash": None,
            "mode": "manual_refund",
            "note": "Ops must refund manually — pot wallet id not set",
            "amount_usdc": float(amount),
        }

    from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

    wallet = await ensure_user_wallet(profile_id, chain_id="arc")
    addr = wallet.get("address")
    if not addr:
        raise TournamentMoneyError("Player has no address for refund")

    circle, _ = _circle_for_arc()
    result = circle.transfer_usdc(pot_wid, addr, float(amount))
    if not result.get("success"):
        raise TournamentMoneyError(f"Refund failed: {result.get('error')}")
    tx = result.get("tx_hash") or result.get("transaction_id")
    return {"tx_hash": tx, "mode": "transfer", "amount_usdc": float(amount)}


async def pay_payouts(payout_block: dict[str, Any], *, cup_code: str) -> dict[str, Any]:
    """
    Send place prizes from pot wallet. Platform fee stays in pot.
    Mutates / returns places with paid + tx_hash when possible.
    """
    places = list((payout_block or {}).get("places") or [])
    pot_wid = pot_wallet_id()
    mode = money_mode()
    paid_any = False
    results = []

    for p in places:
        pid = p.get("profile_id")
        amt = Decimal(str(p.get("amount_usdc") or 0)).quantize(Decimal("0.01"))
        row = dict(p)
        if amt <= 0 or not pid:
            row["paid"] = True
            row["tx_hash"] = "zero"
            results.append(row)
            continue

        if not pot_wid or mode == "commit":
            row["paid"] = False
            row["tx_hash"] = None
            row["pay_note"] = "manual — set TOURNAMENT_POT_WALLET_ID for auto payout"
            results.append(row)
            continue

        try:
            from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

            wallet = await ensure_user_wallet(pid, chain_id="arc")
            addr = wallet.get("address")
            if not addr:
                row["paid"] = False
                row["pay_note"] = "no winner address"
                results.append(row)
                continue
            circle, _ = _circle_for_arc()
            result = circle.transfer_usdc(pot_wid, addr, float(amt))
            if result.get("success"):
                row["paid"] = True
                row["tx_hash"] = result.get("tx_hash") or result.get("transaction_id")
                paid_any = True
            else:
                row["paid"] = False
                row["pay_note"] = result.get("error")
        except Exception as exc:
            logger.exception("[TourMoney] payout place=%s", p.get("place"))
            row["paid"] = False
            row["pay_note"] = str(exc)
        results.append(row)

    out = dict(payout_block or {})
    out["places"] = results
    out["paid"] = paid_any and all(r.get("paid") for r in results)
    out["money_live"] = True
    logger.info(
        "[TourMoney] payouts cup=%s paid=%s places=%s",
        cup_code,
        out["paid"],
        len(results),
    )
    return out
