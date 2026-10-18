"""The naira rail's reconciler: everything a webhook or a crash could miss.

Each pass (every 30 s in the API process when the rail is live, or by hand
with ``scripts/reconcile_paycrest.py``):

1. advance due CCTP transfers (``bridge.cctp.reconcile``) and flag stuck ones;
2. resolve ambiguous submits by looking the order up by our reference;
3. poll Paycrest for orders waiting on it (missed webhooks);
4. retry sweeps (settled on-ramps) and cash-out submits / refunds;
5. cancel quotes whose link expired.

Every step is idempotent; running two reconcilers at once is safe (all
writes are compare-and-set).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from gaming.src.backend.services.paycrest import config, events, notices, offramp, onramp, store
from gaming.src.backend.services.paycrest.client import get_client
from gaming.src.backend.services.paycrest.models import PaycrestError

logger = logging.getLogger(__name__)

POLL_AFTER_MS = 5 * 60 * 1000          # ask Paycrest if a webhook is this late
UNKNOWN_GIVE_UP_MS = 15 * 60 * 1000    # an ambiguous submit not found after this never happened
INTERVAL_SEC = 30.0


def poll_after_ms() -> int:
    """How stale an open order may get before we ask Paycrest ourselves.

    The Paycrest account is shared with BlinkBox, which owns its single webhook
    URL, so production runs Boardman on polling: set PAYCREST_POLL_AFTER_SEC
    (e.g. 20) and PAYCREST_RECONCILE_SEC (e.g. 15). With a webhook of our own,
    the 5-minute default only catches missed deliveries.
    """
    raw = os.environ.get("PAYCREST_POLL_AFTER_SEC", "").strip()
    try:
        return max(5, int(raw)) * 1000 if raw else POLL_AFTER_MS
    except ValueError:
        return POLL_AFTER_MS


def interval_sec() -> float:
    raw = os.environ.get("PAYCREST_RECONCILE_SEC", "").strip()
    try:
        return max(5.0, float(raw)) if raw else INTERVAL_SEC
    except ValueError:
        return INTERVAL_SEC

_alerted_stuck: set[str] = set()


def _due(o: dict, now: int) -> bool:
    return int(o.get("next_attempt_at_ms") or 0) <= now


def reconcile_once(*, now_ms: Optional[int] = None) -> dict[str, Any]:
    from gaming.src.backend.services.bridge import cctp

    now = now_ms if now_ms is not None else store.now_ms()
    out: dict[str, Any] = {}
    out.update(cctp.reconcile())
    for br in cctp.stuck(now_ms=now):
        if br["id"] not in _alerted_stuck:
            _alerted_stuck.add(br["id"])
            notices.alert_admins(f"CCTP transfer {br['id']} ({br['kind']}, ${br['amount_usdc']}) stuck in "
                                 f"{br['status']} for over 2 hours")
    client = get_client()

    # 2. ambiguous submits
    for o in store.list_orders(statuses=("submit_unknown",)):
        if not _due(o, now):
            continue
        ref = (o.get("details") or {}).get("reference") or o["idempotency_key"]
        try:
            pc = client.find_order_by_reference(ref)
        except PaycrestError:
            continue
        if pc is not None:
            if o["direction"] == "onramp":
                onramp._accepted(o, pc, {})
            else:
                offramp.send(o["id"], pc, details={"reference": ref})
            continue
        if now - int(o["updated_at_ms"]) > UNKNOWN_GIVE_UP_MS:
            if o["direction"] == "onramp":
                if store.transition(o["id"], "failed", expect="submit_unknown", error="submit_not_found"):
                    notices.tell(o["profile_id"], "We couldn't create your naira top-up with Paycrest. Nothing "
                                                  "was charged; please start a new one.")
            else:
                store.transition(o["id"], "on_base", expect="submit_unknown", next_attempt_at_ms=now)

    # 3. poll orders waiting on Paycrest
    waiting = store.list_orders(statuses=("awaiting_deposit", "processing", "awaiting_settlement", "refunding"))
    for o in waiting:
        if not o.get("paycrest_id") or now - int(o["updated_at_ms"]) < poll_after_ms():
            continue
        try:
            pc = client.get_order(o["paycrest_id"])
        except PaycrestError:
            continue
        if pc.status and pc.status != (o.get("paycrest_status") or ""):
            events.apply_status(o["id"], pc.status, pc.raw)
        else:
            store.update_order(o["id"], paycrest_status=pc.status)  # bumps updated_at: poll again later

    # 4. retries
    for pid in sorted({o["profile_id"] for o in store.list_orders(statuses=("settled",), direction="onramp")}):
        try:
            onramp.sweep(pid)
        except Exception:
            logger.exception("[paycrest] sweep retry failed")
    for o in store.list_orders(statuses=("on_base",), direction="offramp"):
        if _due(o, now):
            try:
                offramp.submit(o["id"])
            except Exception:
                logger.exception("[paycrest] cash-out submit retry failed")
    for o in store.list_orders(statuses=("refunded_on_base",), direction="offramp"):
        try:
            offramp.refund_home(o["id"])
        except Exception:
            logger.exception("[paycrest] refund retry failed")

    # 5. stale quotes
    for o in store.list_orders(statuses=("quoted",)):
        if o.get("expires_at_ms") and int(o["expires_at_ms"]) < now:
            store.transition(o["id"], "cancelled", expect="quoted", error="quote_expired")

    review = store.list_orders(statuses=("needs_review",), limit=50)
    out["needs_review"] = len(review)
    return out


async def _loop(interval: float) -> None:
    notices.set_loop(asyncio.get_running_loop())
    while True:
        await asyncio.sleep(interval)
        if not config.enabled():
            continue
        try:
            res = await asyncio.to_thread(reconcile_once)
            if res.get("needs_review"):
                logger.warning("[paycrest] %s orders need review", res["needs_review"])
        except Exception:
            logger.exception("[paycrest] reconcile pass failed")


def start_worker(interval: Optional[float] = None) -> Optional[asyncio.Task]:
    """Started from the API's startup hook; does nothing unless the rail is live."""
    if not config.enabled():
        return None
    return asyncio.get_running_loop().create_task(_loop(interval or interval_sec()))
