"""Withdraw USDC from a player's play wallet: every check, then the transfer.

``execute_transfer_sync`` is the Circle transfer plus the audit row, moved
here from ``src/bot/handlers/send.py`` (which now calls it). ``perform_withdrawal``
runs the same gates, in the same order, as the Telegram ``/withdraw`` confirm
step, so a withdrawal confirmed on the web (channels one-time link + PIN)
gets exactly the checks a Telegram one does:

  safety gate (pause, $min–$max per transfer, daily cap, hourly rate) →
  $1–$10,000 bounds → preferred chain, balance, wallet → enough balance →
  wallet id → not to yourself → transfer + audit → daily total, watcher snapshot.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

MIN_SEND = Decimal("1")
MAX_SEND = Decimal("10000")
_TAG_RE = re.compile(r"<[^>]+>")


def _plain(html: str) -> str:
    return _TAG_RE.sub("", html or "").strip()


def execute_transfer_sync(
    sender_id: str,
    sender_wallet_id: str,
    recipient_address: str,
    amount: Decimal,
    recipient_id: Optional[str],
    chain_id: str,
) -> dict:
    """Circle transfer, then an audit row in ``gaming.wallet_debit_audit``."""
    from backend.supabase_client import get_supabase
    from gaming.src.backend.services.clawstation_circle import _circle_for_chain

    circle = _circle_for_chain(chain_id)
    result = circle.transfer_usdc(sender_wallet_id, recipient_address, float(amount))

    audit = {
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "recipient_address": recipient_address.lower(),
        "amount_usdc": float(amount),
        "circle_transaction_id": result.get("transaction_id") if result.get("success") else None,
        "tx_hash": result.get("tx_hash"),
        "status": "pending" if result.get("success") else "failed",
        "settlement_chain": chain_id,
    }
    try:
        # The transfer above already happened: an audit failure (Supabase
        # down, client misconfigured) must never turn it into "nothing sent".
        sb = get_supabase()
        sb.schema("gaming").table("wallet_debit_audit").insert(audit).execute()
    except Exception as exc:
        # Retry without optional chain column if schema is older
        logger.warning("[Withdraw] audit insert failed, retry bare: %s", exc)
        bare = {k: v for k, v in audit.items() if k != "settlement_chain"}
        try:
            sb.schema("gaming").table("wallet_debit_audit").insert(bare).execute()
        except Exception:
            logger.exception("[Withdraw] audit insert failed")
    return result


@dataclass
class WithdrawOutcome:
    ok: bool
    code: str  # ok | gate | bounds | wallet_error | insufficient | no_wallet | self | failed
    message: str  # plain text for any channel
    amount: Decimal = Decimal("0")
    chain: str = ""
    tx_hash: Optional[str] = None
    transaction_id: Optional[str] = None
    new_balance: Optional[Decimal] = None


async def perform_withdrawal(
    profile_id: str,
    *,
    recipient_address: str,
    amount: Decimal,
    recipient_id: Optional[str] = None,
) -> WithdrawOutcome:
    from gaming.src.backend.services.play_adjust import PlaySpendBusy, spend_lock
    from gaming.src.backend.services.safety import assert_money_ops_allowed

    gate = assert_money_ops_allowed(profile_id, action="withdraw", amount=amount, kind="withdraw")
    if gate:
        return WithdrawOutcome(False, "gate", _plain(gate), amount)
    if amount < MIN_SEND or amount > MAX_SEND:
        return WithdrawOutcome(False, "bounds", f"Amount must be between ${MIN_SEND} and ${MAX_SEND}.", amount)
    # Balance check -> daily-cap reservation -> transfer, one spend of this
    # play balance at a time: two withdrawals (web link + Telegram), or a
    # withdrawal and a bet, can no longer both pass the same checks.
    try:
        with spend_lock(profile_id):
            return await _perform_locked(profile_id, recipient_address, amount, recipient_id)
    except PlaySpendBusy as exc:
        return WithdrawOutcome(False, "busy", str(exc), amount)


async def _perform_locked(
    profile_id: str, recipient_address: str, amount: Decimal, recipient_id: Optional[str]
) -> WithdrawOutcome:
    from gaming.src.backend.services import clawstation_circle as circle
    from gaming.src.backend.services.chains import get_chain
    from gaming.src.backend.services.safety import release_daily_withdraw, reserve_daily_withdraw

    try:
        pref = await circle.get_preferred_chain(profile_id)
        balance = await circle.get_usdc_balance(profile_id, chain_id=pref)
        wallet = await circle.ensure_user_wallet(profile_id, chain_id=pref)
    except Exception as exc:
        logger.warning("[Withdraw] wallet check failed", exc_info=True)
        return WithdrawOutcome(False, "wallet_error", f"Could not check your wallet ({type(exc).__name__}).", amount)
    label = get_chain(pref).get("label", pref)
    if balance < amount:
        return WithdrawOutcome(
            False, "insufficient",
            f"Not enough balance on {label}: you have ${balance:,.2f} and asked for ${amount:,.2f}.",
            amount, pref,
        )
    wallet_id = wallet.get("wallet_id")
    if not wallet_id:
        return WithdrawOutcome(False, "no_wallet", "Your wallet is not set up yet.", amount, pref)
    own = (wallet.get("address") or "").lower()
    if recipient_id == profile_id or (own and recipient_address.lower() == own):
        return WithdrawOutcome(False, "self", "You cannot withdraw to yourself.", amount, pref)

    cap = reserve_daily_withdraw(profile_id, amount)
    if cap:
        return WithdrawOutcome(False, "gate", _plain(cap), amount, pref)
    result = await asyncio.to_thread(
        execute_transfer_sync, profile_id, wallet_id, recipient_address, amount, recipient_id, pref
    )
    if not result.get("success"):
        release_daily_withdraw(profile_id, amount)
        return WithdrawOutcome(False, "failed", f"Withdrawal failed: {result.get('error') or 'unknown error'}",
                               amount, pref)
    try:
        new_bal = await circle.get_usdc_balance(profile_id, chain_id=pref)
    except Exception:
        new_bal = balance - amount
    try:
        from gaming.src.backend.services.wallet_activity import set_snapshot

        # Align the watcher so its next poll doesn't DM this outflow twice.
        set_snapshot(profile_id, pref, new_bal)
    except Exception:
        pass
    logger.info("[Withdraw] user=%s amount=%s chain=%s status=%s",
                profile_id[:8], amount, pref, result.get("status"))
    return WithdrawOutcome(
        True, "ok", f"Withdrawal of ${amount:,.2f} USDC submitted on {label}.", amount, pref,
        tx_hash=result.get("tx_hash"), transaction_id=result.get("transaction_id"), new_balance=new_bal,
    )
