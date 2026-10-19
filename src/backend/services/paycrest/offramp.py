"""Naira out: Arc play wallet → Base (CCTP) → Paycrest → the player's bank.

Chat: bank (from Paycrest's institution list) → 10-digit account number →
verify-account shows the holder's name → amount → quote → the usual one-time
withdraw link. Nothing moves until the player enters their PIN on the web
page (``withdraw_links.confirm`` calls ``perform``).

After the PIN:
  confirmed → bridging_out   burn on Arc, mint into the player's Base "out" wallet
  → on_base → submitting     create the Paycrest order (refundAddress = that wallet)
  → awaiting_settlement      send ``amountToTransfer`` to Paycrest's receive address
  → processing → completed   Paycrest paid the bank (webhook ``settled``)
Refunds (``refunded``): the USDC comes back to the Base "out" wallet and is
bridged home: refunded_on_base → refund_bridging → refunded.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional

from gaming.src.backend.services.paycrest import config, notices, quotes, store, wallets
from gaming.src.backend.services.paycrest.client import get_client
from gaming.src.backend.services.paycrest.models import AmbiguousSubmit, BankAccount, PaycrestError
from gaming.src.backend.services.paycrest.onramp import DAY_MS, NairaError, institution_name, institutions

logger = logging.getLogger(__name__)

ARC_GAS_RESERVE = Decimal("0.05")   # USDC kept back for the approve + burn gas on Arc
MIN_SEND = Decimal("0.50")          # Paycrest minimum order
CENT = Decimal("0.01")

# A short list for chat buttons; the full list comes from Paycrest
# (GET /institutions/NGN) and a typed bank name is matched against it.
POPULAR_BANKS = ("OPay", "PalmPay", "Moniepoint", "Kuda", "Access", "GTBank", "Zenith", "UBA", "First Bank")


def search_banks(query: str, limit: int = 8) -> list[dict[str, str]]:
    q = re.sub(r"[^a-z0-9]", "", (query or "").lower())
    if not q:
        return []
    out = []
    for i in institutions():
        name = re.sub(r"[^a-z0-9]", "", i["name"].lower())
        if q in name or q == i["code"].lower():
            out.append(i)
    out.sort(key=lambda i: (not re.sub(r"[^a-z0-9]", "", i["name"].lower()).startswith(q), len(i["name"])))
    return out[:limit]


def popular_banks() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name in POPULAR_BANKS:
        hits = search_banks(name, limit=1)
        if hits and hits[0] not in out:
            out.append(hits[0])
    return out


def resolve_account(institution: str, account_number: str) -> dict[str, str]:
    """Check the account with Paycrest. Returns a bank dict for the link payload."""
    acct = BankAccount(institution.strip().upper(), re.sub(r"\D", "", account_number or ""))
    problem = acct.validate()
    if problem:
        raise NairaError(problem, "bad_account")
    try:
        name = get_client().verify_account(acct.institution, acct.account_identifier)
    except PaycrestError as exc:
        if exc.retryable:
            raise NairaError("Couldn't reach the bank to check that account. Try again in a minute.", "unavailable")
        raise NairaError("That account number doesn't look right for this bank.", "bad_account")
    if not name or name.upper() == "OK":
        raise NairaError("The bank didn't confirm a name for that account, so we can't pay it safely. "
                         "Use another account.", "bad_account")
    bank_name = institution_name(acct.institution)
    full = BankAccount(acct.institution, acct.account_identifier, name, bank_name)
    return {"institution": acct.institution, "institution_name": bank_name,
            "account_identifier": acct.account_identifier, "account_name": name, "label": full.masked}


def limit_problem(profile_id: str, amount: Decimal, *, now_ms: int) -> Optional[str]:
    lim = config.limits()
    if amount < lim.offramp_min_usdc:
        return f"The smallest naira cash-out is ${lim.offramp_min_usdc:,.2f}."
    if amount > lim.offramp_max_usdc:
        return f"The largest naira cash-out is ${lim.offramp_max_usdc:,.2f}."
    used = sum((Decimal(v) for v in store.sum_recent(profile_id, "offramp", "amount_usdc", now_ms - DAY_MS)),
               Decimal("0"))
    if used + amount > lim.offramp_daily_usdc:
        left = max(Decimal("0"), lim.offramp_daily_usdc - used)
        return f"Daily naira cash-out limit is ${lim.offramp_daily_usdc:,.2f}. You can cash out ${left:,.2f} more today."
    return None


@dataclass
class Prepared:
    url: str
    quote: quotes.OfframpQuote
    bank: dict


def prepare(principal: Any, amount: Decimal, bank: dict, *, now_ms: Optional[int] = None) -> Prepared:
    """Checks + quote + the PIN link (sync: call in a thread)."""
    from gaming.src.channels.core import withdraw_links
    from gaming.src.channels.core.actions.withdraw import precheck

    if not config.enabled():
        raise NairaError("Naira cash-outs are not switched on.", "off")
    if wallets.passkey_account(principal.profile_id):
        # TODO(self-custody): build calls.cctp_burn_calls() as a passkey intent
        # and continue this order from the bridge's ``burned`` state.
        raise NairaError("Cash out to bank isn't available for passkey wallets yet. Withdraw USDC to an "
                         "exchange that supports Arc instead.", "self_custody")
    now = now_ms if now_ms is not None else store.now_ms()
    reason = precheck(principal, amount) or limit_problem(principal.profile_id, amount, now_ms=now)
    if reason:
        raise NairaError(reason, "limit")
    try:
        q = quotes.quote_offramp(amount, now_ms=now)
    except PaycrestError:
        raise NairaError("Paycrest can't quote naira right now. Try again in a few minutes.", "unavailable")
    try:
        link = withdraw_links.issue_naira(principal.profile_id, channel=principal.channel,
                                          external_id=principal.external_id, amount=amount, bank=bank,
                                          quote=q.to_json(), now_ms=now)
    except withdraw_links.LinkRefused as exc:
        raise NairaError(exc.message, exc.kind)
    return Prepared(link.url, q, bank)


# ── after the PIN ───────────────────────────────────────────────────────────


async def perform(profile_id: str, *, amount: Decimal, payload: dict, link_hash: str) -> Any:
    """Called once by ``withdraw_links.confirm`` after the PIN and the claim."""
    from gaming.src.backend.services import clawstation_circle as circle
    from gaming.src.backend.services.bridge import cctp
    from gaming.src.backend.services.safety import assert_money_ops_allowed, commit_daily_withdraw
    from gaming.src.backend.services.withdrawals import WithdrawOutcome, _plain

    settle = config.settlement_chain()
    if not config.enabled():
        return WithdrawOutcome(False, "gate", "Naira cash-outs are switched off right now. Nothing was sent.", amount)
    gate = assert_money_ops_allowed(profile_id, action="withdraw", amount=amount, kind="withdraw")
    if gate:
        return WithdrawOutcome(False, "gate", _plain(gate), amount)
    problem = limit_problem(profile_id, amount, now_ms=store.now_ms())
    if problem:
        return WithdrawOutcome(False, "bounds", problem, amount)
    bank = dict(payload.get("bank") or {})
    if not bank.get("account_identifier"):
        return WithdrawOutcome(False, "failed", "This cash-out link has no bank account. Start again.", amount)
    try:
        balance = await circle.get_usdc_balance(profile_id, chain_id=settle)
        play = await wallets.play_wallet(profile_id)
        out_w = await asyncio.to_thread(wallets.base_wallet, profile_id, "out")
    except Exception as exc:
        logger.warning("[paycrest] cash-out wallet check failed", exc_info=True)
        return WithdrawOutcome(False, "wallet_error", f"Could not check your wallet ({type(exc).__name__}).", amount)
    if balance < amount + ARC_GAS_RESERVE:
        return WithdrawOutcome(False, "insufficient",
                               f"Not enough balance: you have ${balance:,.2f}; this cash-out needs "
                               f"${amount:,.2f} plus about ${ARC_GAS_RESERVE} network gas.", amount, settle)
    if not play.get("wallet_id"):
        return WithdrawOutcome(False, "no_wallet", "Your wallet is not set up yet.", amount, settle)

    q = payload.get("quote") or {}
    order, created = await asyncio.to_thread(
        store.create_order, idempotency_key=f"bm-off-{link_hash[:24]}", direction="offramp",
        profile_id=profile_id, status="confirmed", chain=settle, amount_usdc=str(amount), rate=str(q.get("rate") or ""),
        amount_ngn=str(q.get("payout_ngn") or ""), quote=q,
        details={"bank": bank, "bank_label": bank.get("label"), "out_address": out_w["address"]},
    )
    if not created:
        return WithdrawOutcome(True, "ok", _started_text(amount, q, bank), amount, settle,
                               transaction_id=order["id"])
    try:
        br = await asyncio.to_thread(
            cctp.start, idempotency_key=f"{order['id']}:out", kind="offramp_out", profile_id=profile_id,
            src_chain=settle, dst_chain=config.delivery_chain(), amount=amount, from_wallet_id=play["wallet_id"],
            mint_recipient=out_w["address"], fast=False,
        )
    except Exception:
        logger.exception("[paycrest] cash-out bridge did not start for %s", order["id"])
        await asyncio.to_thread(store.transition, order["id"], "failed", expect="confirmed", error="bridge_start")
        return WithdrawOutcome(False, "failed", "Cash-out failed before any money moved. Try again later.", amount)
    await asyncio.to_thread(store.transition, order["id"], "bridging_out", expect="confirmed", bridge_id=br["id"])
    commit_daily_withdraw(profile_id, amount)
    notices.alert_admins(f"Naira cash-out {order['id']} ${amount} → {bank.get('label')} started")
    return WithdrawOutcome(True, "ok", _started_text(amount, q, bank), amount, settle, transaction_id=order["id"])


def _started_text(amount: Decimal, q: dict, bank: dict) -> str:
    ngn = q.get("payout_ngn")
    about = f" (about ₦{Decimal(str(ngn)):,.0f})" if ngn else ""
    return (f"Cash-out started: ${amount:,.2f} USDC{about} to {bank.get('label')}. "
            "It usually lands in under 30 minutes; we'll message you when the bank is paid.")


def _out_wallet(profile_id: str) -> Optional[dict]:
    return store.get_wallet(profile_id, f"{config.delivery_chain()}/out")


def submit(order_id: str) -> None:
    """on_base → create the Paycrest order and send it the USDC (sync)."""
    from gaming.src.backend.services.bridge.chain_ops import get_chain_ops

    o = store.get_order(order_id)
    if not o or o["status"] != "on_base":
        return
    if not store.transition(order_id, "submitting", expect="on_base"):
        return
    n = int(o.get("attempts") or 0) + 1
    w = _out_wallet(o["profile_id"])
    ops = get_chain_ops()
    try:
        bal = ops.usdc_balance(config.delivery_chain(), w["address"]) if w else Decimal("0")
    except Exception:
        bal = Decimal("-1")
    if bal < MIN_SEND:
        # Not visible on Base yet (or RPC hiccup): try again shortly.
        store.transition(order_id, "on_base", expect="submitting", attempts=n,
                         next_attempt_at_ms=store.now_ms() + 30_000)
        if n >= 20:
            store.transition(order_id, "needs_review", expect="on_base", error="no_usdc_on_base")
            notices.alert_admins(f"Cash-out {order_id}: bridged USDC not visible on Base after {n} tries")
        return
    bank = (o.get("details") or {}).get("bank") or {}
    amount = bal.quantize(CENT, rounding=ROUND_DOWN)
    ref = f"{o['idempotency_key']}-{n}"
    client = get_client()

    def payload(amt: Decimal, reference: str) -> dict:
        p: dict[str, Any] = {
            "amount": str(amt), "amountIn": "crypto", "reference": reference,
            "transactionFeePayer": config.transaction_fee_payer(),
            "source": {"type": "crypto", "currency": config.token(), "network": config.network(),
                       "refundAddress": w["address"]},
            "destination": {"type": "fiat", "currency": config.currency(),
                            "recipient": {"institution": bank.get("institution"),
                                          "accountIdentifier": bank.get("account_identifier"),
                                          "accountName": bank.get("account_name"),
                                          "memo": "Boardman cash-out"}},
        }
        if config.sender_fee_percent() > 0:
            p["senderFeePercent"] = str(config.sender_fee_percent())
        return p

    try:
        pc = client.create_order(payload(amount, ref))
        need = pc.provider_account.amount_to_transfer if pc.provider_account else amount
        if need > bal:
            # Fees on top of the amount: shrink the order so the total fits.
            amount = (amount - (need - amount)).quantize(CENT, rounding=ROUND_DOWN)
            ref = f"{ref}b"
            if amount < MIN_SEND:
                raise PaycrestError("balance too small after fees", status_code=400)
            pc = client.create_order(payload(amount, ref))
            need = pc.provider_account.amount_to_transfer if pc.provider_account else amount
            if need > bal:
                store.transition(order_id, "needs_review", expect="submitting", error="fees_exceed_balance")
                notices.alert_admins(f"Cash-out {order_id}: Paycrest wants {need} but only {bal} on Base")
                return
    except AmbiguousSubmit:
        store.transition(order_id, "submit_unknown", expect="submitting", attempts=n,
                         details={"reference": ref}, next_attempt_at_ms=store.now_ms() + 60_000)
        return
    except PaycrestError as exc:
        if exc.retryable and n < config.bridge().max_attempts:
            store.transition(order_id, "on_base", expect="submitting", attempts=n, error=str(exc)[:200],
                             next_attempt_at_ms=store.now_ms() + 60_000 * n)
            return
        store.transition(order_id, "refunded_on_base", expect="submitting", attempts=n,
                         error=f"paycrest_refused:{str(exc)[:160]}")
        notices.tell(o["profile_id"], f"We couldn't pay {bank.get('label')} through Paycrest, so your "
                                      f"${Decimal(o['amount_usdc']):,.2f} is coming back to your play wallet.",
                     kind="withdrawal_update",
                     params={"amount": f"{Decimal(o['amount_usdc']):,.2f}", "destination": bank.get("label"),
                             "status": "returned"})
        refund_home(order_id)
        return
    send(order_id, pc, details={"reference": ref})


def send(order_id: str, pc: Any, *, details: Optional[dict] = None) -> None:
    """Fund the Paycrest order from the Base "out" wallet (idempotent per order)."""
    from gaming.src.backend.services.bridge.chain_ops import ChainOpsError, get_chain_ops

    o = store.get_order(order_id)
    if not o:
        return
    w = _out_wallet(o["profile_id"])
    pa = pc.provider_account
    if not w or not pa or not pa.receive_address:
        store.transition(order_id, "needs_review", expect=("submitting", "submit_unknown"), error="no_receive_address")
        notices.alert_admins(f"Cash-out {order_id}: Paycrest order {pc.id} has no receive address")
        return
    ops = get_chain_ops()
    try:
        if config.base_gas_mode() == "hot_wallet":
            ops.ensure_gas(config.delivery_chain(), w["address"])
        tx = ops.transfer_usdc(config.delivery_chain(), w["wallet_id"], pa.receive_address, pa.amount_to_transfer,
                               f"{order_id}|send|{pc.id}")
    except ChainOpsError as exc:
        # Not sent; the unfunded Paycrest order simply expires. Try a fresh one.
        store.transition(order_id, "on_base", expect=("submitting", "submit_unknown"), error=str(exc)[:200],
                         next_attempt_at_ms=store.now_ms() + 120_000)
        return
    payout = (pc.amount * pc.rate).quantize(Decimal("1"), rounding=ROUND_DOWN) if pc.rate > 0 else None
    store.transition(
        order_id, "awaiting_settlement", expect=("submitting", "submit_unknown"), paycrest_id=pc.id,
        paycrest_status=pc.status, provider_account=pa.to_json(),
        amount_ngn=str(payout) if payout is not None else o.get("amount_ngn"),
        details={**(details or {}), "transfer_tx_id": tx, "sent_usdc": str(pa.amount_to_transfer),
                 "transaction_fee": str(pc.transaction_fee)},
    )


def refund_home(order_id: str) -> None:
    """refunded_on_base → bridge the Base "out" wallet back to the play wallet."""
    from gaming.src.backend.services.bridge import cctp
    from gaming.src.backend.services.bridge.chain_ops import get_chain_ops

    o = store.get_order(order_id)
    if not o or o["status"] != "refunded_on_base":
        return
    w = _out_wallet(o["profile_id"])
    if not w:
        store.transition(order_id, "needs_review", expect="refunded_on_base", error="no_out_wallet")
        return
    bal = get_chain_ops().usdc_balance(config.delivery_chain(), w["address"])
    if bal < config.bridge().min_sweep_usdc:
        return  # refund not visible yet; the reconciler retries
    # A refund goes back to the wallet the cash-out came from: the play wallet
    # (passkey players cannot start a cash-out yet, see offramp.prepare).
    play = wallets.play_wallet_sync(o["profile_id"])
    b = config.bridge()
    br = cctp.start(idempotency_key=f"{order_id}:refund", kind="offramp_refund", profile_id=o["profile_id"],
                    src_chain=config.delivery_chain(), dst_chain=config.settlement_chain(), amount=bal,
                    from_wallet_id=w["wallet_id"], mint_recipient=play["address"], fast=b.onramp_fast_transfer,
                    max_fee_bps=b.max_fee_bps)
    store.transition(order_id, "refund_bridging", expect="refunded_on_base", bridge_id=br["id"])


def _orders_for_bridge(br: dict, status: str) -> list[dict]:
    return [o for o in store.list_orders(statuses=(status,), profile_id=br["profile_id"], direction="offramp")
            if o.get("bridge_id") == br["id"]]


def on_bridge_finished(br: dict) -> None:
    kind = br.get("kind")
    ok = br["status"] == "minted"
    if kind == "offramp_out":
        for o in _orders_for_bridge(br, "bridging_out"):
            if ok:
                if store.transition(o["id"], "on_base", expect="bridging_out"):
                    submit(o["id"])
            else:
                store.transition(o["id"], "needs_review", expect="bridging_out", error="bridge_failed")
                notices.alert_admins(f"Cash-out bridge {br['id']} FAILED for order {o['id']}: check whether the "
                                     "Arc burn happened before refunding by hand.")
                notices.tell(o["profile_id"], "Your cash-out is delayed. Your money is safe; support is on it.")
    elif kind == "offramp_refund":
        for o in _orders_for_bridge(br, "refund_bridging"):
            if ok:
                store.transition(o["id"], "refunded", expect="refund_bridging", settled_at_ms=store.now_ms())
                amt = Decimal(br.get("minted_usdc") or br["amount_usdc"])
                notices.tell(o["profile_id"], f"Your naira cash-out was returned: ${amt:,.2f} USDC is back in your "
                                              "play wallet.", kind="withdrawal_update",
                             params={"amount": f"{amt:,.2f}", "destination": "your play wallet",
                                     "status": "returned"})
            else:
                store.transition(o["id"], "needs_review", expect="refund_bridging", error="refund_bridge_failed")
                notices.alert_admins(f"Cash-out refund bridge {br['id']} FAILED for order {o['id']}")
