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

import asyncio
import inspect
import logging
import os
import uuid
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Namespace for deterministic Circle idempotency keys (uuid5 of the payout
# identity). Circle dedups transfers by key, so a retried place re-uses the
# same key and can never send twice.
_PAYOUT_NS = uuid.UUID("6f1c2a7e-4f0b-5c3e-9a51-b0a2d1e3c4f5")
# A claim older than this (worker died mid-transfer) may be re-driven; the
# deterministic key makes that re-drive safe.
PAYOUT_CLAIM_STALE_MS = 10 * 60 * 1000


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

    from gaming.src.backend.services.realms import assert_practice

    # Cup pots are practice money (realms.py): never a real-money chain.
    cid = assert_practice(
        normalize_chain_id(os.getenv("BOARDMAN_SETTLEMENT_RAIL") or default_chain_id() or "arc"), path="tournament pot"
    )
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
    # Circle's client is synchronous (HTTP + polling): keep it off the loop.
    result = await asyncio.to_thread(circle.transfer_usdc, wid, dest, float(amount))
    if not result.get("success"):
        raise TournamentMoneyError(
            f"Entry transfer failed: {result.get('error') or 'unknown'}"
        )
    tx_id = result.get("transaction_id") or ""
    tx_hash = result.get("tx_hash") or tx_id or f"pending:{tx_id}"
    # Best-effort wait
    if tx_id and hasattr(circle, "wait_for_transaction"):
        try:
            st = await asyncio.to_thread(circle.wait_for_transaction, tx_id, max_wait_seconds=90)
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
    entry_id: Optional[str] = None,
) -> dict[str, Any]:
    """Return entry if player leaves while cup open (or the cup is cancelled).

    The Circle transfer carries a key derived from the ENTRY (not a random
    one): a double /tleave, a cancel racing a leave, or a retried cancel all
    present the same key, so Circle sends the refund once.
    """
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
    key = refund_idempotency_key(cup_code, entry_id or entry_tx_hash or "", profile_id, amount)
    result = await asyncio.to_thread(_transfer_with_key, circle, pot_wid, addr, amount, key)
    if not result.get("success"):
        raise TournamentMoneyError(f"Refund failed: {result.get('error')}")
    tx = result.get("tx_hash") or result.get("transaction_id")
    return {"tx_hash": tx, "mode": "transfer", "amount_usdc": float(amount)}


def refund_idempotency_key(cup_code: str, entry_ref: str, profile_id: str, amount: Decimal) -> str:
    """Deterministic Circle idempotencyKey for one entry's refund."""
    ident = f"tournament:{cup_code}:refund:{entry_ref}:{profile_id}:{Decimal(amount):.6f}"
    return str(uuid.uuid5(_PAYOUT_NS, ident))


def payout_idempotency_key(tournament_key: str, place: Any, profile_id: str, amount: Decimal) -> str:
    """Deterministic Circle idempotencyKey for one (tournament, place) prize."""
    ident = f"tournament:{tournament_key}:place:{place}:{profile_id}:{Decimal(amount):.6f}"
    return str(uuid.uuid5(_PAYOUT_NS, ident))


def _claim_place(tournament_key: str, place: int, profile_id: str, amount: Decimal, key: str) -> tuple[str, dict[str, Any]]:
    """Atomically claim one place for payment.

    Returns (decision, row): "pay" (this worker sends), "paid" (already done),
    or "busy" (another worker is sending it right now).
    """
    from gaming.src.stack.agentic.db import transaction
    from gaming.src.stack.agentic.db.engine import now_ms
    from gaming.src.stack.agentic.db.leases import process_owner
    from gaming.src.stack.agentic.db.money import to_micro
    from datetime import datetime, timezone

    me = process_owner()
    now = now_ms()
    stamp = datetime.now(timezone.utc).isoformat()
    with transaction() as tx:
        row = tx.one(
            "SELECT * FROM tournament_payouts WHERE tournament_key = ? AND place = ?" + tx.for_update,
            (tournament_key, int(place)),
        )
        if row is None:
            # ON CONFLICT: a concurrent claimer may have inserted the place
            # after our (row-less, so lock-less) FOR UPDATE read. No target:
            # its idempotency_key collides too, and either unique index may
            # be the one Postgres checks first.
            if tx.rowcount(
                "INSERT INTO tournament_payouts (tournament_key, place, profile_id, amount_micro, "
                "idempotency_key, status, claimed_by, claimed_at_ms, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'claimed', ?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (tournament_key, int(place), profile_id, to_micro(amount), key, me, now, stamp),
            ):
                return "pay", {"idempotency_key": key}
            row = tx.one(
                "SELECT * FROM tournament_payouts WHERE tournament_key = ? AND place = ?" + tx.for_update,
                (tournament_key, int(place)),
            )
            if row is None:
                return "busy", {}
        if row["status"] == "paid":
            return "paid", row
        if row["status"] in {"claimed", "sent"} and now - int(row.get("claimed_at_ms") or 0) < PAYOUT_CLAIM_STALE_MS:
            return "busy", row
        # failed, or a stale claim from a dead worker: re-drive with the SAME key.
        tx.execute(
            "UPDATE tournament_payouts SET status = 'claimed', claimed_by = ?, claimed_at_ms = ?, "
            "updated_at = ? WHERE tournament_key = ? AND place = ?",
            (me, now, stamp, tournament_key, int(place)),
        )
        return "pay", row


