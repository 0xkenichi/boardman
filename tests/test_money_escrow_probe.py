"""Aborting a table reads the on-chain escrow and acts on what it really holds.

BoardmanEscrow.MatchStatus (v1 and v2 alike) is OPEN=0, LOCKED=1,
DISPUTED=2, RESOLVED=3, CANCELLED=4; an empty slot also reads status 0 but
has player1 = address(0). The old probe did ``int(status or -1)``, so an
OPEN escrow (status 0) became -1 and was skipped: the creator's stake stayed
on-chain while the ledger refunded the table. Here a fake chain client stands
in for the escrow contract.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from gaming.src.stack.agentic import matches as matches_mod
from gaming.src.stack.agentic import onchain
from gaming.src.stack.agentic.db import leases
from gaming.src.stack.agentic.db.tables import MATCHES

RAJA = "agent_raja_kia_alekhine"
NERO = "agent_nero_sicilian_french"
ZERO = "0x0000000000000000000000000000000000000000"


class FakeEscrow:
    """``escrow.functions.matches(mid).call()`` over an in-memory slot map."""

    def __init__(self) -> None:
        self.slots: dict[bytes, tuple] = {}
        self.calls = 0
        self.fail = False
        outer = self

        class _Call:
            def __init__(self, mid: bytes) -> None:
                self.mid = mid

            def call(self) -> tuple:
                outer.calls += 1
                if outer.fail:
                    raise ConnectionError("rpc down")
                return outer.slots.get(self.mid, (ZERO, ZERO, 0, 0, 0, 0))

        class _Functions:
            def matches(self, mid: bytes) -> _Call:
                return _Call(mid)

        self.functions = _Functions()

    def put(self, match_id: str, status: int) -> None:
        self.slots[onchain.match_id_to_bytes32(match_id)] = (
            "0x" + "a1" * 20, "0x" + "b2" * 20, 1_000_000, status, 1_700_000_000, 0,
        )


@pytest.fixture()
def chain(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setattr(matches_mod, "_notify_spectator_outcomes", lambda *a, **k: None)
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry.cache_clear()
    get_match_service.cache_clear()
    leases.forget_local_state()

    fake = FakeEscrow()
    cancels: list[str] = []
    monkeypatch.setattr(onchain, "_chain_config", lambda cid: {"escrow": "0xe", "chain_id": cid})
    monkeypatch.setattr(onchain, "_w3", lambda cfg: object())
    monkeypatch.setattr(onchain, "_contracts", lambda w3, cfg: (None, fake))

    def _resolve(match_id: str, winner: Any, *, chain_id: str, draw: bool, authorization: Any) -> dict:
        assert draw is True  # an abort only ever cancels (both stakes back)
        cancels.append(match_id)
        fake.put(match_id, onchain.ONCHAIN_CANCELLED)
        return {"success": True, "tx_hash": "0xcancel", "result": "draw"}

    monkeypatch.setattr(onchain, "resolve_onchain", _resolve)
    yield fake, cancels
    leases.forget_local_state()


def _onchain_table(**extra: Any) -> str:
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    rt = get_house()
    mid = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=1, white_agent_id=RAJA)["match_id"]
    rt.lock(mid)
    MATCHES.update(mid, lambda r: r.update(onchain=True, settlement_mode="onchain", **extra))
    return mid


@pytest.mark.parametrize(
    "status", [onchain.ONCHAIN_OPEN, onchain.ONCHAIN_LOCKED, onchain.ONCHAIN_DISPUTED]
)
def test_open_locked_and_disputed_escrows_are_cancelled(chain, status):
    from gaming.src.stack.agentic.house import abort_table

    fake, cancels = chain
    mid = _onchain_table()
    fake.put(mid, status)
    out = abort_table(mid, reason="interrupted")
    assert out["status"] == "cancelled"
    assert cancels == [mid], f"status {onchain.ONCHAIN_STATUS[status]} must be cancelled on-chain"
    assert out["onchain"]["tx_hash"] == "0xcancel"
    # A retry (ops script, recovery sweep) is a journaled no-op: no 2nd cancel.
    abort_table(mid, reason="interrupted")
    assert cancels == [mid]


@pytest.mark.parametrize("status", [onchain.ONCHAIN_RESOLVED, onchain.ONCHAIN_CANCELLED])
def test_final_escrows_are_not_cancelled_again(chain, status):
    from gaming.src.stack.agentic.house import abort_table

    fake, cancels = chain
    mid = _onchain_table()
    fake.put(mid, status)
    out = abort_table(mid, reason="interrupted")
    assert out["status"] == "cancelled"
    assert cancels == []
    assert out["onchain"] == {"tx_hash": None, "already_final": True, "status": status}


def test_absent_escrow_is_skipped(chain):
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.house import abort_table

    fake, cancels = chain
    mid = _onchain_table()  # the on-chain create never landed: empty slot
    out = abort_table(mid, reason="interrupted")
    assert out["status"] == "cancelled"
    assert cancels == []
    assert out["onchain"] == {"tx_hash": None, "skipped": True, "absent": True}
    # The ledger side is still refunded.
    assert ledger.get_escrow(mid)["result"] == "draw"


def test_absent_escrow_with_a_lock_tx_in_flight_is_not_skipped(chain):
    from gaming.src.stack.agentic.house import abort_table

    fake, cancels = chain
    mid = _onchain_table(onchain_pending_tx={"label": "createMatch", "tx_hash": "0xpending"})
    with pytest.raises(RuntimeError, match="may still mine"):
        abort_table(mid, reason="interrupted")
    assert MATCHES.get(mid)["status"] == "aborting"
    # The tx mined after all: the next attempt cancels the OPEN escrow.
    fake.put(mid, onchain.ONCHAIN_OPEN)
    assert abort_table(mid, reason="interrupted")["status"] == "cancelled"
    assert cancels == [mid]


def test_unreadable_escrow_retries_instead_of_skipping(chain):
    from gaming.src.stack.agentic.house import abort_table

    fake, cancels = chain
    mid = _onchain_table()
    fake.put(mid, onchain.ONCHAIN_OPEN)
    fake.fail = True
    with pytest.raises(ConnectionError):
        abort_table(mid, reason="interrupted")
    assert MATCHES.get(mid)["status"] == "aborting" and cancels == []
    fake.fail = False
    assert abort_table(mid, reason="interrupted")["status"] == "cancelled"
    assert cancels == [mid]


def test_settle_probe_treats_open_as_not_final(chain):
    fake, _ = chain
    fake.put("agm_probe", onchain.ONCHAIN_OPEN)
    assert matches_mod._onchain_already_final("agm_probe", "arc") is None
    fake.put("agm_probe", onchain.ONCHAIN_CANCELLED)
    assert matches_mod._onchain_already_final("agm_probe", "arc")["status"] == "CANCELLED"
    with pytest.raises(onchain.OnchainMatchAbsent):
        onchain.read_onchain_match("agm_never", "arc")
    assert Decimal(onchain.read_onchain_match("agm_probe", "arc")["stake_usdc"]) == Decimal("1")
