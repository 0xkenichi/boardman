"""October 2026 contracts audit, delta after merging integration/wave1:
the custodial v2 createMatch permit path (docs/security/AUDIT_2026-10_contracts.md §9).

D-01: the custodial creator's permit binds the opponent's passkey account
when they have one, but neither join path followed that binding: the
passkey path refused (no passkey creator row) and the custodial path sent a
joinMatch from the Circle wallet that the escrow rejects. The real-money
match could not lock, and the creator's stake sat until openTimeout.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from gaming.src.backend.services import clawstation_escrow as esc
from gaming.src.backend.services.self_custody import calls as C
from gaming.src.backend.services.self_custody import intents
from tests.channels_fixtures import world  # noqa: F401
from tests.channels_match_fixtures import mworld  # noqa: F401
from tests.test_self_custody import BOLA_SA, FakeChain, sc  # noqa: F401

CIRCLE_P1 = "0x" + "c1" * 20
CIRCLE_P2 = "0x" + "c2" * 20
ESCROW = "0x" + "e5" * 20


class BoundChain(FakeChain):
    """FakeChain that also answers BoardmanEscrow.matches(id).player2."""

    def __init__(self) -> None:
        super().__init__()
        self.player2: dict[str, str] = {}

    def escrow_player2(self, escrow, match_id_b32):
        return self.player2.get("0x" + bytes(match_id_b32).hex())


# ── passkey side: follow the on-chain binding ───────────────────────────────


def test_d01_passkey_opponent_can_join_a_custodial_creators_match(sc):  # noqa: F811
    """No passkey lock_create row exists (the creator locked custodially), but
    the escrow bound the opponent's passkey account: the passkey join is the
    only way in, so it must be allowed."""
    chainr = BoundChain()
    chainr.player2[C.match_id_hex("ch_d01")] = BOLA_SA
    assert intents.join_allowed("ch_d01", BOLA_SA, chainr) is True
    assert intents.join_allowed("ch_d01", "0x" + "99" * 20, chainr) is False


def test_d01_passkey_join_still_refused_without_an_onchain_match(sc):  # noqa: F811
    chainr = BoundChain()
    assert intents.join_allowed("ch_none", BOLA_SA, chainr) is False


# ── custodial side: refuse before any approve ───────────────────────────────


class FakeCircle:
    def __init__(self, execute_ok: bool = False) -> None:
        self.calls: list[str] = []
        self.execute_ok = execute_ok

    def approve_usdc_transfer(self, wallet_id, amount, spender):
        self.calls.append("approve")
        return {"success": True, "transaction_id": "tx_approve"}

    async def wait_for_transaction_async(self, tx_id, max_wait_seconds=0):
        return {"success": True, "tx_hash": "0x" + "ab" * 32, "time_waited": 0}

    def execute_contract_function(self, wallet_id, contract, sig, args):
        self.calls.append(sig)
        if self.execute_ok:
            return {"success": True, "transaction_id": "tx_exec", "tx_hash": "0x" + "cd" * 32}
        return {"success": False, "error": "execution reverted"}


def _custodial(monkeypatch, onchain: dict, *, role: str) -> FakeCircle:
    ch = {"id": "ch_d01", "creator_id": "u1", "opponent_id": "u2", "settlement_chain": "arc_mainnet",
          "status": "accepted" if role == "creator" else "creator_locked",
          "creator_lock_tx_id": None if role == "creator" else "tx_c"}
    fake = FakeCircle()
    audits: list[dict] = []
    monkeypatch.setattr(esc, "_load_challenge", lambda cid: dict(ch))
    monkeypatch.setattr(esc, "_challenge_chain", lambda c: "arc_mainnet")
    monkeypatch.setattr(esc, "_require_escrow", lambda chain_id: ESCROW)
    monkeypatch.setattr(esc, "escrow_version", lambda chain_id: 2)
    monkeypatch.setattr(esc, "_onchain_match_status", lambda chain_id, cid: onchain)
    monkeypatch.setattr(esc, "_find_existing_audit", lambda *a, **k: None)
    monkeypatch.setattr(esc, "_circle", lambda chain_id: fake)
    monkeypatch.setattr(esc, "_record_audit", lambda **k: audits.append(k))
    monkeypatch.setattr(esc, "_update_challenge", lambda cid, upd: audits.append(upd))

    async def _prep(uid, chain_id):
        return ("w_" + uid, CIRCLE_P1 if uid == "u1" else CIRCLE_P2)

    async def _args(challenge, chain_id, escrow_address, player1, stake_wei):
        return ["0x" + "00" * 32, BOLA_SA, str(stake_wei), "1", "0x"]

    monkeypatch.setattr(esc, "_prepare_wallet", _prep)
    monkeypatch.setattr(esc, "_v2_create_args", _args)
    fake.audits = audits  # type: ignore[attr-defined]
    return fake


def _stage() -> dict:
    async def _reserve(chain_id):
        return None

    return {"reserve": _reserve, "submitted": False, "reserved": False}


def test_d01_custodial_join_refuses_before_approve_when_bound_to_another_account(monkeypatch):
    fake = _custodial(monkeypatch, {"player1": CIRCLE_P1, "player2": BOLA_SA, "stake_per_player": 5.0,
                                    "status": "OPEN"}, role="opponent")
    stage = _stage()
    with pytest.raises(esc.EscrowError, match="passkey"):
        asyncio.run(esc._approve_and_join_match("u2", "ch_d01", Decimal("5"), stage))
    assert fake.calls == [], "approved/joined from a wallet the escrow will reject"
    assert stage["submitted"] is False  # the stake-cap reservation is released


def test_d01_custodial_join_proceeds_when_bound_to_this_wallet(monkeypatch):
    fake = _custodial(monkeypatch, {"player1": CIRCLE_P1, "player2": CIRCLE_P2, "stake_per_player": 5.0,
                                    "status": "OPEN"}, role="opponent")
    fake.execute_ok = True
    out = asyncio.run(esc._approve_and_join_match("u2", "ch_d01", Decimal("5"), _stage()))
    assert out["success"] is True
    assert fake.calls == ["approve", "joinMatch(bytes32)"]


def test_d01_create_recovery_requires_the_onchain_player1_to_be_us(monkeypatch):
    """createMatch reverted and the chain shows a match for this id — but
    created by another account. That is not "our earlier attempt"."""
    fake = _custodial(monkeypatch, {"player1": "0x" + "77" * 20, "player2": BOLA_SA,
                                    "stake_per_player": 5.0, "status": "OPEN"}, role="creator")
    with pytest.raises(esc.EscrowError, match="createMatch failed"):
        asyncio.run(esc._approve_and_create_match("u1", "ch_d01", Decimal("5"), _stage()))
    assert not any(a.get("status") == "creator_locked" for a in fake.audits)
