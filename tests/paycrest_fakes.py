"""In-memory stand-ins for Paycrest and the chains (CCTP + Circle wallets).

Nothing here touches the network: ``FakePaycrest`` replaces the Sender API
client and ``FakeChainOps`` replaces Circle wallet calls and the Iris
attestation API. Both record what they were asked to do so tests can assert
money moved exactly once.
"""
from __future__ import annotations

import itertools
import json
from decimal import Decimal
from typing import Any, Optional

import pytest

from gaming.src.backend.services.paycrest.client import sign
from gaming.src.backend.services.paycrest.models import (
    AmbiguousSubmit,
    Institution,
    KycRejected,
    PaycrestError,
    PaycrestOrder,
    RateQuote,
)

SECRET = "paycrest-test-secret-not-real"
RELAYERS = {"PAYCREST_ARC_RELAYER_WALLET_ID": "relay-arc", "PAYCREST_BASE_RELAYER_WALLET_ID": "relay-base"}
BANKS = [
    Institution("GTBINGLA", "Guaranty Trust Bank", "bank"),
    Institution("OPAYNGPC", "OPay", "bank"),
    Institution("ABNGNGLA", "Access Bank", "bank"),
    Institution("KUDANGPC", "Kuda Microfinance Bank", "bank"),
]


class FakePaycrest:
    def __init__(self) -> None:
        self.buy_rate = Decimal("1600")
        self.sell_rate = Decimal("1550")
        self.names: dict[str, str] = {}
        self.default_name = "ADA OBI"
        self.created: list[dict] = []
        self.orders: dict[str, PaycrestOrder] = {}
        self.kyc_reject = False
        self.unavailable = 0      # next N creates answer 503
        self.ambiguous = 0        # next N creates lose their answer (order IS created)
        self.refuse = False       # 400 non-KYC
        self.fee_usdc = Decimal("0.02")
        self.fee_ngn = Decimal("50")
        self._ids = itertools.count(1)

    # -- reads --
    def get_rate(self, amount, *, side, network=None, token=None, currency=None) -> RateQuote:
        rate = self.buy_rate if side == "buy" else self.sell_rate
        return RateQuote("base", "USDC", "NGN", side, rate, ["AbCdEfGh"], "regular", 60)

    def list_institutions(self, currency=None):
        return list(BANKS)

    def verify_account(self, institution, account_identifier):
        return self.names.get(account_identifier, self.default_name)

    def get_order(self, order_id):
        return self.orders[order_id]

    def find_order_by_reference(self, reference, **kw):
        for o in self.orders.values():
            if o.reference == reference:
                return o
        return None

    # -- create --
    def create_order(self, payload: dict) -> PaycrestOrder:
        if self.unavailable > 0:
            self.unavailable -= 1
            raise PaycrestError("no provider", status_code=503, retryable=True, kind="unavailable")
        if self.kyc_reject and payload["source"]["type"] == "fiat":
            raise KycRejected("kyc invalid", status_code=400, field_errors=[{"field": "Source"}], kind="kyc")
        if self.refuse:
            raise PaycrestError("bad recipient", status_code=400)
        self.created.append(json.loads(json.dumps(payload)))
        oid = f"pc-{next(self._ids)}"
        amount = Decimal(payload["amount"])
        if payload["source"]["type"] == "fiat":
            pa = {"institution": "PROVNGPC", "accountIdentifier": "9900001111", "accountName": "PAYCREST/ADA OBI",
                  "amountToTransfer": str(amount + self.fee_ngn), "currency": "NGN",
                  "validUntil": "2099-01-01T00:00:00Z"}
            rate = self.buy_rate
        else:
            pa = {"network": "base", "receiveAddress": "0x" + "9" * 40,
                  "amountToTransfer": str(amount + self.fee_usdc), "currency": "USDC",
                  "validUntil": "2099-01-01T00:00:00Z"}
            rate = self.sell_rate
        order = PaycrestOrder.from_api({"id": oid, "status": "initiated", "amount": str(amount), "rate": str(rate),
                                        "reference": payload.get("reference"), "providerAccount": pa,
                                        "transactionFee": str(self.fee_usdc)})
        self.orders[oid] = order
        if self.ambiguous > 0:
            self.ambiguous -= 1
            raise AmbiguousSubmit("lost answer", kind="ambiguous")
        return order

    def set_status(self, order_id: str, status: str) -> None:
        self.orders[order_id].status = status
        self.orders[order_id].raw["status"] = status


