"""Play-wallet overlay so Telegram, website, and the book share one number.

display = on-chain USDC + adjust

adjust goes negative when we lock a bet/LP that has not left the Circle
address yet, and positive when we owe a payout that has not been sent back.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Any

from gaming.src.stack.agentic.store import load_json, save_json

FILE = "play_adjust.json"


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def get_adjust(profile_id: str) -> Decimal:
    pid = (profile_id or "").strip()
    if not pid:
        return Decimal("0")
    data = load_json(FILE, {"profiles": {}})
    rec = (data.get("profiles") or {}).get(pid) or {}
    try:
        return _q(Decimal(str(rec.get("adjust") or "0")))
    except Exception:
        return Decimal("0")


def add_adjust(profile_id: str, delta: Decimal | float | str, *, reason: str) -> Decimal:
    pid = (profile_id or "").strip()
    if not pid:
        return Decimal("0")
    amt = _q(Decimal(str(delta)))
    if amt == 0:
        return get_adjust(pid)
    data = load_json(FILE, {"profiles": {}})
    rec = data.setdefault("profiles", {}).get(pid) or {
        "adjust": "0",
        "history": [],
    }
    nxt = _q(Decimal(str(rec.get("adjust") or "0")) + amt)
    rec["adjust"] = str(nxt)
    hist = list(rec.get("history") or [])
    hist.append({"delta": str(amt), "reason": reason[:80]})
    rec["history"] = hist[-80:]
    data["profiles"][pid] = rec
    save_json(FILE, data)
    return nxt
