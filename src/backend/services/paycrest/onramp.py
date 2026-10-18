"""Naira in: NGN bank transfer → USDC on Base (Paycrest) → Arc play wallet (CCTP).

1. Chat: amount → quote → one-time link (``/app/naira/<token>``). The order
   is ``quoted``; nothing has been sent anywhere yet.
2. Web page: the player types their KYC (full name, date of birth, BVN or
   NIN) and their own refund bank account. Boardman checks the account name
   with Paycrest's verify-account, creates the Paycrest order with the KYC in
   ``source.kyc`` and forgets the KYC (pass-through, never written to disk).
   The page and the chat show the virtual account to pay (``awaiting_deposit``).
3. Paycrest webhooks move the order; ``settled`` means USDC arrived in the
   player's Base "in" wallet; ``sweep`` bridges it to the Arc play wallet
   (``bridging``) and the bridge listener completes it (``completed``).

Expired orders (account never funded) and refunds (naira returned) end the
order with a plain notice; no USDC ever moved.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Optional

from gaming.src.backend.services.paycrest import config, notices, quotes, store, wallets
from gaming.src.backend.services.paycrest.client import get_client
from gaming.src.backend.services.paycrest.models import (
    AmbiguousSubmit,
    BankAccount,
    KycPerson,
    KycRejected,
    PaycrestError,
)

logger = logging.getLogger(__name__)

DAY_MS = 24 * 3600 * 1000
TOKEN_PURPOSE = "naira_kyc"


class NairaError(Exception):
    def __init__(self, message: str, kind: str = "refused") -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind


def parse_ngn(raw: str) -> Optional[Decimal]:
    s = (raw or "").strip().lower().replace(",", "").replace("₦", "").replace("ngn", "").replace("naira", "")
    s = s.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(k)?", s)
    if not m:
        return None
    try:
        v = Decimal(m.group(1))
    except InvalidOperation:
        return None
    if m.group(2):
        v *= 1000
    return v.quantize(Decimal("1")) if v > 0 else None


def _used(profile_id: str, direction: str, column: str, now_ms: int) -> Decimal:
    return sum((Decimal(v) for v in store.sum_recent(profile_id, direction, column, now_ms - DAY_MS)),
               Decimal("0"))


def limit_problem(profile_id: str, amount_ngn: Decimal, *, now_ms: int) -> Optional[str]:
    lim = config.limits()
    if amount_ngn < lim.onramp_min_ngn:
        return f"The smallest naira top-up is ₦{lim.onramp_min_ngn:,.0f}."
    if amount_ngn > lim.onramp_max_ngn:
        return f"The largest naira top-up is ₦{lim.onramp_max_ngn:,.0f}."
    used = _used(profile_id, "onramp", "amount_ngn", now_ms)
    if used + amount_ngn > lim.onramp_daily_ngn:
        left = max(Decimal("0"), lim.onramp_daily_ngn - used)
        return f"Daily naira limit is ₦{lim.onramp_daily_ngn:,.0f}. You can top up ₦{left:,.0f} more today."
    return None


@dataclass
class StartedOnramp:
    order_id: str
    url: str
    quote: quotes.OnrampQuote
    expires_at_ms: int


def start(profile_id: str, *, channel: str, external_id: str, amount_ngn: Decimal, arc_address: str,
          now_ms: Optional[int] = None) -> StartedOnramp:
    """Quote and open a one-time KYC/payment link. Sync: call in a thread."""
    from gaming.src.channels.core import withdraw_links
    from gaming.src.channels.core.withdraw_links import LinkRefused

    if not config.enabled():
        raise NairaError("Naira top-ups are not switched on.", "off")
    now = now_ms if now_ms is not None else store.now_ms()
    problem = limit_problem(profile_id, amount_ngn, now_ms=now)
    if problem:
        raise NairaError(problem, "limit")
    try:
        q = quotes.quote_onramp(amount_ngn, now_ms=now)
    except PaycrestError as exc:
        logger.warning("[paycrest] on-ramp quote failed: %s", exc)
        raise NairaError("Paycrest can't quote naira right now. Try again in a few minutes.", "unavailable")
    for old in store.list_orders(statuses=("quoted",), profile_id=profile_id, direction="onramp"):
        store.transition(old["id"], "cancelled", expect="quoted", error="superseded")
    key = f"bm-on-{uuid.uuid4().hex[:24]}"
    ttl = config.limits().quote_ttl_sec * 1000
    order, _ = store.create_order(
        idempotency_key=key, direction="onramp", profile_id=profile_id, status="quoted",
        channel=channel, external_id=str(external_id), amount_ngn=str(amount_ngn),
        amount_usdc=str(q.receive_usdc), rate=str(q.rate), quote=q.to_json(),
        details={"arc_address": arc_address}, expires_at_ms=now + ttl,
    )
    try:
        link = withdraw_links.issue_purpose(
            TOKEN_PURPOSE, profile_id, channel=channel, external_id=str(external_id),
            payload={"order_id": order["id"]}, now_ms=now, rate_bucket=f"naira_issue:{profile_id}",
            path="naira",
        )
    except LinkRefused as exc:
        store.transition(order["id"], "cancelled", expect="quoted", error="link_refused")
        raise NairaError(exc.message, exc.kind)
    return StartedOnramp(order["id"], link.url, q, link.expires_at_ms)


# ── the web page ────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _institutions_cached(_day: int) -> tuple:
    try:
        return tuple((i.code, i.name, i.type) for i in get_client().list_institutions())
    except PaycrestError:
        return ()


def institutions() -> list[dict[str, str]]:
    rows = _institutions_cached(store.now_ms() // DAY_MS)
    if not rows:
        _institutions_cached.cache_clear()  # never cache an outage for a day
    return [{"code": c, "name": n, "type": t} for c, n, t in rows]


def institution_name(code: str) -> str:
    for i in institutions():
        if i["code"] == code:
            return i["name"]
    return code


def _token_row(token: str, session_profile_id: Optional[str], now: int) -> dict:
    from gaming.src.channels.core import withdraw_links

    return withdraw_links.check_open(withdraw_links.load(token), now, session_profile_id,
                                     purposes=(TOKEN_PURPOSE,))


def view(token: str, *, session_profile_id: Optional[str] = None, now_ms: Optional[int] = None) -> dict:
    now = now_ms if now_ms is not None else store.now_ms()
    row = _token_row(token, session_profile_id, now)
    order = store.get_order(row["payload"].get("order_id") or "")
    if not order or order["status"] != "quoted":
        from gaming.src.channels.core.withdraw_links import LinkRefused

        raise LinkRefused("used", "This top-up was already started or cancelled. Start again in the chat.")
    q = order.get("quote") or {}
    return {
        "ok": True,
        "purpose": TOKEN_PURPOSE,
        "amount_ngn": order["amount_ngn"],
        "rate": q.get("rate"),
        "receive_usdc": q.get("receive_usdc"),
        "bridge_fee_max_usdc": q.get("bridge_fee_max_usdc"),
        "sender_fee_usdc": q.get("sender_fee_usdc"),
        "id_types": list(config.kyc_id_types()),
        "institutions": institutions(),
        "expires_in_sec": max(0, (int(row["expires_at_ms"]) - now) // 1000),
        "real_money": True,
    }


def _norm_words(name: str) -> set[str]:
    return {w for w in re.split(r"[^a-z]+", (name or "").lower()) if len(w) > 1}


def names_match(bank_name: str, kyc_name: str) -> bool:
    """Bank-resolved holder name vs the KYC name: at least two shared words
    (or every word of the shorter one). Paycrest enforces its own check too."""
    a, b = _norm_words(bank_name), _norm_words(kyc_name)
    if not a or not b:
        return False
    shared = a & b
    return len(shared) >= 2 or shared == a or shared == b


def _parse_valid_until(raw: str) -> Optional[int]:
    if not raw:
        return None
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def pay_text(pa: dict, *, reference: str = "") -> str:
    amount = Decimal(str(pa.get("amount_to_transfer") or "0"))
    bank = institution_name(pa.get("institution") or "")
    until = pa.get("valid_until") or ""
    return (
        "*Pay this exact amount by bank transfer:*\n"
        f"₦{amount:,.2f} to {bank}\n"
        f"Account: `{pa.get('account_identifier')}` ({pa.get('account_name')})\n"
        + (f"Before: {until}\n" if until else "")
        + "\nPay from YOUR OWN bank account (the one you gave as refund account). "
        "Payments from someone else's account are held and sent back. "
        "This is real money: Boardman never asks you to pay any other account."
        + (f"\nRef: {reference}" if reference else "")
    )


def submit(token: str, *, kyc: dict[str, Any], refund: dict[str, Any], session_profile_id: Optional[str] = None,
           now_ms: Optional[int] = None) -> dict:
    """Create the Paycrest order with the player's KYC (pass-through)."""
    from gaming.src.channels.core import ratelimit, withdraw_links
    from gaming.src.channels.core.withdraw_links import LinkRefused

    now = now_ms if now_ms is not None else store.now_ms()
    row = _token_row(token, session_profile_id, now)
    pid = row["profile_id"]
    order = store.get_order(row["payload"].get("order_id") or "")
    if not order or order["status"] != "quoted":
        raise LinkRefused("used", "This top-up was already started or cancelled. Start again in the chat.")
    if not config.enabled():
        raise LinkRefused("bad_request", "Naira top-ups are switched off right now.")
    if not ratelimit.hit(f"naira_submit:{pid}", limit=10, window_sec=3600):
        raise LinkRefused("rate_limited", "Too many tries. Try again in an hour.")

    person = KycPerson(
        full_name=str(kyc.get("full_name") or ""), birth_date=str(kyc.get("birth_date") or ""),
        id_type=str(kyc.get("id_type") or ""), id_number=re.sub(r"\D", "", str(kyc.get("id_number") or "")),
        email=str(kyc.get("email") or "").strip(), phone_e164=str(kyc.get("phone") or "").strip(),
    )
    problem = person.validate(allowed_types=config.kyc_id_types())
    acct = BankAccount(str(refund.get("institution") or "").strip().upper(),
                       re.sub(r"\D", "", str(refund.get("account_identifier") or "")))
    problem = problem or acct.validate()
    if problem:
        raise LinkRefused("bad_request", problem)

    client = get_client()
    try:
        resolved = client.verify_account(acct.institution, acct.account_identifier)
    except PaycrestError:
        raise LinkRefused("bad_request", "We couldn't check that bank account. Check the number and try again.")
    if resolved and resolved.upper() != "OK" and not names_match(resolved, person.full_name):
        raise LinkRefused("bad_request", "The refund account must be in your own name, matching the name you "
                                         "entered. Use your own account.")
    holder = resolved if resolved and resolved.upper() != "OK" else " ".join(person.full_name.split())
    acct = BankAccount(acct.institution, acct.account_identifier, holder, institution_name(acct.institution))

    if not store.transition(order["id"], "submitting", expect="quoted"):
        raise LinkRefused("used", "This top-up was already started. Check the chat for the account to pay.")
    base = wallets.base_wallet(pid, "in")
    payload: dict[str, Any] = {
        "amount": str(Decimal(order["amount_ngn"])),
        "amountIn": "fiat",
        "transactionFeePayer": config.transaction_fee_payer(),
        "reference": order["idempotency_key"],
        "source": {"type": "fiat", "currency": config.currency(), "refundAccount": acct.to_api(),
                   "kyc": person.to_api()},
        "destination": {"type": "crypto", "currency": config.token(),
                        "recipient": {"address": base["address"], "network": config.network()}},
    }
    if config.sender_fee_percent() > 0:
        payload["senderFeePercent"] = str(config.sender_fee_percent())
    details = {"refund_account": acct.masked, "base_address": base["address"], "kyc_id_type": person.id_type,
               "reference": order["idempotency_key"]}
    del person  # pass-through: the KYC lives only in this request
    try:
        pc = client.create_order(payload)
    except KycRejected as exc:
        store.transition(order["id"], "failed", expect="submitting", error="kyc_rejected", details=details)
        withdraw_links.set_status(row["token_hash"], "burned", {"reason": "kyc_rejected"})
        logger.info("[paycrest] KYC refused for order %s", order["id"])
        return {"ok": False, "error": "kyc_rejected",
                "message": "Paycrest could not verify those details. Check that your name, date of birth and "
                           "BVN/NIN match your bank records, then start again in the chat. "
                           f"({str(exc)[:120]})"}
    except AmbiguousSubmit:
        store.transition(order["id"], "submit_unknown", expect="submitting", details=details,
                         next_attempt_at_ms=now + 60_000)
        withdraw_links.set_status(row["token_hash"], "done", {"status": "submit_unknown"})
        return {"ok": True, "status": "confirming",
                "message": "We're confirming your order with Paycrest. The chat will send you the account to pay "
                           "in a minute. Don't pay anything until it does."}
    except PaycrestError as exc:
        if exc.retryable:
            store.transition(order["id"], "quoted", expect="submitting")
            raise LinkRefused("bad_request", "Paycrest has no naira provider free right now. Try again in a "
                                             "minute; nothing was charged.")
        store.transition(order["id"], "failed", expect="submitting", error=f"paycrest_{exc.status_code}",
                         details=details)
        withdraw_links.set_status(row["token_hash"], "burned", {"reason": "paycrest_error"})
        return {"ok": False, "error": "failed", "message": "Paycrest refused this order. Nothing was charged. "
                                                           "Start again in the chat or contact support."}
    return _accepted(order, pc, details, token_hash=row["token_hash"])


