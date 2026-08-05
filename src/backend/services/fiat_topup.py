"""
Fiat (Naira) top-up → USDC credit quotes + pending top-up store.

Bootstrap model:
  User says how much ₦ they will send
  → commercial rate + floor fee → quote USDC they receive
  → user pays collection account + sends proof / txn id
  → ops credits play wallet manually (admin command)

Config via env (see .env.example). Storage defaults to a local JSON file so
no DB migration is required for the pilot.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import string
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Commercial knobs ─────────────────────────────────────────────────────────

def _d(name: str, default: str) -> Decimal:
    try:
        return Decimal(str(os.getenv(name, default)).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


# ₦ per $1 on-ramp (user pays Naira → gets USDC). Higher = we keep FX spread.
# Product default: 1520 (real cost ~1400).
NGN_PER_USD = _d("FIAT_NGN_PER_USD", "1520")
# ₦ per $1 off-ramp (user sells USDC → gets Naira). Lower than on-ramp = bid/ask.
NGN_OFFRAMP_PER_USD = _d("FIAT_NGN_OFFRAMP_PER_USD", "1500")
# Floor fee in USDC so Kobox ~1.5 send + margin is covered
FEE_FLOOR_USDC = _d("FIAT_FEE_FLOOR_USDC", "2")
# Optional % of gross USD (fee = max(floor, gross * pct))
FEE_PCT = _d("FIAT_FEE_PCT", "0.05")
MIN_NGN = _d("FIAT_MIN_NGN", "5000")  # ~$3 credit at default rate after $2 fee
MAX_NGN = _d("FIAT_MAX_NGN", "200000")
MIN_CREDIT_USDC = _d("FIAT_MIN_CREDIT_USDC", "1")
MAX_CREDIT_USDC = _d("FIAT_MAX_CREDIT_USDC", "100")

_STORE_LOCK = threading.Lock()


def _store_path() -> Path:
    raw = (
        os.getenv("FIAT_TOPUP_STORE")
        or os.getenv("REMATCH_FIAT_TOPUP_FILE")
        or ""
    ).strip()
    if raw:
        return Path(os.path.expanduser(raw))
    # Prefer repo data/ when present; else ~/.rematch/
    here = Path(__file__).resolve()
    for root in (here.parents[3], here.parents[2], Path.cwd()):
        data = root / "data"
        if data.is_dir() or (root / ".env").is_file():
            data.mkdir(parents=True, exist_ok=True)
            return data / "fiat_topups.json"
    path = Path(os.path.expanduser("~/.rematch/fiat_topups.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def bank_details_ngn() -> dict[str, str]:
    """Collection account for Naira transfers (fill via env)."""
    return {
        "bank_name": (os.getenv("FIAT_NGN_BANK_NAME") or "").strip(),
        "account_name": (os.getenv("FIAT_NGN_ACCOUNT_NAME") or "").strip(),
        "account_number": (os.getenv("FIAT_NGN_ACCOUNT_NUMBER") or "").strip(),
        "extra": (os.getenv("FIAT_NGN_BANK_NOTE") or "").strip(),
    }


def bank_details_usd() -> dict[str, str]:
    """US bank / ACH collection (Lead etc.) for dollar wires."""
    return {
        "bank_name": (os.getenv("FIAT_USD_BANK_NAME") or "").strip(),
        "account_name": (os.getenv("FIAT_USD_ACCOUNT_NAME") or "").strip(),
        "account_number": (os.getenv("FIAT_USD_ACCOUNT_NUMBER") or "").strip(),
        "account_type": (os.getenv("FIAT_USD_ACCOUNT_TYPE") or "Checking").strip(),
        "ach_routing": (os.getenv("FIAT_USD_ACH_ROUTING") or "").strip(),
        "wire_routing": (os.getenv("FIAT_USD_WIRE_ROUTING") or "").strip(),
        "bank_address": (os.getenv("FIAT_USD_BANK_ADDRESS") or "").strip(),
        "extra": (os.getenv("FIAT_USD_BANK_NOTE") or "").strip(),
    }


def bank_configured(currency: str = "ngn") -> bool:
    c = (currency or "ngn").lower()
    if c == "usd":
        d = bank_details_usd()
        return bool(d["account_number"] and (d["ach_routing"] or d["wire_routing"]))
    d = bank_details_ngn()
    return bool(d["account_number"] and d["account_name"])


def commercial_rate() -> Decimal:
    """On-ramp: ₦ per $1 user pays (reload each call so ops can update without restart)."""
    return _d("FIAT_NGN_PER_USD", "1520")


def offramp_rate() -> Decimal:
    """Off-ramp: ₦ per $1 we pay user when they cash out to bank."""
    return _d("FIAT_NGN_OFFRAMP_PER_USD", "1500")


def fee_floor() -> Decimal:
    return _d("FIAT_FEE_FLOOR_USDC", "2")


def fee_pct() -> Decimal:
    return _d("FIAT_FEE_PCT", "0.05")


def quote_offramp_ngn(amount_usdc: Decimal) -> dict:
    """User sells USDC → Naira to their linked bank (ops pays out).

    We apply the same style fee floor in USDC space first, then convert
    remaining USDC at the off-ramp rate.
    """
    if amount_usdc <= 0:
        raise ValueError("Amount must be greater than zero")
    floor = fee_floor()
    pct = fee_pct()
    pct_fee = (amount_usdc * pct).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    fee = max(floor, pct_fee)
    net = (amount_usdc - fee).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if net <= 0:
        raise ValueError(f"After ${fee} fee nothing left to cash out. Send more.")
    rate = offramp_rate()
    ngn = (net * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return {
        "amount_usdc": float(amount_usdc),
        "fee_usdc": float(fee),
        "net_usdc": float(net),
        "rate_ngn_per_usd": float(rate),
        "payout_ngn": float(ngn),
        "fee_note": f"${fee} fee, then ₦{rate:,.0f}/$ off-ramp rate",
    }


@dataclass
class TopupQuote:
    amount_ngn: Decimal
    rate_ngn_per_usd: Decimal
    gross_usd: Decimal
    fee_usd: Decimal
    credit_usdc: Decimal
    fee_note: str

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "amount_ngn": float(self.amount_ngn),
            "rate_ngn_per_usd": float(self.rate_ngn_per_usd),
            "gross_usd": float(self.gross_usd),
            "fee_usd": float(self.fee_usd),
            "credit_usdc": float(self.credit_usdc),
            "fee_note": self.fee_note,
        }


def parse_ngn_amount(raw: str) -> Decimal:
    """Accept 10000, 10,000, 10k, ₦10000, etc."""
    s = (raw or "").strip().lower().replace(",", "").replace(" ", "")
    s = s.replace("₦", "").replace("ngn", "").replace("naira", "")
    if s.endswith("k") and len(s) > 1:
        s = s[:-1]
        mult = Decimal("1000")
    else:
        mult = Decimal("1")
    if not s or not all(c.isdigit() or c == "." for c in s):
        raise ValueError("Enter a Naira amount, e.g. 10000 or 10,000")
    amt = (Decimal(s) * mult).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if amt <= 0:
        raise ValueError("Amount must be greater than zero")
    return amt


def quote_from_ngn(amount_ngn: Decimal) -> TopupQuote:
    """Convert ₦ user will send → USDC they receive after commercial fee."""
    min_n = _d("FIAT_MIN_NGN", str(MIN_NGN))
    max_n = _d("FIAT_MAX_NGN", str(MAX_NGN))
    if amount_ngn < min_n:
        raise ValueError(f"Minimum top-up is ₦{min_n:,.0f}")
    if amount_ngn > max_n:
        raise ValueError(f"Maximum top-up is ₦{max_n:,.0f} for now")

    rate = commercial_rate()
    if rate <= 0:
        raise ValueError("Rate not configured")

    gross = (amount_ngn / rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    floor = fee_floor()
    pct = fee_pct()
    pct_fee = (gross * pct).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    fee = max(floor, pct_fee)
    credit = (gross - fee).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    min_c = _d("FIAT_MIN_CREDIT_USDC", str(MIN_CREDIT_USDC))
    max_c = _d("FIAT_MAX_CREDIT_USDC", str(MAX_CREDIT_USDC))
    if credit < min_c:
        raise ValueError(
            f"After fees you'd get ${credit} — below minimum ${min_c}. "
            f"Send more Naira (min roughly ₦{(min_c + floor) * rate:,.0f})."
        )
    if credit > max_c:
        raise ValueError(
            f"After fees credit would be ${credit} — max ${max_c} per top-up for now."
        )

    if pct_fee > floor:
        fee_note = f"${fee} fee ({float(pct) * 100:.0f}% of gross)"
    else:
        fee_note = f"${fee} flat fee (covers conversion + send)"

    return TopupQuote(
        amount_ngn=amount_ngn,
        rate_ngn_per_usd=rate,
        gross_usd=gross,
        fee_usd=fee,
        credit_usdc=credit,
        fee_note=fee_note,
    )


def _new_ref() -> str:
    alphabet = string.ascii_uppercase + string.digits
    # Avoid ambiguous chars
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    code = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"RM-{code}"


@dataclass
class FiatTopup:
    ref: str
    profile_id: str
    telegram_id: int
    display_name: str
    amount_ngn: float
    rate_ngn_per_usd: float
    gross_usd: float
    fee_usd: float
    credit_usdc: float
    currency: str = "ngn"  # ngn | usd
    amount_fiat: float = 0.0  # ₦ or $ sent by user
    status: str = "awaiting_payment"  # awaiting_payment | proof_submitted | credited | rejected | cancelled
    proof_text: str = ""
    proof_file_id: str = ""
    usdc_tx: str = ""
    admin_note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    play_address: str = ""

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


def _load_all() -> list[dict]:
    path = _store_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("topups"), list):
            return data["topups"]
    except Exception:
        logger.exception("[FiatTopup] failed to read %s", path)
    return []


def _save_all(rows: list[dict]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def create_topup(
    *,
    profile_id: str,
    telegram_id: int,
    display_name: str,
    quote: TopupQuote,
    play_address: str = "",
    currency: str = "ngn",
    amount_fiat: Optional[Decimal] = None,
) -> FiatTopup:
    cur = (currency or "ngn").lower()
    with _STORE_LOCK:
        rows = _load_all()
        # unique ref
        for _ in range(20):
            ref = _new_ref()
            if not any(r.get("ref") == ref for r in rows):
                break
        else:
            raise RuntimeError("Could not allocate top-up reference")

        fiat_amt = float(amount_fiat) if amount_fiat is not None else (
            float(quote.gross_usd) if cur == "usd" else float(quote.amount_ngn)
        )
        top = FiatTopup(
            ref=ref,
            profile_id=profile_id,
            telegram_id=int(telegram_id),
            display_name=display_name or "",
            amount_ngn=float(quote.amount_ngn),
            rate_ngn_per_usd=float(quote.rate_ngn_per_usd),
            gross_usd=float(quote.gross_usd),
            fee_usd=float(quote.fee_usd),
            credit_usdc=float(quote.credit_usdc),
            currency=cur,
            amount_fiat=fiat_amt,
            play_address=play_address or "",
        )
        rows.append(asdict(top))
        _save_all(rows)
        return top


def get_topup(ref: str) -> Optional[dict]:
    key = (ref or "").strip().upper()
    if not key.startswith("RM-"):
        key = f"RM-{key}" if key else key
    with _STORE_LOCK:
        for row in _load_all():
            if str(row.get("ref", "")).upper() == key:
                return row
    return None


def update_topup(ref: str, **fields: Any) -> Optional[dict]:
    key = (ref or "").strip().upper()
    if key and not key.startswith("RM-"):
        key = f"RM-{key}"
    with _STORE_LOCK:
        rows = _load_all()
        for i, row in enumerate(rows):
            if str(row.get("ref", "")).upper() != key:
                continue
            row = dict(row)
            for k, v in fields.items():
                if v is not None:
                    row[k] = v
            row["updated_at"] = datetime.now(timezone.utc).isoformat()
            rows[i] = row
            _save_all(rows)
            return row
    return None


def list_topups(
    *,
    status: Optional[str] = None,
    telegram_id: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    with _STORE_LOCK:
        rows = list(_load_all())
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    out: list[dict] = []
    for row in rows:
        if status and row.get("status") != status:
            continue
        if telegram_id is not None and int(row.get("telegram_id") or 0) != int(telegram_id):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def format_bank_block(currency: str = "ngn") -> str:
    c = (currency or "ngn").lower()
    if c == "usd":
        d = bank_details_usd()
        if not bank_configured("usd"):
            return (
                "⚠️ USD bank details not configured yet.\n"
                "Set <code>FIAT_USD_ACCOUNT_NUMBER</code> + routing in the bot env."
            )
        lines = [
            f"<b>Bank:</b> {_esc(d['bank_name']) or '—'}",
            f"<b>Account number:</b> <code>{_esc(d['account_number'])}</code>",
            f"<b>Account type:</b> {_esc(d['account_type']) or 'Checking'}",
        ]
        if d.get("account_name"):
            lines.insert(1, f"<b>Account name:</b> {_esc(d['account_name'])}")
        if d.get("ach_routing"):
            lines.append(f"<b>ACH routing:</b> <code>{_esc(d['ach_routing'])}</code>")
        if d.get("wire_routing"):
            lines.append(f"<b>Wire routing:</b> <code>{_esc(d['wire_routing'])}</code>")
        if d.get("bank_address"):
            lines.append(f"<b>Bank address:</b> {_esc(d['bank_address'])}")
        if d.get("extra"):
            lines.append(f"<i>{_esc(d['extra'])}</i>")
        return "\n".join(lines)

    d = bank_details_ngn()
    if not bank_configured("ngn"):
        return (
            "⚠️ Bank details not configured yet.\n"
            "Set <code>FIAT_NGN_BANK_NAME</code>, <code>FIAT_NGN_ACCOUNT_NAME</code>, "
            "<code>FIAT_NGN_ACCOUNT_NUMBER</code> in the bot env."
        )
    lines = [
        f"<b>Bank:</b> {_esc(d['bank_name']) or '—'}",
        f"<b>Account name:</b> {_esc(d['account_name'])}",
        f"<b>Account number:</b> <code>{_esc(d['account_number'])}</code>",
    ]
    if d["extra"]:
        lines.append(f"<i>{_esc(d['extra'])}</i>")
    return "\n".join(lines)


def quote_from_usd(amount_usd: Decimal) -> TopupQuote:
    """USD bank transfer: fee taken in USDC space; rate field is 1."""
    min_u = _d("FIAT_MIN_USD", "5")
    max_u = _d("FIAT_MAX_USD", "200")
    if amount_usd < min_u:
        raise ValueError(f"Minimum top-up is ${min_u:,.2f}")
    if amount_usd > max_u:
        raise ValueError(f"Maximum top-up is ${max_u:,.2f} for now")

    gross = amount_usd.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    floor = fee_floor()
    pct = fee_pct()
    pct_fee = (gross * pct).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    fee = max(floor, pct_fee)
    credit = (gross - fee).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    min_c = _d("FIAT_MIN_CREDIT_USDC", str(MIN_CREDIT_USDC))
    max_c = _d("FIAT_MAX_CREDIT_USDC", str(MAX_CREDIT_USDC))
    if credit < min_c:
        raise ValueError(
            f"After fees you'd get ${credit} — below minimum ${min_c}. "
            f"Send at least roughly ${min_c + floor:,.2f}."
        )
    if credit > max_c:
        raise ValueError(
            f"After fees credit would be ${credit} — max ${max_c} per top-up for now."
        )

    if pct_fee > floor:
        fee_note = f"${fee} fee ({float(pct) * 100:.0f}% of amount)"
    else:
        fee_note = f"${fee} flat fee (covers conversion + send)"

    return TopupQuote(
        amount_ngn=Decimal("0"),  # unused for USD path
        rate_ngn_per_usd=Decimal("1"),
        gross_usd=gross,
        fee_usd=fee,
        credit_usdc=credit,
        fee_note=fee_note,
    )


def parse_usd_amount(raw: str) -> Decimal:
    s = (raw or "").strip().lower().replace(",", "").replace(" ", "")
    s = s.replace("$", "").replace("usd", "").replace("usdc", "")
    if not s or not all(c.isdigit() or c == "." for c in s):
        raise ValueError("Enter a USD amount, e.g. 20 or 20.00")
    amt = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if amt <= 0:
        raise ValueError("Amount must be greater than zero")
    return amt


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_quote_html(
    quote: TopupQuote,
    ref: str | None = None,
    currency: str = "ngn",
) -> str:
    cur = (currency or "ngn").lower()
    if cur == "usd":
        lines = [
            f"You send: <b>${quote.gross_usd:,.2f} USD</b>",
            f"Fee: <b>${quote.fee_usd:,.2f}</b> <i>({_esc(quote.fee_note)})</i>",
            f"You get: <b>${quote.credit_usdc:,.2f} USDC</b> in your play wallet",
        ]
    else:
        lines = [
            f"You send: <b>₦{quote.amount_ngn:,.0f}</b>",
            f"Rate: <b>₦{quote.rate_ngn_per_usd:,.0f}</b> per $1",
            f"Before fee: <b>${quote.gross_usd:,.2f}</b>",
            f"Fee: <b>${quote.fee_usd:,.2f}</b> <i>({_esc(quote.fee_note)})</i>",
            f"You get: <b>${quote.credit_usdc:,.2f} USDC</b> in your play wallet",
        ]
    if ref:
        lines.append(f"Reference: <code>{_esc(ref)}</code>")
        lines.append("Put this ref in the transfer narration if you can.")
    return "\n".join(lines)
