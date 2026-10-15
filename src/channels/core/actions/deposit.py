"""Deposits: a Paystack naira top-up or the crypto play address.

Reuses ``fiat_topup`` (quote, top-up record) and ``paystack`` (initialize,
verify) exactly as the Telegram Paystack path does, with two differences that
matter off Telegram: the Paystack email never contains a phone number, and
"I've paid" checks only the caller's own top-ups.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

EMAIL_DOMAIN = "boardman.playingsidequest.fun"


class DepositError(Exception):
    pass


def paystack_ready() -> bool:
    from gaming.src.backend.services.funding_rails import naira_paystack_enabled
    from gaming.src.backend.services.paystack import paystack_configured

    return paystack_configured() and naira_paystack_enabled()


def paystack_email(profile: dict, channel: str, external_id: str) -> str:
    """Verified email if we have one, else a synthetic address with no PII."""
    explicit = (os.getenv("PAYSTACK_DEFAULT_EMAIL") or "").strip()
    if explicit:
        return explicit
    backup = (profile.get("gaming_backup_email") or "").strip()
    if backup and "@" in backup:
        return backup
    tg = profile.get("telegram_id")
    if channel == "telegram" or tg:
        return f"tg{tg or external_id}@{EMAIL_DOMAIN}"
    digest = hashlib.sha256(str(profile.get("id") or external_id).encode()).hexdigest()[:16]
    return f"wa{digest}@{EMAIL_DOMAIN}"


@dataclass
class PaystackStart:
    ref: str
    url: str
    credit_usdc: Decimal
    amount_ngn: Decimal
    fee_note: str
    rate: Decimal


async def start_paystack(profile: dict, *, channel: str, external_id: str, raw_amount: str,
                         display_name: str = "") -> PaystackStart:
    from gaming.src.backend.services.fiat_topup import (
        create_topup,
        parse_ngn_amount,
        quote_from_ngn,
        update_topup,
    )
    from gaming.src.backend.services.paystack import initialize_transaction

    if not paystack_ready():
        raise DepositError("Naira payments are not switched on yet.")
    try:
        amount = parse_ngn_amount(raw_amount)
        quote = quote_from_ngn(amount)
    except ValueError as exc:
        raise DepositError(str(exc)) from exc

    pid = str(profile["id"])
    play_addr = ""
    try:
        from gaming.src.channels.core.actions.wallet import play_address

        play_addr = await play_address(pid)
    except Exception:
        logger.exception("[channels] play address lookup failed")

    def _sync() -> PaystackStart:
        top = create_topup(
            profile_id=pid,
            telegram_id=int(profile.get("telegram_id") or 0),
            display_name=display_name or str(profile.get("gaming_tag") or ""),
            quote=quote,
            play_address=play_addr,
            currency="ngn",
            amount_fiat=amount,
            provider="paystack",
        )
        ps_ref = top.ref.replace("-", "")
        init = initialize_transaction(
            email=paystack_email(profile, channel, external_id),
            amount_ngn=amount,
            reference=ps_ref,
            metadata={
                "boardman_ref": top.ref,
                "profile_id": pid,
                "channel": channel,
                "credit_usdc": str(quote.credit_usdc),
                "play_address": play_addr,
            },
        )
        url = init.get("authorization_url") or ""
        update_topup(
            top.ref,
            paystack_reference=ps_ref,
            paystack_access_code=init.get("access_code") or "",
            authorization_url=url,
            provider="paystack",
        )
        return PaystackStart(top.ref, url, quote.credit_usdc, amount, quote.fee_note, quote.rate_ngn_per_usd)

    try:
        out = await asyncio.to_thread(_sync)
    except DepositError:
        raise
    except Exception as exc:
        logger.exception("[channels] Paystack init failed")
        raise DepositError("Could not start Paystack. Try again in a minute.") from exc
    await alert_admins(
        f"🆕 Fiat top-up {out.ref} via {channel}\nCredit due: ${out.credit_usdc:,.2f}\nStatus: awaiting payment"
    )
    return out


@dataclass
class PaystackCheck:
    status: str  # credited | paid | pending | mismatch | unknown | error
    credit_usdc: Decimal = Decimal("0")
    paid_ngn: Decimal = Decimal("0")
    detail: str = ""
    url: str = ""


async def check_paystack(profile_id: str, ref: str) -> PaystackCheck:
    from gaming.src.backend.services.fiat_topup import get_topup, update_topup
    from gaming.src.backend.services.paystack import verify_transaction

    row: Optional[dict[str, Any]] = await asyncio.to_thread(get_topup, ref)
    if not row or str(row.get("profile_id")) != str(profile_id):
        return PaystackCheck("unknown")
    credit = Decimal(str(row.get("credit_usdc") or 0))
    url = str(row.get("authorization_url") or "")
    if row.get("status") == "credited":
        return PaystackCheck("credited", credit)
    if row.get("status") == "paystack_paid":
        return PaystackCheck("paid", credit)
    ps_ref = row.get("paystack_reference") or str(row.get("ref") or ref).replace("-", "")
    try:
        result = await asyncio.to_thread(verify_transaction, ps_ref)
    except Exception:
        logger.warning("[channels] Paystack verify failed", exc_info=True)
        return PaystackCheck("error", credit, url=url)
    if not result.get("paid"):
        return PaystackCheck("pending", credit, detail=str(result.get("status") or "unknown"), url=url)
    paid = Decimal(str(result.get("amount_ngn") or 0))
    expected = Decimal(str(row.get("amount_ngn") or row.get("amount_fiat") or 0))
    real_ref = str(row.get("ref"))
    if expected and abs(paid - expected) > 1:
        await asyncio.to_thread(
            update_topup, real_ref, status="proof_submitted",
            proof_text=f"paystack_paid_amount_mismatch paid={paid} expected={expected}",
            admin_note="amount_mismatch",
        )
        await alert_admins(f"⚠️ Paystack amount mismatch {real_ref}: paid ₦{paid} vs ₦{expected}")
        return PaystackCheck("mismatch", credit, paid)
    await asyncio.to_thread(
        update_topup, real_ref, status="paystack_paid",
        proof_text=f"paystack success channel={result.get('channel')} paid_at={result.get('paid_at')}",
    )
    await alert_admins(
        f"⚡ Paystack PAID {real_ref}\n₦{paid:,.2f} → credit ${credit:,.2f} USDC\n"
        f"Play: {row.get('play_address') or '—'}\n1) Send USDC from float/Kobox\n2) /credit_topup {real_ref}"
    )
    return PaystackCheck("paid", credit, paid)


async def alert_admins(text: str) -> None:
    """Ops alerts stay on Telegram (CHANNELS_DESIGN §8.9). Best effort."""
    try:
        from gaming.src.backend.services.safety import admin_telegram_ids
        from gaming.src.bot.utils.notify import _ensure_bot

        bot = _ensure_bot()
        if bot is None:
            return
        for aid in admin_telegram_ids():
            try:
                await bot.send_message(aid, text, parse_mode=None)
            except Exception:
                logger.debug("[channels] admin alert failed", exc_info=True)
    except Exception:
        logger.debug("[channels] admin alerts unavailable", exc_info=True)


def crypto_instructions(address: str) -> str:
    from gaming.src.backend.services.funding_rails import player_copy

    hint = (player_copy() or {}).get("convert_hint", "")
    body = (
        "*Fund with crypto*\n\n"
        "Send USDC on *Arc* to your play address (your Boardman wallet):\n"
        f"`{address or 'not ready yet, try again in a minute'}`\n\n"
        "Your balance updates once it lands. Any other network or token can be lost."
    )
    return body + (f"\n\n{hint}" if hint else "")
