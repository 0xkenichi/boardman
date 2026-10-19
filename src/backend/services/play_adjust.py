"""Play-wallet overlay so Telegram, website, and the book share one number.

display = on-chain USDC + adjust

adjust goes negative when we lock a bet/LP that has not left the Circle
address yet, and positive when we owe a payout that has not been sent back.

Every write is an atomic read-modify-write under the store's cross-process
file lock. Money moves that must happen exactly once (settlement payouts,
refunds, wallet-bridge transfers) go through ``apply_once`` with a key: the
key is recorded in the same write as the balance change, durably (not in the
80-entry display history), so a retry after a crash can always tell whether
the change already landed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Iterator, Optional

from gaming.src.stack.agentic.store import load_json, update_json

FILE = "play_adjust.json"


class InsufficientPlayBalance(ValueError):
    """A debit would take the play balance (chain + adjust) below zero."""


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def _fresh() -> dict[str, Any]:
    return {"profiles": {}, "applied": {}}


def get_adjust(profile_id: str) -> Decimal:
    pid = (profile_id or "").strip()
    if not pid:
        return Decimal("0")
    data = load_json(FILE, _fresh())
    rec = (data.get("profiles") or {}).get(pid) or {}
    try:
        return _q(Decimal(str(rec.get("adjust") or "0")))
    except Exception:
        return Decimal("0")


def _apply(data: dict[str, Any], pid: str, amt: Decimal, reason: str) -> Decimal:
    profiles = data.setdefault("profiles", {})
    rec = profiles.get(pid) or {"adjust": "0", "history": []}
    nxt = _q(Decimal(str(rec.get("adjust") or "0")) + amt)
    rec["adjust"] = str(nxt)
    hist = list(rec.get("history") or [])
    hist.append({"delta": str(amt), "reason": reason[:80]})
    rec["history"] = hist[-80:]
    profiles[pid] = rec
    return nxt


def add_adjust(profile_id: str, delta: Decimal | float | str, *, reason: str) -> Decimal:
    pid = (profile_id or "").strip()
    if not pid:
        return Decimal("0")
    amt = _q(Decimal(str(delta)))
    if amt == 0:
        return get_adjust(pid)
    out: dict[str, Decimal] = {}

    def _fn(data: dict[str, Any]) -> dict[str, Any]:
        out["v"] = _apply(data, pid, amt, reason)
        return data

    update_json(FILE, _fn, _fresh())
    return out["v"]


def apply_once(
    profile_id: str,
    delta: Decimal | str,
    *,
    key: str,
    chain_usdc: Optional[Decimal] = None,
) -> bool:
    """Apply ``delta`` exactly once per ``key``. True if applied now, False if
    the key had already been applied (nothing changes).

    A debit (negative delta) with ``chain_usdc`` given is refused with
    InsufficientPlayBalance when ``chain_usdc + adjust`` (the play balance the
    bot and the website show) would go below zero — checked under the same
    lock as the write.
    """
    pid = (profile_id or "").strip()
    k = (key or "").strip()
    if not pid or not k:
        raise ValueError("profile_id and key are required")
    amt = _q(Decimal(str(delta)))
    if amt == 0:
        raise ValueError("delta must be non-zero")
    out = {"applied": False}

    def _fn(data: dict[str, Any]) -> dict[str, Any]:
        applied = data.setdefault("applied", {})
        if k in applied:
            return data
        if amt < 0 and chain_usdc is not None:
            cur = Decimal(str(((data.get("profiles") or {}).get(pid) or {}).get("adjust") or "0"))
            have = _q(Decimal(str(chain_usdc)) + cur)
            if have + amt < 0:
                raise InsufficientPlayBalance(f"play balance is ${have}, need ${-amt}")
        _apply(data, pid, amt, k)
        applied[k] = {
            "profile_id": pid,
            "delta": str(amt),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        out["applied"] = True
        return data

    update_json(FILE, _fn, _fresh())
    return out["applied"]


class PlaySpendBusy(ValueError):
    """Another spend of this play balance is still going through."""


@contextmanager
def spend_lock(profile_id: str) -> Iterator[None]:
    """One spend of a play balance at a time — bets, LP, withdrawals and
    cash-outs alike, across requests, threads and processes. Each of them
    reads the chain, checks chain + overlay, then moves money; two of them
    interleaving can each pass the check and together overdraw."""
    from gaming.src.stack.agentic.db import leases

    pid = (profile_id or "").strip()
    cm = leases.exclusive(f"play-spend:{pid}")
    try:
        cm.__enter__()
    except leases.LeaseBusy as exc:
        raise PlaySpendBusy(
            "Another payment from this wallet is still going through. Try again in a moment."
        ) from exc
    try:
        yield
    finally:
        cm.__exit__(None, None, None)


def was_applied(profile_id: str, key: str) -> bool:
    """Has this keyed change landed? (Legacy rows: the display history.)"""
    pid = (profile_id or "").strip()
    data = load_json(FILE, _fresh())
    hit = (data.get("applied") or {}).get(key)
    if hit is not None:
        return str(hit.get("profile_id") or "") == pid
    rec = (data.get("profiles") or {}).get(pid) or {}
    return any(str(h.get("reason") or "") == key[:80] for h in rec.get("history") or [])