def _record_place(tournament_key: str, place: int, **fields: Any) -> None:
    from datetime import datetime, timezone

    from gaming.src.stack.agentic.db import transaction

    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with transaction() as tx:
        tx.execute(
            f"UPDATE tournament_payouts SET {cols} WHERE tournament_key = ? AND place = ?",
            (*fields.values(), tournament_key, int(place)),
        )


def _transfer_with_key(circle: Any, wallet_id: str, to_address: str, amount: Decimal, key: str) -> dict[str, Any]:
    fn = circle.transfer_usdc
    try:
        accepts_key = "idempotency_key" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        accepts_key = False
    if not accepts_key:
        # Never pay without dedup: a client that cannot take the key is refused.
        return {"success": False, "error": "Circle client lacks idempotency_key support — refusing payout"}
    return fn(wallet_id, to_address, float(amount), idempotency_key=key)


async def pay_payouts(payout_block: dict[str, Any], *, cup_code: str) -> dict[str, Any]:
    """
    Send place prizes from pot wallet. Platform fee stays in pot.
    Mutates / returns places with paid + tx_hash when possible.

    Exactly-once per (cup, place): a place already marked ``paid`` (in the
    block or in the ``tournament_payouts`` table) is skipped; every other place
    is claimed atomically before sending, and the Circle transfer carries a
    deterministic idempotency key, so a retry or a concurrent second caller
    cannot pay the same prize twice.
    """
    places = list((payout_block or {}).get("places") or [])
    pot_wid = pot_wallet_id()
    mode = money_mode()
    paid_any = False
    results = []
    tkey = str(cup_code or (payout_block or {}).get("tournament_id") or "").strip()

    for p in places:
        pid = p.get("profile_id")
        amt = Decimal(str(p.get("amount_usdc") or 0)).quantize(Decimal("0.01"))
        row = dict(p)
        if p.get("paid") and p.get("tx_hash"):
            results.append(row)  # already paid on a previous run
            paid_any = paid_any or p.get("tx_hash") != "zero"
            continue
        if amt <= 0 or not pid:
            row["paid"] = True
            row["tx_hash"] = "zero"
            results.append(row)
            continue

        if not pot_wid or mode == "commit" or not tkey:
            row["paid"] = False
            row["tx_hash"] = None
            row["pay_note"] = (
                "manual — set TOURNAMENT_POT_WALLET_ID for auto payout"
                if tkey
                else "manual — payout block has no tournament key"
            )
            results.append(row)
            continue

        place_no = int(p.get("place") or (len(results) + 1))
        key = payout_idempotency_key(tkey, place_no, str(pid), amt)
        decision, claim = _claim_place(tkey, place_no, str(pid), amt, key)
        if decision == "paid":
            row["paid"] = True
            row["tx_hash"] = claim.get("tx_hash") or claim.get("transaction_id")
            paid_any = True
            results.append(row)
            continue
        if decision == "busy":
            row["paid"] = False
            row["pay_note"] = "payout in progress on another worker"
            results.append(row)
            continue

        try:
            from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

            wallet = await ensure_user_wallet(pid, chain_id="arc")
            addr = wallet.get("address")
            if not addr:
                row["paid"] = False
                row["pay_note"] = "no winner address"
                _record_place(tkey, place_no, status="failed", error="no winner address")
                results.append(row)
                continue
            circle, _ = _circle_for_arc()
            _record_place(tkey, place_no, status="sent")
            result = await asyncio.to_thread(_transfer_with_key, circle, pot_wid, addr, amt, key)
            if result.get("success"):
                row["paid"] = True
                row["tx_hash"] = result.get("tx_hash") or result.get("transaction_id")
                row["idempotency_key"] = key
                _record_place(
                    tkey,
                    place_no,
                    status="paid",
                    transaction_id=result.get("transaction_id"),
                    tx_hash=result.get("tx_hash"),
                    error=None,
                )
                paid_any = True
            else:
                row["paid"] = False
                row["pay_note"] = result.get("error")
                _record_place(tkey, place_no, status="failed", error=str(result.get("error"))[:500])
        except Exception as exc:
            logger.exception("[TourMoney] payout place=%s", p.get("place"))
            row["paid"] = False
            row["pay_note"] = str(exc)
            # Unknown outcome: leave it re-drivable with the same key.
            _record_place(tkey, place_no, status="failed", error=str(exc)[:500])
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
