"""v2 fee sweeps: withdrawFees/withdraw when accrued, a no-op on v1."""
from __future__ import annotations

from types import SimpleNamespace

from gaming.src.stack.agentic import fee_sweep


class _Fn:
    def __init__(self, value=None, label=None):
        self.value = value
        self.label = label

    def call(self):
        return self.value

    def build_transaction(self, opts):
        return {"label": self.label, "from": opts["from"]}


class FakeContract:
    def __init__(self, accrued_name: str, accrued: int, owed: dict[str, int]):
        self._owed = owed
        self.functions = SimpleNamespace(
            **{accrued_name: lambda: _Fn(accrued)},
            owed=lambda addr: _Fn(owed.get(addr, 0)),
            withdrawFees=lambda: _Fn(label="withdrawFees"),
            withdraw=lambda: _Fn(label="withdraw"),
        )


class FakeW3:
    @staticmethod
    def to_checksum_address(a):
        return a


def test_sweeps_accrued_fees_and_owed_creator_shares():
    sent = []

    def send(w3, acct, tx, label):
        sent.append((acct.address, label))
        return f"0x{len(sent):064x}"

    out = fee_sweep._sweep_contract(
        FakeW3(),
        FakeContract("protocolFees", 5_000_000, {"0xraja": 250_000}),
        accrued_fn="protocolFees",
        resolver_acct=SimpleNamespace(address="0xresolver"),
        agent_accounts=[("raja", SimpleNamespace(address="0xraja")), ("nero", SimpleNamespace(address="0xnero"))],
        send=send,
    )
    assert sent == [("0xresolver", "withdrawFees"), ("0xraja", "withdraw")]
    assert out["accrued_raw"] == 5_000_000 and out["withdraw"][0]["agent_id"] == "raja"


def test_nothing_accrued_sends_nothing():
    sent = []
    fee_sweep._sweep_contract(
        FakeW3(), FakeContract("accruedFees", 0, {}), accrued_fn="accruedFees",
        resolver_acct=SimpleNamespace(address="0xr"), agent_accounts=[], send=lambda *a: sent.append(a),
    )
    assert sent == []


def test_v1_contracts_are_a_no_op(monkeypatch):
    from gaming.src.stack.agentic import onchain, spectator_onchain

    monkeypatch.setattr(onchain, "_chain_config", lambda cid: {"escrow": "0xe", "chain_id": cid})
    monkeypatch.setattr(onchain, "_w3", lambda cfg: FakeW3())
    monkeypatch.setattr(onchain, "escrow_version", lambda w3, cfg: 1)
    assert "skipped" in fee_sweep.sweep_escrow_fees()

    monkeypatch.setattr(spectator_onchain, "spectator_pool_address", lambda: "0xpool")
    monkeypatch.setattr(spectator_onchain, "_pool_cfg", lambda cid: {"pool": "0xpool"})
    monkeypatch.setattr(spectator_onchain, "pool_version", lambda w3, cfg: 1)
    assert "skipped" in fee_sweep.sweep_pool_fees()


def test_sweep_refuses_other_labels():
    import pytest

    with pytest.raises(RuntimeError, match="cannot broadcast"):
        fee_sweep._guarded_send(None, None, {}, "transfer")


def test_sweep_slot_is_claimed_once_per_interval():
    assert fee_sweep._claim_slot("fee_sweep:test", 3600) is True
    assert fee_sweep._claim_slot("fee_sweep:test", 3600) is False
    assert fee_sweep._claim_slot("fee_sweep:test", 0) is True


def test_maintenance_tick_offchain_only_cleans_tmp(tmp_path, monkeypatch):
    import os
    import time

    from gaming.src.stack.agentic.store import data_dir

    old = data_dir() / "ledger.json.123.456.tmp"
    old.write_text("")
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    fresh = data_dir() / "agents.json.1.2.tmp"
    fresh.write_text("")
    out = fee_sweep.maintenance_tick()
    assert out["tmp_removed"] == ["ledger.json.123.456.tmp"]
    assert fresh.exists() and out["onchain"] == "disabled"
