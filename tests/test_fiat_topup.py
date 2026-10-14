"""Unit tests for Naira/USD fiat top-up quotes and store."""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.backend.services import fiat_topup as ft

# Pricing knobs these tests are written against. Pinned with setenv (the old
# os.environ.setdefault lost to FIAT_* values leaked from the real .env, which
# moved the rate to 1520 and broke two quotes). Schedule under test:
# fee = max($2 floor, 5% of gross), credit capped at $100 per top-up.
_KNOBS = {
    "FIAT_NGN_PER_USD": "1650",
    "FIAT_NGN_OFFRAMP_PER_USD": "1500",
    "FIAT_FEE_FLOOR_USDC": "2",
    "FIAT_FEE_PCT": "0.05",
    "FIAT_MIN_NGN": "5000",
    "FIAT_MAX_NGN": "200000",
    "FIAT_MIN_USD": "5",
    "FIAT_MAX_USD": "200",
    "FIAT_MIN_CREDIT_USDC": "1",
    "FIAT_MAX_CREDIT_USDC": "100",
}


@pytest.fixture(autouse=True)
def _pinned_pricing_and_store(tmp_path, monkeypatch):
    for k, v in _KNOBS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("REMATCH_FIAT_TOPUP_FILE", raising=False)
    # was tests/_tmp_fiat_topups_test.json inside the repo
    monkeypatch.setenv("FIAT_TOPUP_STORE", str(tmp_path / "fiat_topups.json"))


def test_parse_ngn():
    assert ft.parse_ngn_amount("10000") == Decimal("10000")
    assert ft.parse_ngn_amount("10,000") == Decimal("10000")
    assert ft.parse_ngn_amount("10k") == Decimal("10000")
    assert ft.parse_ngn_amount("₦15,000") == Decimal("15000")


def test_quote_min_naira_uses_floor_fee():
    q = ft.quote_from_ngn(Decimal("10000"))
    # 10000/1650 ≈ 6.06 → fee $2 floor → credit ~4.06
    assert q.fee_usd == Decimal("2.00")
    assert q.credit_usdc == Decimal("4.06")
    assert q.gross_usd == Decimal("6.06")


def test_quote_large_uses_pct():
    # 165000 / 1650 = 100; 5% = 5 > floor 2
    q = ft.quote_from_ngn(Decimal("165000"))
    assert q.gross_usd == Decimal("100.00")
    assert q.fee_usd == Decimal("5.00")
    assert q.credit_usdc == Decimal("95.00")


def test_quote_usd():
    q = ft.quote_from_usd(Decimal("20"))
    assert q.gross_usd == Decimal("20.00")
    assert q.fee_usd == Decimal("2.00")  # floor > 5% of 20
    assert q.credit_usdc == Decimal("18.00")


def test_below_min_raises():
    with pytest.raises(ValueError):
        ft.quote_from_ngn(Decimal("1000"))
    with pytest.raises(ValueError):
        ft.quote_from_usd(Decimal("2"))


def test_create_and_credit_flow():
    q = ft.quote_from_ngn(Decimal("10000"))
    top = ft.create_topup(
        profile_id="prof-1",
        telegram_id=12345,
        display_name="Tester",
        quote=q,
        play_address="0xabc",
        currency="ngn",
    )
    assert top.ref.startswith("RM-")
    row = ft.get_topup(top.ref)
    assert row is not None
    assert row["status"] == "awaiting_payment"
    updated = ft.update_topup(top.ref, status="proof_submitted", proof_text="TXN123")
    assert updated["status"] == "proof_submitted"
    credited = ft.update_topup(top.ref, status="credited")
    assert credited["status"] == "credited"
    pending = ft.list_topups(status="proof_submitted")
    assert all(r["ref"] != top.ref for r in pending)
