"""Real valuation → in-game price & wages."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from gaming.src.stack.agentic.games.football_managers.rules import (
    PRICE_DIVISOR,
    PRICE_MAX,
    PRICE_MIN,
    WAGE_FRACTION_OF_PRICE,
)


def game_price_from_real_value(real_value_usd: float | int | str) -> Decimal:
    """Map real transfer value to in-game USDC-denominated price."""
    v = Decimal(str(real_value_usd))
    if v < 0:
        v = Decimal("0")
    raw = v / Decimal(PRICE_DIVISOR)
    lo, hi = Decimal(str(PRICE_MIN)), Decimal(str(PRICE_MAX))
    p = max(lo, min(hi, raw))
    return p.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def wage_per_matchday(game_price: Decimal | float) -> Decimal:
    p = Decimal(str(game_price))
    w = p * Decimal(str(WAGE_FRACTION_OF_PRICE))
    return max(Decimal("0.01"), w.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
