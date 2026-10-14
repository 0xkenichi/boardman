"""Nonce manager + _send: no collisions, hash recorded first, timeouts are not failures."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from gaming.src.stack.agentic import onchain
from gaming.src.stack.agentic.db import nonces


class FakeEth:
    """A lagging RPC node: it reports the pending count slowly."""

    def __init__(self, *, lag_sec: float = 0.0, receipt_timeout: bool = False, revert: bool = False):
        self.chain_id = 5042002
        self.mined: set[int] = set()
        self.sent: list[tuple[int, str]] = []
        self.lag = lag_sec
        self.receipt_timeout = receipt_timeout
        self.revert = revert
        self.lock = threading.Lock()
        self.fail_broadcast = False

    def get_transaction_count(self, addr, block="latest"):
        assert block == "pending", "nonce must come from the pending count"
        with self.lock:
            n = len(self.mined)
        time.sleep(self.lag)
        return n

    def estimate_gas(self, tx):
        return 21000

    def get_block(self, _):
        return {"baseFeePerGas": 1}

    def send_raw_transaction(self, raw):
        if self.fail_broadcast:
            raise ConnectionError("rpc refused")
        nonce, h = raw
        with self.lock:
            assert nonce not in {n for n, _ in self.sent}, f"nonce {nonce} reused"
            self.sent.append((nonce, h))
            self.mined.add(nonce)
        return bytes.fromhex(h[2:])

    def wait_for_transaction_receipt(self, h, timeout=180):
        if self.receipt_timeout:
            raise TimeoutError("TimeExhausted")
        return SimpleNamespace(status=0 if self.revert else 1, blockNumber=7)

    def get_transaction(self, h):
        return None


class FakeW3:
    def __init__(self, eth):
        self.eth = eth

    @staticmethod
    def to_wei(n, unit):
        return int(n * 10**9)


class FakeAcct:
    address = "0x00000000000000000000000000000000000000aa"

    def sign_transaction(self, tx):
        h = "0x" + f"{tx['nonce']:064x}"
        return SimpleNamespace(raw_transaction=(tx["nonce"], h), hash=bytes.fromhex(h[2:]))


def test_concurrent_sends_never_share_a_nonce():
    eth = FakeEth(lag_sec=0.01)
    w3 = FakeW3(eth)
    hashes: list[str] = []

    def go():
        hashes.append(onchain._send(w3, FakeAcct(), {"to": "0x1"}, "resolveMatch"))

    ts = [threading.Thread(target=go) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(n for n, _ in eth.sent) == list(range(8))
    assert all(nonces.get(h)["status"] == "confirmed" for h in hashes)


def test_in_flight_reservation_is_skipped_even_if_node_lags():
    """A load-balanced RPC may still report the old pending count."""
    eth = FakeEth()
    w3 = FakeW3(eth)
    eth.mined = set()  # node never sees our txs mine
    original = eth.send_raw_transaction

    def send_without_mining(raw):
        nonce, h = raw
        eth.sent.append((nonce, h))
        return bytes.fromhex(h[2:])

    eth.send_raw_transaction = send_without_mining
    onchain._send(w3, FakeAcct(), {"to": "0x1"}, "a")
    onchain._send(w3, FakeAcct(), {"to": "0x1"}, "b")
    assert [n for n, _ in eth.sent] == [0, 1]
    eth.send_raw_transaction = original


def test_receipt_timeout_is_pending_confirmation_not_failure():
    eth = FakeEth(receipt_timeout=True)
    with pytest.raises(nonces.TxPendingConfirmation) as ei:
        onchain._send(FakeW3(eth), FakeAcct(), {"to": "0x1"}, "resolveMatch")
    row = nonces.get(ei.value.tx_hash)
    assert row["status"] == "pending_confirmation"
    assert row["tx_hash"] == ei.value.tx_hash  # recorded before the wait

    out = nonces.reconcile_pending(lambda chain, h: {"status": 1, "blockNumber": 9})
    assert out["confirmed"] == 1
    assert nonces.get(ei.value.tx_hash)["status"] == "confirmed"


def test_failed_broadcast_releases_the_nonce_for_reuse():
    eth = FakeEth()
    eth.fail_broadcast = True
    with pytest.raises(ConnectionError):
        onchain._send(FakeW3(eth), FakeAcct(), {"to": "0x1"}, "x")
    eth.fail_broadcast = False
    onchain._send(FakeW3(eth), FakeAcct(), {"to": "0x1"}, "x")
    assert [n for n, _ in eth.sent] == [0]  # no gap left behind


def test_revert_is_recorded_and_raised():
    eth = FakeEth(revert=True)
    with pytest.raises(RuntimeError, match="reverted"):
        onchain._send(FakeW3(eth), FakeAcct(), {"to": "0x1"}, "resolveMatch")
    assert nonces.get(eth.sent[0][1])["status"] == "reverted"


def test_build_transaction_nonce_is_overridden():
    eth = FakeEth()
    eth.mined = {0, 1, 2}
    onchain._send(FakeW3(eth), FakeAcct(), {"to": "0x1", "nonce": 0}, "x")
    assert eth.sent[0][0] == 3
