"""CCTP v2 transfers between Base and Arc, one recorded leg at a time.

A transfer row (``bridge_transfers``) walks:

  pending → approve_submitted → burn_submitted → burned → attested →
  mint_submitted → minted        (or failed after ``max_attempts``)

``advance(id)`` does at most one step and is safe to call from anywhere, any
number of times: every chain call uses an idempotency key derived from the
transfer and the attempt, and every status write is compare-and-set, so two
workers cannot double-submit. ``reconcile()`` advances everything that is due
and is what the worker loop and ``scripts/reconcile_paycrest.py`` run.

* Burn: the player's own wallet on the source chain (Base: gas sponsored by
  Circle Gas Station on SCA wallets, or ETH from the Boardman gas tank;
  Arc: gas is USDC from the same wallet).
* Mint: a Boardman relayer wallet on the destination chain calls
  ``receiveMessage`` (destinationCaller is zero, so anyone may), because a
  fresh destination wallet has no gas yet.
* Fast Transfer (Base → Arc only; Arc has no Fast Transfer as a source) when
  Circle's quoted fee is at or below ``bridge.max_fee_bps``; otherwise the
  standard (finalized, slower) transfer.
"""
from __future__ import annotations

import logging
from decimal import ROUND_UP, Decimal
from typing import Callable, Optional

from gaming.src.backend.services.bridge.chain_ops import ChainOpsError, get_chain_ops
from gaming.src.backend.services.paycrest import store

logger = logging.getLogger(__name__)

# Backoff between attempts of one leg, and between attestation polls.
RETRY_MS = (15_000, 30_000, 60_000, 120_000, 300_000, 600_000, 1_800_000)
ATTEST_POLL_MS = 10_000

_listeners: list[Callable[[dict], None]] = []


def on_finished(fn: Callable[[dict], None]) -> None:
    """Register an extra callback for minted/failed transfers."""
    if fn not in _listeners:
        _listeners.append(fn)


def _emit(row: dict) -> None:
    """A transfer reached minted or failed: tell the order layer."""
    from gaming.src.backend.services.paycrest import events

    for fn in [events.bridge_finished, *_listeners]:
        try:
            fn(row)
        except Exception:
            logger.exception("[cctp] finish listener failed bridge=%s", row.get("id"))


def _backoff(attempts: int) -> int:
    return RETRY_MS[min(attempts, len(RETRY_MS) - 1)]


def start(*, idempotency_key: str, kind: str, profile_id: str, src_chain: str, dst_chain: str,
          amount: Decimal, from_wallet_id: str, mint_recipient: str, fast: bool = False,
          max_fee_bps: Decimal = Decimal("0")) -> dict:
    """Record a transfer (once per key) and try its first leg."""
    ops = get_chain_ops()
    use_fast = False
    max_fee = Decimal("0")
    if fast and not src_chain.startswith("arc"):
        bps = ops.fast_fee_bps(src_chain, dst_chain)
        if bps is not None and bps <= max_fee_bps:
            use_fast = True
            # Pay at most the cap (the burn reverts if Circle's fee is higher).
            max_fee = (amount * max_fee_bps / Decimal(10_000)).quantize(Decimal("0.000001"), rounding=ROUND_UP)
    row, _created = store.create_bridge(
        idempotency_key=idempotency_key, kind=kind, profile_id=profile_id, src_chain=src_chain,
        dst_chain=dst_chain, amount_usdc=str(amount), from_wallet_id=from_wallet_id,
        mint_recipient=mint_recipient, fast=use_fast, max_fee_usdc=str(max_fee),
    )
    return advance(row["id"]) or row


def _fail_or_retry(row: dict, err: str, *, back_to: Optional[str] = None) -> None:
    from gaming.src.backend.services.paycrest import config

    attempts = int(row.get("attempts") or 0) + 1
    if attempts >= config.bridge().max_attempts:
        store.update_bridge(row["id"], expect=row["status"], status="failed", attempts=attempts, error=err[:500])
        logger.error("[cctp] transfer %s failed for good: %s", row["id"], err)
        _emit(store.get_bridge(row["id"]) or row)
        return
    fields = {"attempts": attempts, "error": err[:500], "next_attempt_at_ms": store.now_ms() + _backoff(attempts)}
    if back_to:
        fields["status"] = back_to
    store.update_bridge(row["id"], expect=row["status"], **fields)
    logger.warning("[cctp] transfer %s step %s retry %s: %s", row["id"], row["status"], attempts, err)


