"""Unit tests for Naira/USD fiat top-up quotes and store."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

# Ensure repo root on path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("FIAT_NGN_PER_USD", "1650")
os.environ.setdefault("FIAT_FEE_FLOOR_USDC", "2")
os.environ.setdefault("FIAT_FEE_PCT", "0.05")
os.environ.setdefault("FIAT_MIN_NGN", "5000")
os.environ.setdefault("FIAT_MIN_USD", "5")
os.environ.setdefault("FIAT_MIN_CREDIT_USDC", "1")
os.environ["FIAT_TOPUP_STORE"] = str(
    Path(__file__).resolve().parent / "_tmp_fiat_topups_test.json"
)


from gaming.src.backend.services import fiat_topup as ft  # noqa: E402


def setup_function(_fn):
    p = Path(os.environ["FIAT_TOPUP_STORE"])
    if p.exists():
        p.unlink()


def teardown_function(_fn):
    p = Path(os.environ["FIAT_TOPUP_STORE"])
    if p.exists():
        p.unlink()


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
