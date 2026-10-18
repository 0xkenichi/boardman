"""Rate quotes shown to the player before anything is confirmed.

Paycrest's own fee (about 0.5%) is already inside its rate. On top of that a
player can see up to three costs, all listed in the quote:

* Paycrest's network ``transactionFee``: exact only once the order exists,
  so the chat says it will be shown on the payment page / taken from the
  payout, and the order record keeps the real number;
* Boardman's ``sender_fee_percent`` (0 today);
* the CCTP bridge fee: Fast Transfer Base → Arc is capped at
  ``bridge.max_fee_bps`` (standard transfers are free), and Arc gas for the
  cash-out burn (paid in USDC, cents).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from gaming.src.backend.services.paycrest import config
from gaming.src.backend.services.paycrest.client import get_client

CENT = Decimal("0.01")
GUESS_NGN_PER_USD = Decimal("1500")  # only sizes the rate request; never shown


def _q(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_DOWN)


@dataclass
class OnrampQuote:
    amount_ngn: Decimal
    rate: Decimal              # NGN per USDC
    usdc_gross: Decimal        # what the naira buys at the rate
    sender_fee_usdc: Decimal
    bridge_fee_max_usdc: Decimal
    receive_usdc: Decimal      # lower bound before Paycrest's network fee
    provider_ids: list
    quoted_at_ms: int

    def to_json(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}

    def text(self) -> str:
        lines = [
            f"You pay ₦{self.amount_ngn:,.0f} by bank transfer.",
            f"Rate: ₦{self.rate:,.2f} per $1 (Paycrest's 0.5% fee is in the rate).",
        ]
        if self.sender_fee_usdc > 0:
            lines.append(f"Boardman fee: ${self.sender_fee_usdc:,.2f}.")
        lines.append(f"Bridge to your play wallet: up to ${self.bridge_fee_max_usdc:,.2f}.")
        lines.append(f"You get about *${self.receive_usdc:,.2f} USDC*, less Paycrest's small network fee, "
                     "shown before you pay.")
        return "\n".join(lines)


@dataclass
class OfframpQuote:
    amount_usdc: Decimal
    rate: Decimal
    sender_fee_usdc: Decimal
    payout_ngn: Decimal        # before Paycrest's network fee
    quoted_at_ms: int

    def to_json(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}

    def text(self) -> str:
        lines = [
            f"You cash out ${self.amount_usdc:,.2f} USDC.",
            f"Rate: ₦{self.rate:,.2f} per $1 (Paycrest's 0.5% fee is in the rate).",
        ]
        if self.sender_fee_usdc > 0:
            lines.append(f"Boardman fee: ${self.sender_fee_usdc:,.2f}.")
        lines.append(f"Your bank gets about *₦{self.payout_ngn:,.0f}*, less Paycrest's small network fee "
                     "and a few cents of network gas.")
        return "\n".join(lines)


def quote_onramp(amount_ngn: Decimal, *, now_ms: int) -> OnrampQuote:
    guess = max(Decimal("1"), _q(amount_ngn / GUESS_NGN_PER_USD))
    rq = get_client().get_rate(guess, side="buy")
    gross = _q(amount_ngn / rq.rate)
    fee = _q(gross * config.sender_fee_percent() / Decimal(100))
    b = config.bridge()
    bridge_max = (gross * b.max_fee_bps / Decimal(10_000)).quantize(CENT) if b.onramp_fast_transfer else Decimal("0")
    return OnrampQuote(amount_ngn, rq.rate, gross, fee, bridge_max, max(Decimal("0"), gross - fee - bridge_max),
                       rq.provider_ids, now_ms)


def quote_offramp(amount_usdc: Decimal, *, now_ms: int) -> OfframpQuote:
    rq = get_client().get_rate(amount_usdc, side="sell")
    fee = _q(amount_usdc * config.sender_fee_percent() / Decimal(100))
    payout = ((amount_usdc - fee) * rq.rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return OfframpQuote(amount_usdc, rq.rate, fee, payout, now_ms)
