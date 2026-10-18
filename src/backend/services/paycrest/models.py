"""Paycrest Sender API v2 shapes, as Boardman uses them.

Field names follow https://docs.paycrest.io/openapi-v2.yaml (checked
2026-10-18). Only what we send or read is modelled; unknown response fields
are kept in ``raw``. Personal data (KYC, bank details) never appears in
``repr`` or logs: see ``KycPerson.masked`` / ``BankAccount.masked``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

# ── Paycrest order statuses (V2) ─────────────────────────────────────────────
# initiated → deposited → pending → fulfilling → (fulfilled) → validated →
# settling → settled; failures: expired, refunding → refunded, cancelled.
PAYCREST_STATUSES = (
    "initiated", "deposited", "pending", "fulfilling", "fulfilled", "validated",
    "settling", "settled", "cancelled", "refunding", "refunded", "expired",
)
IN_FLIGHT = frozenset({"deposited", "pending", "fulfilling", "fulfilled", "validated", "settling"})

# Webhook events: payment_order.<status> plus compliance_hold (not a status:
# data.status stays "pending" while a deposit from a third-party account is
# reviewed; it ends settled or refunded).
WEBHOOK_EVENTS = frozenset({
    "payment_order.deposited", "payment_order.pending", "payment_order.validated",
    "payment_order.settling", "payment_order.settled", "payment_order.refunding",
    "payment_order.refunded", "payment_order.expired", "payment_order.compliance_hold",
})


class PaycrestError(Exception):
    """A Paycrest call failed. ``retryable`` means nothing was created."""

    def __init__(self, message: str, *, status_code: int = 0, retryable: bool = False,
                 field_errors: Optional[list] = None, kind: str = "error") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.field_errors = field_errors or []
        self.kind = kind


class KycRejected(PaycrestError):
    """Paycrest refused the customer KYC (400 on field ``Source``)."""


class AmbiguousSubmit(PaycrestError):
    """The create-order request may or may not have reached Paycrest."""


def money(raw: Any, default: str = "0") -> Decimal:
    try:
        d = Decimal(str(raw if raw not in (None, "") else default))
    except (InvalidOperation, ValueError):
        d = Decimal(default)
    return d if d.is_finite() else Decimal(default)


# ── inputs ──────────────────────────────────────────────────────────────────

_ACCOUNT_RE = re.compile(r"^\d{10}$")          # NUBAN
_ID_RE = re.compile(r"^\d{11}$")               # BVN and NIN are both 11 digits
_INSTITUTION_RE = re.compile(r"^[A-Z0-9]{4,16}$")


@dataclass(frozen=True)
class BankAccount:
    institution: str          # Paycrest institution code, e.g. GTBINGLA
    account_identifier: str   # 10-digit NUBAN
    account_name: str = ""
    institution_name: str = ""

    def validate(self) -> Optional[str]:
        if not _INSTITUTION_RE.match(self.institution or ""):
            return "Pick your bank from the list."
        if not _ACCOUNT_RE.match(self.account_identifier or ""):
            return "Nigerian account numbers are 10 digits."
        return None

    def to_api(self) -> dict[str, str]:
        return {
            "institution": self.institution,
            "accountIdentifier": self.account_identifier,
            "accountName": self.account_name,
        }

    @property
    def masked(self) -> str:
        tail = self.account_identifier[-4:] if self.account_identifier else "????"
        bank = self.institution_name or self.institution
        return f"{bank} ••••{tail}"

    def __repr__(self) -> str:  # never print the full account number
        return f"BankAccount({self.masked})"


@dataclass(frozen=True)
class KycPerson:
    """Customer KYC for an on-ramp order. Pass-through: never persisted."""

    full_name: str
    birth_date: str           # YYYY-MM-DD
    id_type: str              # BVN | nationalID (NIN)
    id_number: str
    email: str = ""
    phone_e164: str = ""

    def validate(self, *, allowed_types: tuple[str, ...] = ("BVN", "nationalID"),
                 today: Optional[date] = None) -> Optional[str]:
        name = " ".join((self.full_name or "").split())
        if len(name) < 3 or len(name.split()) < 2:
            return "Enter your full name as it appears at your bank."
        try:
            born = date.fromisoformat(self.birth_date)
        except (TypeError, ValueError):
            return "Enter your date of birth as YYYY-MM-DD."
        today = today or date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < 18:
            return "You must be 18 or older."
        if age > 120:
            return "Check your date of birth."
        if self.id_type not in allowed_types:
            return "Choose BVN or NIN."
        if not _ID_RE.match(self.id_number or ""):
            return "BVN and NIN are 11 digits."
        if self.phone_e164 and not re.match(r"^\+\d{8,15}$", self.phone_e164):
            return "Phone must look like +2348012345678."
        return None

    def to_api(self) -> dict[str, Any]:
        person: dict[str, Any] = {
            "fullName": " ".join(self.full_name.split()),
            "birthDate": self.birth_date,
            "nationality": "NG",
            "idDocument": {"type": self.id_type, "number": self.id_number, "issuerCountry": "NG"},
        }
        contact = {k: v for k, v in (("email", self.email), ("phoneE164", self.phone_e164)) if v}
        if contact:
            person["contact"] = contact
        return {"entityType": "person", "personDetails": person}

    @property
    def masked(self) -> str:
        return f"{self.id_type} •••••••{(self.id_number or '')[-4:]}"

    def __repr__(self) -> str:
        return f"KycPerson({self.masked})"


# ── outputs ─────────────────────────────────────────────────────────────────


@dataclass
class RateQuote:
    network: str
    token: str
    currency: str
    side: str                 # buy (on-ramp) | sell (off-ramp)
    rate: Decimal             # NGN per 1 USDC
    provider_ids: list[str] = field(default_factory=list)
    order_type: str = ""
    refund_timeout_minutes: Optional[int] = None


@dataclass
class Institution:
    code: str
    name: str
    type: str = ""


@dataclass
class ProviderAccount:
    """Where the payer sends money: a virtual bank account (on-ramp) or a
    crypto receive address (off-ramp)."""

    amount_to_transfer: Decimal
    currency: str
    valid_until: str = ""
    # on-ramp (fiat in)
    institution: str = ""
    account_identifier: str = ""
    account_name: str = ""
    # off-ramp (crypto in)
    network: str = ""
    receive_address: str = ""
    memo: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "ProviderAccount":
        d = d or {}
        return cls(
            amount_to_transfer=money(d.get("amountToTransfer")),
            currency=str(d.get("currency") or ""),
            valid_until=str(d.get("validUntil") or ""),
            institution=str(d.get("institution") or ""),
            account_identifier=str(d.get("accountIdentifier") or ""),
            account_name=str(d.get("accountName") or ""),
            network=str(d.get("network") or ""),
            receive_address=str(d.get("receiveAddress") or ""),
            memo=str(d.get("memo") or ""),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "amount_to_transfer": str(self.amount_to_transfer), "currency": self.currency,
            "valid_until": self.valid_until, "institution": self.institution,
            "account_identifier": self.account_identifier, "account_name": self.account_name,
            "network": self.network, "receive_address": self.receive_address, "memo": self.memo,
        }


@dataclass
class PaycrestOrder:
    id: str
    status: str
    amount: Decimal = Decimal("0")
    rate: Decimal = Decimal("0")
    sender_fee: Decimal = Decimal("0")
    transaction_fee: Decimal = Decimal("0")
    reference: str = ""
    tx_hash: str = ""
    direction: str = ""
    status_detail: str = ""
    refund_reason: str = ""
    amount_paid: Decimal = Decimal("0")
    provider_account: Optional[ProviderAccount] = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, d: dict) -> "PaycrestOrder":
        d = d or {}
        pa = d.get("providerAccount")
        return cls(
            id=str(d.get("id") or ""),
            status=str(d.get("status") or "").lower(),
            amount=money(d.get("amount")),
            rate=money(d.get("rate")),
            sender_fee=money(d.get("senderFee")),
            transaction_fee=money(d.get("transactionFee") or d.get("networkFee")),
            reference=str(d.get("reference") or ""),
            tx_hash=str(d.get("txHash") or ""),
            direction=str(d.get("direction") or ""),
            status_detail=str(d.get("statusDetail") or ""),
            refund_reason=str(d.get("refundReason") or ""),
            amount_paid=money(d.get("amountPaid")),
            provider_account=ProviderAccount.from_api(pa) if isinstance(pa, dict) else None,
            raw=d,
        )