def _accepted(order: dict, pc: Any, details: dict, *, token_hash: Optional[str] = None) -> dict:
    from gaming.src.channels.core import withdraw_links

    pa = pc.provider_account.to_json() if pc.provider_account else {}
    moved = store.transition(
        order["id"], "awaiting_deposit", expect=("submitting", "submit_unknown"), paycrest_id=pc.id,
        paycrest_status=pc.status, provider_account=pa, details=details,
        expires_at_ms=_parse_valid_until(pa.get("valid_until") or ""),
    )
    if token_hash:
        withdraw_links.set_status(token_hash, "done", {"status": "awaiting_deposit"})
    text = pay_text(pa, reference=order["idempotency_key"][-8:])
    if moved:
        notices.tell(order["profile_id"], text)
    return {"ok": True, "status": "awaiting_deposit", "pay": pa, "bank_name": institution_name(pa.get("institution")
                                                                                               or ""),
            "message": "Order created. Pay the exact amount below from your own account."}


# ── after Paycrest settles: Base → Arc ───────────────────────────────────────


def sweep(profile_id: str) -> Optional[dict]:
    """Bridge everything in the player's Base "in" wallet to their play wallet,
    covering every settled on-ramp order. Safe to call repeatedly."""
    from gaming.src.backend.services.bridge import cctp
    from gaming.src.backend.services.bridge.chain_ops import get_chain_ops

    settled = store.list_orders(statuses=("settled",), profile_id=profile_id, direction="onramp")
    if not settled:
        return None
    w = store.get_wallet(profile_id, f"{config.delivery_chain()}/in")
    if not w:
        notices.alert_admins(f"Paycrest on-ramp settled for {profile_id[:8]} but no Base wallet is recorded")
        return None
    bal = get_chain_ops().usdc_balance(config.delivery_chain(), w["address"])
    b = config.bridge()
    if bal < b.min_sweep_usdc:
        return None  # not visible on Base yet; the reconciler tries again
    arc = (settled[0].get("details") or {}).get("arc_address") or ""
    if not arc:
        arc = wallets.arc_destination_sync(profile_id)
    ids = sorted(o["id"] for o in settled)
    key = "sweep:" + "|".join(ids)
    br = cctp.start(idempotency_key=key, kind="onramp_sweep", profile_id=profile_id,
                    src_chain=config.delivery_chain(), dst_chain=config.settlement_chain(), amount=bal,
                    from_wallet_id=w["wallet_id"], mint_recipient=arc, fast=b.onramp_fast_transfer,
                    max_fee_bps=b.max_fee_bps)
    for o in settled:
        store.transition(o["id"], "bridging", expect="settled", bridge_id=br["id"])
    notices.tell(profile_id, f"Your naira top-up arrived: ${bal:,.2f} USDC is on its way to your play wallet "
                             "(usually under a minute).")
    return br


def on_bridge_finished(br: dict) -> None:
    if br.get("kind") != "onramp_sweep":
        return
    orders = [o for o in store.list_orders(statuses=("bridging",), profile_id=br["profile_id"],
                                           direction="onramp") if o.get("bridge_id") == br["id"]]
    if br["status"] == "minted":
        for o in orders:
            store.transition(o["id"], "completed", expect="bridging", settled_at_ms=store.now_ms())
        notices.tell(br["profile_id"], f"*Your naira top-up is in your play wallet* (about "
                                       f"${Decimal(br.get('minted_usdc') or br['amount_usdc']):,.2f} USDC after the "
                                       "bridge fee). Ready to play.",
                     kind="naira_update")
    else:
        for o in orders:
            store.transition(o["id"], "needs_review", expect="bridging", error="bridge_failed")
        notices.alert_admins(f"Paycrest on-ramp bridge {br['id']} FAILED for {br['profile_id'][:8]}: "
                             f"${br['amount_usdc']} sits in the Base wallet. Check bridge_transfers.")
        notices.tell(br["profile_id"], "Your naira top-up reached us but moving it to your play wallet is "
                                       "delayed. Your money is safe; support is on it.")
