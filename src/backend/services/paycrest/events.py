"""Apply Paycrest order updates (webhook or poll) to our orders.

Webhooks are at least once and can arrive out of order or be replayed:
* the raw body hash is the dedupe key (``paycrest_webhook_events``);
* every move goes through the order state machine, which never goes
  backwards, so a late ``pending`` after ``settled`` does nothing.
The same ``apply_status`` serves the reconciler's polling, so a missed
webhook is caught by ``GET /sender/orders/{id}``.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
from decimal import Decimal
from typing import Any, Callable, Optional

from gaming.src.backend.services.paycrest import notices, store
from gaming.src.backend.services.paycrest.models import IN_FLIGHT, WEBHOOK_EVENTS

logger = logging.getLogger(__name__)


def event_key(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body or b"").hexdigest()


# Slow follow-ups (chain calls) after a status change. The webhook route sets
# a deferrer so Paycrest gets its 2xx at once; elsewhere they run inline.
_deferrer: contextvars.ContextVar[Optional[Callable[..., None]]] = contextvars.ContextVar(
    "paycrest_deferrer", default=None)


def _run_followup(fn: Callable[..., Any], *args: Any) -> None:
    try:
        fn(*args)
    except Exception:
        logger.exception("[paycrest] follow-up %s failed; the reconciler retries", getattr(fn, "__name__", fn))


def _followup(fn: Callable[..., Any], *args: Any) -> None:
    defer = _deferrer.get()
    if defer is not None:
        defer(_run_followup, fn, *args)
    else:
        _run_followup(fn, *args)


def _find(data: dict) -> Optional[dict]:
    pid = str(data.get("id") or "")
    o = store.get_order_by_paycrest_id(pid) if pid else None
    if o is None and data.get("reference"):
        # The webhook can beat our own write after an ambiguous submit.
        ref = str(data["reference"])
        o = store.get_order_by_key(ref)
        if o is None and "-" in ref:  # cash-out references carry an attempt suffix
            o = store.get_order_by_key(ref.rsplit("-", 1)[0])
    return o


def handle_webhook(raw_body: bytes, *, defer: Optional[Callable[..., None]] = None) -> dict[str, Any]:
    """Signature already verified. Returns a small outcome for logs/tests.

    ``defer(fn, *args)`` schedules slow follow-ups after the response."""
    token = _deferrer.set(defer)
    try:
        return _handle(raw_body)
    finally:
        _deferrer.reset(token)


def _handle(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body or b"{}")
    except ValueError:
        return {"ok": False, "outcome": "bad_json"}
    event = str(payload.get("event") or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if event not in WEBHOOK_EVENTS:
        return {"ok": True, "outcome": "ignored_event"}
    key = event_key(raw_body)
    if not store.record_event(key, paycrest_id=str(data.get("id") or ""), event=event,
                              status=str(data.get("status") or "")):
        return {"ok": True, "outcome": "duplicate"}
    try:
        return _apply_event(key, event, data)
    except Exception:
        # Nothing of it may count as seen: the retry (same body) must run.
        store.forget_event(key)
        raise


def _apply_event(key: str, event: str, data: dict) -> dict[str, Any]:
    order = _find(data)
    if order is None:
        logger.warning("[paycrest] webhook for unknown order event=%s", event)
        store.set_event_outcome(key, "unknown_order")
        return {"ok": True, "outcome": "unknown_order"}
    if not order.get("paycrest_id") and data.get("id"):
        store.update_order(order["id"], paycrest_id=str(data["id"]))
    if event == "payment_order.compliance_hold":
        outcome = _hold(order, data)
    else:
        outcome = apply_status(order["id"], str(data.get("status") or event.split(".", 1)[1]), data)
    store.set_event_outcome(key, outcome)
    return {"ok": True, "outcome": outcome}


def _hold(order: dict, data: dict) -> str:
    store.update_order(order["id"], details={"hold": True, "status_detail": str(data.get("statusDetail") or "")})
    store.transition(order["id"], "processing")
    if order["direction"] == "onramp":
        notices.tell(order["profile_id"], "Your naira payment is under review because it may have come from an "
                                          "account that isn't in your name. If so it will be sent back to that "
                                          "account. Nothing else for you to do.")
    return "hold"


def apply_status(order_id: str, pc_status: str, data: Optional[dict] = None) -> str:
    data = data or {}
    o = store.get_order(order_id)
    if o is None:
        return "unknown_order"
    st = pc_status.lower()
    # Echo Paycrest's status only AFTER the transition it implies went
    # through: the poller skips orders whose echo already matches, so an
    # echo written before a failed transition left the order stuck forever.
    outcome = _onramp(o, st, data) if o["direction"] == "onramp" else _offramp(o, st, data)
    store.update_order(order_id, paycrest_status=st)
    return outcome


def _onramp(o: dict, st: str, data: dict) -> str:
    from gaming.src.backend.services.paycrest import onramp

    oid, pid = o["id"], o["profile_id"]
    if st in IN_FLIGHT:
        return "processing" if store.transition(oid, "processing") else "noop"
    if st == "settled":
        if store.transition(oid, "settled", details={"tx_hash": str(data.get("txHash") or "")}):
            _followup(onramp.sweep, pid)
            return "settled"
        return "noop"
    if st == "refunding":
        return "refunding" if store.transition(oid, "refunding") else "noop"
    if st == "refunded":
        if store.transition(oid, "refunded", error=str(data.get("refundReason") or "") or None):
            reason = str(data.get("refundReason") or "")
            why = (" because it came from an account that isn't in your name" if reason == "payer_mismatch"
                   else " because the payer couldn't be verified" if reason == "payer_unverified" else "")
            notices.tell(pid, f"Your naira payment was sent back to your bank{why}. No USDC was added.")
            return "refunded"
        return "noop"
    if st == "expired":
        if store.transition(oid, "expired"):
            notices.tell(pid, "Your naira top-up expired because no payment arrived in time. Start a new one "
                              "if you still want to top up; don't pay the old account.")
            return "expired"
        return "noop"
    if st == "cancelled":
        return "cancelled" if store.transition(oid, "cancelled") else "noop"
    return "noop"


def _offramp(o: dict, st: str, data: dict) -> str:
    from gaming.src.backend.services.paycrest import offramp

    oid, pid = o["id"], o["profile_id"]
    label = (o.get("details") or {}).get("bank_label") or "your bank"
    amt = f"{Decimal(o.get('amount_usdc') or '0'):,.2f}"
    if st in IN_FLIGHT:
        return "processing" if store.transition(oid, "processing") else "noop"
    if st == "settled":
        if store.transition(oid, "completed", settled_at_ms=store.now_ms(),
                            details={"tx_hash": str(data.get("txHash") or "")}):
            ngn = o.get("amount_ngn")
            paid = f"₦{Decimal(ngn):,.0f}" if ngn else "Your naira"
            notices.tell(pid, f"{paid} has been paid to {label}. Cash-out done.", kind="withdrawal_update",
                         params={"amount": amt, "destination": label, "status": "paid"})
            return "completed"
        return "noop"
    if st == "refunding":
        return "refunding" if store.transition(oid, "refunding") else "noop"
    if st == "refunded":
        if store.transition(oid, "refunded_on_base", error=str(data.get("refundReason") or "") or None):
            notices.tell(pid, f"Paycrest couldn't pay {label}. Your ${amt} is coming back to your play wallet.",
                         kind="withdrawal_update",
                         params={"amount": amt, "destination": label, "status": "returned"})
            _followup(offramp.refund_home, oid)
            return "refunded_on_base"
        return "noop"
    if st in ("expired", "cancelled"):
        # We fund cash-out orders right after creating them, so this means the
        # USDC may be stuck at Paycrest or on its way back: a human checks.
        if store.transition(oid, "needs_review", error=f"paycrest_{st}"):
            notices.alert_admins(f"Cash-out {oid} ({o.get('paycrest_id')}) went {st} at Paycrest after funding")
            return "needs_review"
        return "noop"
    return "noop"


def bridge_finished(br: dict) -> None:
    from gaming.src.backend.services.paycrest import offramp, onramp

    if br.get("kind") == "onramp_sweep":
        onramp.on_bridge_finished(br)
    elif br.get("kind") in ("offramp_out", "offramp_refund"):
        offramp.on_bridge_finished(br)
