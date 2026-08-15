"""
gaming/tests/test_deposit_webhook.py — Tests for the ClawStation Circle deposit flow.

Covers:
    - Circle webhook signature verification (HMAC-SHA256).
    - Inbound USDC transfer credits ``wallet_balance_usdc`` exactly once.
    - Duplicate webhook delivery returns 200 but does not double-credit.
    - ``GET /api/deposit/address`` is idempotent for the same user.
"""
from __future__ import annotations

import hmac
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gaming.src.backend.main import app  # noqa: E402

_TEST_USER_ID = str(uuid.uuid4())
_TEST_WALLET_ID = "wallet_" + _TEST_USER_ID.replace("-", "")
_TEST_ADDRESS = "0x" + "a" * 40
_TEST_TX_HASH = "0x" + "b" * 64
_TEST_SECRET = "test-circle-webhook-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CIRCLE_WEBHOOK_SECRET", _TEST_SECRET)
    # Force the Supabase credit path; the asyncpg path needs a real Postgres DSN.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(app)


def _make_body(payload: dict) -> bytes:
    # The endpoint verifies the HMAC over ``request.body()`` — the exact bytes
    # sent. Post raw ``content=`` so the test controls those bytes precisely
    # (TestClient's ``json=`` re-serializes with spaces, which breaks the HMAC).
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _make_signature(body: bytes) -> str:
    digest = hmac.new(_TEST_SECRET.encode("utf-8"), body, "sha256").hexdigest()
    return f"v1={digest}"


def _make_transfer_payload(
    *,
    tx_hash: str = _TEST_TX_HASH,
    amount: str = "5000000",  # 5 USDC in wei units
    address: str = _TEST_ADDRESS,
    status: str = "CONFIRMED",
) -> dict:
    return {
        "type": "transfer",
        "data": {
            "walletId": _TEST_WALLET_ID,
            "transaction": {
                "txHash": tx_hash,
                "status": status,
                "amount": [
                    {
                        "amount": amount,
                        "token": {"symbol": "USDC", "decimals": 6},
                    }
                ],
                "destinationAddress": address,
            },
        },
    }


class _AwaitableClient(MagicMock):
    """Supabase client mock that is also await-able.

    Some producers use ``await get_supabase()`` (async wrapper) while others
    call it synchronously; a plain MagicMock breaks the ``await`` path.
    """

    def __await__(self):
        async def _inner():
            return self

        return _inner().__await__()


@pytest.fixture
def _mock_services(monkeypatch):
    """Mock Supabase and Circle so tests never hit real infrastructure."""
    _audit: list[dict] = []
    _balances: dict[str, Decimal] = {}
    _profiles: dict[str, dict] = {
        _TEST_USER_ID: {
            "id": _TEST_USER_ID,
            "gaming_deposit_address": _TEST_ADDRESS,
            "circle_wallet_id": _TEST_WALLET_ID,
        }
    }

    def _get_supabase():
        sb = _AwaitableClient()

        def _table(name: str):
            tbl = MagicMock()
            chain = tbl

            def _select(columns: str):
                chain.select_columns = columns
                return chain

            def _eq(col: str, val):
                chain.eq_col = col
                chain.eq_val = val
                return chain

            def _ilike(col: str, val: str):
                if name == "profiles" and col == "gaming_deposit_address":
                    for profile in _profiles.values():
                        if profile.get("gaming_deposit_address", "").lower() == val.lower():
                            chain.found_profile = profile
                            break
                return chain

            def _maybe_single():
                if name == "profiles" and getattr(chain, "eq_col", None) == "id":
                    return MagicMock(execute=lambda: MagicMock(data=_profiles.get(chain.eq_val)))
                if name == "profiles" and hasattr(chain, "found_profile"):
                    return MagicMock(execute=lambda: MagicMock(data=chain.found_profile))
                if name == "wallet_credit_audit" and getattr(chain, "eq_col", None) == "tx_hash":
                    return MagicMock(execute=lambda: _execute())
                return MagicMock(execute=lambda: MagicMock(data=None))

            def _order(col: str, desc: bool = False):
                return chain

            def _limit(n: int):
                return chain

            def _execute():
                eq_col = getattr(chain, "eq_col", None)
                eq_val = getattr(chain, "eq_val", None)
                if name == "wallet_credit_audit":
                    if eq_col == "user_id" and eq_val is not None:
                        items = [
                            r
                            for r in _audit
                            if str(r["user_id"]) == str(eq_val)
                        ]
                        return MagicMock(data=items)
                    if eq_col == "tx_hash" and eq_val is not None:
                        for r in _audit:
                            if r["tx_hash"] == eq_val:
                                return MagicMock(data={"id": r["id"]})
                        return MagicMock(data=None)
                if name == "profiles" and eq_col == "id" and eq_val is not None:
                    profile = _profiles.get(eq_val)
                    return MagicMock(data=[profile] if profile else None)
                return MagicMock(data=None)

            def _insert(data: dict):
                # Only credit-audit inserts are under test; notification-failure
                # rows (missing telegram chat id) must not pollute _audit.
                if name == "wallet_credit_audit":
                    data["id"] = str(uuid.uuid4())
                    _audit.append(data)
                return MagicMock(execute=lambda: MagicMock(data=[data]))

            def _update(data: dict):
                return MagicMock(execute=lambda: MagicMock(data=[]))

            chain.select = _select
            chain.eq = _eq
            chain.ilike = _ilike
            chain.maybe_single = _maybe_single
            chain.order = _order
            chain.limit = _limit
            chain.execute = _execute
            chain.insert = _insert
            chain.update = _update
            return chain

        def _rpc(name: str, params: dict):
            if name == "credit_wallet":
                uid = params.get("p_user_id")
                amount = params.get("p_amount")
                _balances[uid] = _balances.get(uid, Decimal("0")) + Decimal(str(amount))
            return MagicMock(execute=lambda: MagicMock(data=None))

        sb.table = _table
        sb.rpc = _rpc
        return sb

    monkeypatch.setattr("backend.supabase_client.get_supabase", _get_supabase)

    def _create_wallet(self, profile_id: str, phone_number=None):
        _profiles.setdefault(profile_id, {"id": profile_id})
        _profiles[profile_id]["gaming_deposit_address"] = _TEST_ADDRESS
        _profiles[profile_id]["circle_wallet_id"] = _TEST_WALLET_ID
        return {
            "success": True,
            "wallet_id": _TEST_WALLET_ID,
            "wallet_address": _TEST_ADDRESS,
            "blockchain": "BASE-SEPOLIA",
        }

    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_circle.CircleWalletService.create_custodial_wallet_for_user",
        _create_wallet,
    )

    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_circle.CircleWalletService.get_wallet_balance",
        lambda self, addr: {"success": True, "balance_usdc": 0.0},
    )

    yield {"audit": _audit, "balances": _balances, "profiles": _profiles}


