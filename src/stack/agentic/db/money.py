"""Exact USDC amounts: integer micro-USDC in storage, Decimal at the edges.

Never float. Inputs with more than 6 decimals are rounded half-even to the
micro unit — symmetric for a debit and its matching credit, so a transfer
never creates or destroys a micro.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

MICRO_PER_USDC = 1_000_000
_MICRO = Decimal(MICRO_PER_USDC)
_ONE = Decimal(1)


def to_micro(amount: Any) -> int:
    """Decimal/str/int USDC -> int micro-USDC (a float goes through its repr)."""
    if isinstance(amount, bool):
        raise TypeError("bool is not an amount")
    if isinstance(amount, float):
        # Floats are how money drifted before; go through str() so the value
        # a caller *printed* is the value booked, but never accept binary noise.
        amount = repr(amount)
    try:
        d = amount if isinstance(amount, Decimal) else Decimal(str(amount).strip() or "0")
    except InvalidOperation as exc:
        raise ValueError(f"not a USDC amount: {amount!r}") from exc
    if not d.is_finite():
        raise ValueError(f"not a finite USDC amount: {amount!r}")
    return int((d * _MICRO).quantize(_ONE, rounding=ROUND_HALF_EVEN))


def from_micro(micro: Any) -> Decimal:
    """int micro -> Decimal USDC with the smallest exact exponent ('58.6', '50')."""
    return Decimal(int(micro or 0)) / _MICRO


def fmt(micro: Any) -> str:
    return str(from_micro(micro))


MAX_PLACES = 6


def places(amount: Any) -> int:
    """Decimal places an amount was written with (0..6), e.g. '30.00' -> 2.

    Legacy balances were Decimal strings whose sums kept the widest operand's
    places ('0' + '30.00' -> '30.00'); the ledger tracks that display scale so
    API strings read exactly as before.
    """
    try:
        d = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return 0
    exp = d.as_tuple().exponent
    if not isinstance(exp, int) or exp >= 0:
        return 0
    return min(MAX_PLACES, -exp)


def fmt_places(micro: Any, n: int) -> str:
    """Format micro-USDC with at least ``n`` decimal places (exact either way)."""
    d = from_micro(micro)
    n = max(0, min(MAX_PLACES, int(n or 0)))
    if n and places(d) < n:
        d = d.quantize(Decimal(1).scaleb(-n))
    return str(d)