class FakeChainOps:
    """Balances per (chain, address); burns debit, mints credit."""

    def __init__(self) -> None:
        self.balances: dict[tuple[str, str], Decimal] = {}
        self.addr_of: dict[str, tuple[str, str]] = {}   # wallet_id -> (chain, address)
        self.calls: list[tuple] = []
        self.txs: dict[str, dict] = {}
        self.fail: dict[str, int] = {}                  # op -> how many times to fail on chain
        self.raise_: dict[str, int] = {}                # op -> how many times to raise ChainOpsError
        self.attest_pending = 0
        self.fee_bps = Decimal("1")
        self._n = itertools.count(1)

    def _tx(self, op: str, **info) -> str:
        from gaming.src.backend.services.bridge.chain_ops import ChainOpsError

        if self.raise_.get(op):
            self.raise_[op] -= 1
            raise ChainOpsError(f"{op} rejected")
        tid = f"tx-{op}-{next(self._n)}"
        failed = bool(self.fail.get(op))
        if failed:
            self.fail[op] -= 1
        self.txs[tid] = {"op": op, "failed": failed, **info}
        self.calls.append((op, info.get("idem")))
        if not failed and "apply" in info:
            info["apply"]()
        return tid

    def bal(self, chain: str, address: str) -> Decimal:
        return self.balances.get((chain, address.lower()), Decimal("0"))

    def credit(self, chain: str, address: str, amount: Decimal) -> None:
        k = (chain, address.lower())
        self.balances[k] = self.balances.get(k, Decimal("0")) + Decimal(amount)

    # -- ChainOps --
    def create_wallet(self, chain, profile_id, account_type, idem):
        for wid, (c, a) in self.addr_of.items():
            if wid == f"wal-{idem}":
                return wid, a
        n = len(self.addr_of) + 1
        addr = "0x" + f"{n:040x}"
        wid = f"wal-{idem}"
        self.addr_of[wid] = (chain, addr)
        self.calls.append(("create_wallet", idem, account_type))
        return wid, addr

    def usdc_balance(self, chain, address):
        return self.bal(chain, address)

    def ensure_gas(self, chain, address):
        self.calls.append(("ensure_gas", address))

    def transfer_usdc(self, chain, wallet_id, to, amount, idem):
        if any(t.get("idem") == idem and not t["failed"] for t in self.txs.values()):
            return next(k for k, t in self.txs.items() if t.get("idem") == idem)
        c, a = self.addr_of[wallet_id]

        def apply():
            self.credit(c, a, -Decimal(amount))
            self.credit(c, to, Decimal(amount))
        return self._tx("transfer", idem=idem, apply=apply, amount=Decimal(amount), to=to)

    def approve_burn(self, chain, wallet_id, amount, idem):
        return self._tx("approve", idem=idem)

    def burn(self, chain, wallet_id, amount, dst_domain, mint_recipient, max_fee, fast, idem):
        c, a = self.addr_of[wallet_id]
        if self.bal(c, a) < Decimal(amount):
            from gaming.src.backend.services.bridge.chain_ops import ChainOpsError

            raise ChainOpsError("insufficient USDC to burn")
        info: dict[str, Any] = {"amount": Decimal(amount), "dst_domain": dst_domain, "recipient": mint_recipient,
                                "fee": Decimal(max_fee), "fast": fast}

        def apply():
            self.credit(c, a, -Decimal(amount))
        return self._tx("burn", idem=idem, apply=apply, **info)

    def tx_status(self, chain, tx_id):
        t = self.txs[tx_id]
        return ("failed", "") if t["failed"] else ("confirmed", f"0xhash-{tx_id}")

    def fetch_message(self, src_chain, burn_tx_hash):
        if self.attest_pending > 0:
            self.attest_pending -= 1
            return {"status": "pending"}
        return {"status": "complete", "message": f"msg:{burn_tx_hash.removeprefix('0xhash-')}",
                "attestation": "0xatt"}

    def mint(self, dst_chain, relayer_wallet_id, message, attestation, idem):
        burn = self.txs[message.split(":", 1)[1]]
        # Circle charges its quoted fee (never more than the burn's maxFee).
        fee = min(burn["fee"], burn["amount"] * self.fee_bps / Decimal(10_000)) if burn["fast"] else Decimal("0")
        amount = burn["amount"] - fee

        def apply():
            self.credit(dst_chain, burn["recipient"], amount)
        return self._tx("mint", idem=idem, apply=apply, relayer=relayer_wallet_id)

    def fast_fee_bps(self, src_chain, dst_chain):
        return self.fee_bps

    def ops(self, name: str) -> list:
        return [c for c in self.calls if c[0] == name]


@pytest.fixture
def rail(monkeypatch):
    """The naira rail switched on against fakes."""
    from gaming.src.backend.services.bridge import chain_ops
    from gaming.src.backend.services.paycrest import client, notices, onramp

    monkeypatch.setenv("PAYCREST_ENABLED", "1")
    monkeypatch.setenv("REAL_MONEY_ENABLED", "1")
    monkeypatch.setenv("PAYCREST_API_KEY", "pk-test-not-real")
    monkeypatch.setenv("PAYCREST_API_SECRET", SECRET)
    for k, v in RELAYERS.items():
        monkeypatch.setenv(k, v)
    pc, ops = FakePaycrest(), FakeChainOps()
    client.set_client(pc)
    chain_ops.set_chain_ops(ops)
    onramp._institutions_cached.cache_clear()
    told: list[tuple[str, str]] = []
    alerts: list[str] = []
    monkeypatch.setattr(notices, "tell", lambda pid, text, **kw: told.append((pid, text)))
    monkeypatch.setattr(notices, "alert_admins", lambda text: alerts.append(text))
    ns = type("Rail", (), {})()
    ns.pc, ns.ops, ns.told, ns.alerts = pc, ops, told, alerts
    yield ns
    client.set_client(None)
    chain_ops.set_chain_ops(None)
    onramp._institutions_cached.cache_clear()


def webhook_body(order_id: str, status: str, *, event: Optional[str] = None, reference: str = "",
                 **extra: Any) -> bytes:
    data = {"id": order_id, "status": status, "reference": reference, **extra}
    return json.dumps({"event": event or f"payment_order.{status}", "webhookVersion": "2", "data": data}).encode()


def signed(body: bytes, secret: str = SECRET) -> dict[str, str]:
    return {"X-Paycrest-Signature": sign(body, secret), "Content-Type": "application/json"}