class TestCircleWebhook:
    def test_webhook_credits_once(self, client, _mock_services, monkeypatch):
        payload = _make_transfer_payload()
        body = _make_body(payload)
        signature = _make_signature(body)

        resp = client.post(
            "/webhooks/circle",
            content=body,
            headers={"X-Circle-Signature": signature},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "credited"
        assert resp.json()["tx_hash"] == _TEST_TX_HASH
        assert Decimal(resp.json()["amount_usdc"]) == Decimal("5")

        assert len(_mock_services["audit"]) == 1
        assert _mock_services["audit"][0]["tx_hash"] == _TEST_TX_HASH
        assert Decimal(str(_mock_services["audit"][0]["amount_usdc"])) == Decimal("5")
        assert Decimal(str(_mock_services["balances"].get(_TEST_USER_ID, 0))) == Decimal("5")

    def test_duplicate_webhook_is_noop(self, client, _mock_services, monkeypatch):
        payload = _make_transfer_payload()
        body = _make_body(payload)
        signature = _make_signature(body)

        # First delivery
        resp1 = client.post(
            "/webhooks/circle",
            content=body,
            headers={"X-Circle-Signature": signature},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "credited"

        # Second delivery (same tx_hash)
        resp2 = client.post(
            "/webhooks/circle",
            content=body,
            headers={"X-Circle-Signature": signature},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_processed"

        assert len(_mock_services["audit"]) == 1
        assert Decimal(str(_mock_services["balances"].get(_TEST_USER_ID, 0))) == Decimal("5")

    def test_invalid_signature_rejected(self, client, _mock_services):
        payload = _make_transfer_payload()
        resp = client.post(
            "/webhooks/circle",
            content=_make_body(payload),
            headers={"X-Circle-Signature": "v1=deadbeef"},
        )
        assert resp.status_code == 401


class TestDepositAddress:
    def test_address_is_idempotent(self, client, _mock_services):
        resp1 = client.get("/api/deposit/address", params={"user_id": _TEST_USER_ID})
        assert resp1.status_code == 200, resp1.text
        data1 = resp1.json()
        assert data1["address"] == _TEST_ADDRESS
        assert data1["currency"] == "USDC"
        assert data1["network"] == "BASE"

        resp2 = client.get("/api/deposit/address", params={"user_id": _TEST_USER_ID})
        assert resp2.status_code == 200
        assert resp2.json()["address"] == data1["address"]

    def test_address_creates_wallet_when_missing(self, client, _mock_services, monkeypatch):
        new_user = str(uuid.uuid4())
        _mock_services["profiles"][new_user] = {"id": new_user}

        resp = client.get("/api/deposit/address", params={"user_id": new_user})
        assert resp.status_code == 200, resp.text
        assert resp.json()["address"] == _TEST_ADDRESS
        assert _mock_services["profiles"][new_user]["gaming_deposit_address"] == _TEST_ADDRESS