def advance(bridge_id: str) -> Optional[dict]:
    """Do the next step of one transfer. Returns the row after the step."""
    from gaming.src.backend.services.chains import cctp_domain
    from gaming.src.backend.services.paycrest import config

    row = store.get_bridge(bridge_id)
    if row is None or row["status"] in ("minted", "failed"):
        return row
    ops = get_chain_ops()
    st = row["status"]
    key = row["idempotency_key"]
    n = int(row.get("attempts") or 0)
    amount = Decimal(row["amount_usdc"])
    try:
        if st == "pending":
            if row["src_chain"].startswith("base") and config.base_gas_mode() == "hot_wallet":
                ops.ensure_gas(row["src_chain"], _wallet_address(row))
            tx = ops.approve_burn(row["src_chain"], row["from_wallet_id"], amount, f"{key}|approve|{n}")
            store.update_bridge(bridge_id, expect=st, status="approve_submitted", approve_tx_id=tx, error=None)
        elif st == "approve_submitted":
            state, _h = ops.tx_status(row["src_chain"], row["approve_tx_id"])
            if state == "pending":
                store.update_bridge(bridge_id, expect=st, next_attempt_at_ms=store.now_ms() + ATTEST_POLL_MS)
            elif state == "failed":
                _fail_or_retry(row, "approve failed on chain", back_to="pending")
            else:
                tx = ops.burn(row["src_chain"], row["from_wallet_id"], amount, cctp_domain(row["dst_chain"]),
                              row["mint_recipient"], Decimal(row.get("max_fee_usdc") or "0"),
                              bool(row["fast"]), f"{key}|burn|{n}")
                store.update_bridge(bridge_id, expect=st, status="burn_submitted", burn_tx_id=tx, error=None)
        elif st == "burn_submitted":
            state, tx_hash = ops.tx_status(row["src_chain"], row["burn_tx_id"])
            if state == "pending":
                store.update_bridge(bridge_id, expect=st, next_attempt_at_ms=store.now_ms() + ATTEST_POLL_MS)
            elif state == "failed":
                # The allowance is still there: just burn again.
                _fail_or_retry(row, "burn failed on chain", back_to="approve_submitted")
            else:
                store.update_bridge(bridge_id, expect=st, status="burned", burn_tx_hash=tx_hash, error=None)
        elif st == "burned":
            m = ops.fetch_message(row["src_chain"], row["burn_tx_hash"])
            if m.get("status") != "complete":
                store.update_bridge(bridge_id, expect=st, next_attempt_at_ms=store.now_ms() + ATTEST_POLL_MS)
            else:
                store.update_bridge(bridge_id, expect=st, status="attested", message=m["message"],
                                    attestation=m["attestation"])
        elif st == "attested":
            relayer = config.relayer_wallet_id(row["dst_chain"])
            if not relayer:
                raise ChainOpsError(f"no relayer wallet configured for {row['dst_chain']}")
            tx = ops.mint(row["dst_chain"], relayer, row["message"], row["attestation"], f"{key}|mint|{n}")
            store.update_bridge(bridge_id, expect=st, status="mint_submitted", mint_tx_id=tx, error=None)
        elif st == "mint_submitted":
            state, tx_hash = ops.tx_status(row["dst_chain"], row["mint_tx_id"])
            if state == "pending":
                store.update_bridge(bridge_id, expect=st, next_attempt_at_ms=store.now_ms() + ATTEST_POLL_MS)
            elif state == "failed":
                # A mint can fail because someone else already relayed the
                # message (nonce used): the reconciler escalates after retries.
                _fail_or_retry(row, "mint failed on chain", back_to="attested")
            else:
                # Lower bound: Circle charges its quoted fee, never above maxFee.
                fee = Decimal(row.get("max_fee_usdc") or "0")
                store.update_bridge(bridge_id, expect=st, status="minted", mint_tx_hash=tx_hash,
                                    minted_usdc=str(amount - fee), error=None)
                done = store.get_bridge(bridge_id)
                if done:
                    _emit(done)
    except ChainOpsError as exc:
        _fail_or_retry(row, str(exc))
    except Exception as exc:  # network, provider bugs: retry later, never crash the worker
        logger.exception("[cctp] step %s crashed for %s", st, bridge_id)
        _fail_or_retry(row, f"{type(exc).__name__}")
    return store.get_bridge(bridge_id)


def _wallet_address(row: dict) -> str:
    w = store.wallet_by_id(row["from_wallet_id"])
    if w:
        return w["address"]
    raise ChainOpsError("source wallet address unknown")


STUCK_AFTER_MS = 2 * 3600 * 1000


def stuck(*, now_ms: Optional[int] = None) -> list[dict]:
    """Open transfers older than two hours: a human should look."""
    now = now_ms if now_ms is not None else store.now_ms()
    return [r for r in store.list_bridges(statuses=store.BRIDGE_OPEN, limit=500)
            if now - int(r["created_at_ms"]) > STUCK_AFTER_MS]


def reconcile(*, limit: int = 100, max_steps: int = 8) -> dict:
    """Advance every open transfer that is due. Returns counts for logs."""
    now = store.now_ms()
    seen = 0
    for row in store.list_bridges(statuses=store.BRIDGE_OPEN, due_before_ms=now, limit=limit):
        seen += 1
        for _ in range(max_steps):
            before = store.get_bridge(row["id"])
            after = advance(row["id"])
            if after is None or before is None:
                break
            if after["status"] == before["status"] or after["status"] in ("minted", "failed"):
                break
            if int(after.get("next_attempt_at_ms") or 0) > store.now_ms():
                break
    return {"bridges_checked": seen}
