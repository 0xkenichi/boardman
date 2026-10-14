"""Per-signer nonce manager and on-chain tx outcomes.

Problem it fixes: ``_send`` used ``get_transaction_count(addr)`` (the *latest*
block), so two tables signing with the same key at once picked the same nonce
and one tx was dropped; and a 180s receipt timeout recorded a *failure* for a
tx that could still mine.

How it works:

* A process lock per (chain, signer) serializes reserve -> sign -> broadcast
  inside one process; a row lock on ``signer_locks`` (Postgres ``FOR UPDATE``,
  SQLite's write lock) does the same across processes for the reservation.
* The nonce is the lowest one >= the chain's *pending* count that no recent
  in-flight reservation of ours holds. Reservations are rows in
  ``onchain_txs`` (status reserved -> sent -> confirmed | reverted |
  pending_confirmation, or released if the broadcast never happened), so a
  lagging RPC node cannot hand out a nonce we already used, and a released
  nonce is reused instead of leaving a gap.
* The tx hash is recorded *before* waiting for the receipt. A receipt
  timeout marks the row ``pending_confirmation`` and raises
  ``TxPendingConfirmation`` — never a failure. ``reconcile_pending`` settles
  those rows later from their receipts.
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

from gaming.src.stack.agentic.db.engine import now_ms, transaction

logger = logging.getLogger(__name__)

IN_FLIGHT = ("reserved", "sent", "pending_confirmation")
# A reservation/send older than this no longer blocks its nonce (crashed
# process or dropped tx) — the chain's pending count is the truth again.
DEFAULT_STALE_SEC = 900
DEFAULT_RECEIPT_TIMEOUT_SEC = 180


class TxPendingConfirmation(RuntimeError):
    """The tx was broadcast but no receipt arrived in time. It may still mine.

    Callers must not treat this as a failure (and must not refund/retry
    blindly); the row is ``pending_confirmation`` until reconciled.
    """

    def __init__(self, label: str, tx_hash: str) -> None:
        super().__init__(f"{label} tx {tx_hash} sent but unconfirmed — pending confirmation")
        self.label = label
        self.tx_hash = tx_hash


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stale_ms() -> int:
    try:
        return int(float(os.getenv("BOARDMAN_NONCE_STALE_SEC") or DEFAULT_STALE_SEC) * 1000)
    except ValueError:
        return DEFAULT_STALE_SEC * 1000


def receipt_timeout_sec() -> float:
    try:
        return float(os.getenv("BOARDMAN_RECEIPT_TIMEOUT_SEC") or DEFAULT_RECEIPT_TIMEOUT_SEC)
    except ValueError:
        return float(DEFAULT_RECEIPT_TIMEOUT_SEC)


_plocks: dict[tuple[str, str], threading.Lock] = {}
_plocks_guard = threading.Lock()


def _process_lock(chain_key: str, signer: str) -> threading.Lock:
    with _plocks_guard:
        k = (chain_key, signer)
        lk = _plocks.get(k)
        if lk is None:
            lk = _plocks[k] = threading.Lock()
        return lk


@dataclass
class Slot:
    row_id: int
    chain_key: str
    signer: str
    nonce: int
    label: str
    tx_hash: str = ""
    state: str = "reserved"

    def signed(self, tx_hash: str) -> None:
        self.tx_hash = tx_hash
        _update(self.row_id, tx_hash=tx_hash)

    def sent(self) -> None:
        self.state = "sent"
        _update(self.row_id, status="sent", tx_hash=self.tx_hash or None)

    def release(self, error: str) -> None:
        """The broadcast did not happen: free the nonce for reuse."""
        self.state = "released"
        _update(self.row_id, status="released", error=error[:500])


def _update(row_id: int, **fields: Any) -> None:
    fields["updated_at_ms"] = now_ms()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with transaction() as tx:
        tx.execute(f"UPDATE onchain_txs SET {cols} WHERE id = ?", (*fields.values(), row_id))


def _reserve(chain_key: str, signer: str, label: str, pending_count: int) -> Slot:
    now = now_ms()
    with transaction() as tx:
        # Serialize reservations for this signer across processes.
        tx.execute(
            "INSERT INTO signer_locks (chain_key, signer, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (chain_key, signer) DO NOTHING",
            (chain_key, signer, _now()),
        )
        tx.one(
            f"SELECT signer FROM signer_locks WHERE chain_key = ? AND signer = ?{tx.for_update}",
            (chain_key, signer),
        )
        marks = ",".join("?" for _ in IN_FLIGHT)
        rows = tx.all(
            f"SELECT nonce FROM onchain_txs WHERE chain_key = ? AND signer = ? AND nonce >= ? "
            f"AND status IN ({marks}) AND updated_at_ms > ?",
            (chain_key, signer, int(pending_count), *IN_FLIGHT, now - stale_ms()),
        )
        taken = {int(r["nonce"]) for r in rows}
        nonce = int(pending_count)
        while nonce in taken:
            nonce += 1
        row_id = tx.scalar(
            "INSERT INTO onchain_txs (chain_key, signer, nonce, label, status, tx_hash, "
            "created_at, updated_at_ms) VALUES (?, ?, ?, ?, 'reserved', NULL, ?, ?) RETURNING id",
            (chain_key, signer, nonce, label, _now(), now),
        )
    return Slot(int(row_id), chain_key, signer, nonce, label)


@contextmanager
def reserve(
    chain_key: str, signer: str, label: str, pending_count: Callable[[], int]
) -> Iterator[Slot]:
    """Reserve the next nonce for ``signer``; hold it through broadcast.

    The body must call ``slot.signed(hash)`` then ``slot.sent()`` once the
    node accepted the tx. Leaving the block any other way releases the nonce.
    """
    signer = signer.lower()
    with _process_lock(chain_key, signer):
        slot = _reserve(chain_key, signer, label, pending_count())
        try:
            yield slot
        except BaseException as exc:
            if slot.state == "reserved":
                slot.release(f"{type(exc).__name__}: {exc}")
            raise
        if slot.state == "reserved":
            slot.release("broadcast not confirmed by caller")


def mark(tx_hash: str, status: str, *, block_number: Optional[int] = None, error: str = "") -> None:
    fields: dict[str, Any] = {"status": status, "updated_at_ms": now_ms()}
    if block_number is not None:
        fields["block_number"] = int(block_number)
    if error:
        fields["error"] = error[:500]
    cols = ", ".join(f"{k} = ?" for k in fields)
    with transaction() as tx:
        tx.execute(f"UPDATE onchain_txs SET {cols} WHERE tx_hash = ?", (*fields.values(), tx_hash))


def get(tx_hash: str) -> Optional[dict[str, Any]]:
    with transaction(readonly=True) as tx:
        return tx.one("SELECT * FROM onchain_txs WHERE tx_hash = ?", (tx_hash,))


def pending(limit: int = 200) -> list[dict[str, Any]]:
    with transaction(readonly=True) as tx:
        return tx.all(
            "SELECT * FROM onchain_txs WHERE status = 'pending_confirmation' ORDER BY id LIMIT ?",
            (int(limit),),
        )


def reconcile_pending(get_receipt: Callable[[str, str], Optional[dict[str, Any]]]) -> dict[str, int]:
    """Settle ``pending_confirmation`` rows from their receipts.

    ``get_receipt(chain_key, tx_hash)`` returns ``{"status": 0|1,
    "blockNumber": n}`` or None while still unknown. Unknown rows older than
    the stale window become ``dropped`` (their nonce is then reusable).
    """
    out = {"confirmed": 0, "reverted": 0, "dropped": 0, "still_pending": 0}
    cutoff = now_ms() - stale_ms()
    for row in pending():
        h = str(row.get("tx_hash") or "")
        if not h:
            continue
        try:
            rcpt = get_receipt(str(row["chain_key"]), h)
        except Exception:
            logger.warning("[nonces] receipt lookup failed for %s", h, exc_info=True)
            rcpt = None
        if rcpt is None:
            if int(row.get("updated_at_ms") or 0) < cutoff:
                mark(h, "dropped", error="no receipt within stale window")
                out["dropped"] += 1
            else:
                out["still_pending"] += 1
            continue
        if int(rcpt.get("status") or 0) == 1:
            mark(h, "confirmed", block_number=rcpt.get("blockNumber"))
            out["confirmed"] += 1
        else:
            mark(h, "reverted", block_number=rcpt.get("blockNumber"), error="reverted")
            out["reverted"] += 1
    return out
