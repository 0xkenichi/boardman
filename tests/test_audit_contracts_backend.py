"""October 2026 contracts audit: backend PoCs (docs/security/AUDIT_2026-10_contracts.md).

Each test is named after its finding id. Chain access is faked; nothing here
talks to an RPC.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from gaming.src.stack.agentic import matches as matches_mod
from gaming.src.stack.agentic import spectator_onchain as soc
from gaming.src.stack.agentic.db import leases

RAJA = "agent_raja_kia_alekhine"
NERO = "agent_nero_sicilian_french"
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# Same vector as PERMIT_VECTOR in contracts/test/Audit.2026-10.js, where it is
# checked against the contract's own hashCreateMatch encoding.
VECTOR_DIGEST = "909093eb8f7da9dfe46e9c28838faf8e260f6345e78a0bd067f59b151fb8529c"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setattr(matches_mod, "_notify_spectator_outcomes", lambda *a, **k: None)
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry.cache_clear()
    get_match_service.cache_clear()
    leases.forget_local_state()
    yield
    leases.forget_local_state()


# ── A-01: backend signer == contract EIP-712 encoding ───────────────────────


def test_a01_python_permit_signs_the_contract_digest():
    import hashlib

    from eth_account import Account

    from gaming.src.stack.agentic.onchain import sign_create_permit

    acct = Account.create()
    sig = sign_create_permit(
        acct.key.hex(),
        chain_id=5042,
        escrow="0x00000000000000000000000000000000000E5C70",
        match_id_b32=hashlib.sha256(b"agm_audit_vector").digest(),
        player1="0x1111111111111111111111111111111111111111",
        player2="0x2222222222222222222222222222222222222222",
        stake_raw=5_000_000,
        deadline=1_800_000_000,
    )
    assert len(sig) == 65
    assert sig[64] in (27, 28)  # OZ ECDSA wants v in {27, 28}
    assert int.from_bytes(sig[32:64], "big") <= SECP256K1_N // 2  # low-s only
    assert Account._recover_hash(bytes.fromhex(VECTOR_DIGEST), signature=sig) == acct.address


# ── H-01: no on-chain bets once the result can be known ─────────────────────


def _onchain_table(monkeypatch) -> str:
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    # lock_both opens the pool book when the operator is on; no RPC in tests.
    monkeypatch.setattr(soc, "open_book_onchain", lambda m, chain_id="arc": {"pool": "0xpool", "tx_hash": "0xopen"})
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    svc = get_match_service()
    mid = svc.create_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=5, white_agent_id=RAJA)["match_id"]
    svc.lock_both(mid)
    if not SpectatorBook().get(mid):
        SpectatorBook().open_book(mid, agent_a_id=RAJA, agent_b_id=NERO)
    SpectatorBook().mark_onchain(mid, pool="0xpool", open_tx_hash="0xopen")
    return mid


def test_h01_settlement_closes_the_pool_book_before_any_other_step(store, monkeypatch):
    """The game is over (and public) when settlement starts. The SpectatorPool
    book must be closed first, not after the escrow and stats steps."""
    events: list[str] = []
    monkeypatch.setattr(soc, "spectator_onchain_enabled", lambda: True)
    monkeypatch.setattr(soc, "close_book_onchain", lambda mid, chain_id="arc": events.append("pool_close") or {"tx_hash": "0xc"})
    monkeypatch.setattr(soc, "resolve_book", lambda mid, side, chain_id="arc": events.append("pool_resolve") or {"tx_hash": None})
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", lambda name: events.append(name))
    mid = _onchain_table(monkeypatch)
    from gaming.src.stack.agentic.matches import get_match_service

    out = get_match_service().settle_result(
        mid, {"result": "white_win", "winner_agent_id": RAJA, "termination": "CHECKMATE", "moves": []}
    )
    assert out["status"] == "settled"
    assert "pool_close" in events, "settlement never closed the on-chain book itself"
    assert events.index("pool_close") < events.index("escrow"), events
    assert events.index("pool_close") < events.index("pool_resolve")


def test_h01_a_failed_early_close_does_not_block_settlement(store, monkeypatch):
    def _boom(mid, chain_id="arc"):
        raise RuntimeError("rpc down")

    monkeypatch.setattr(soc, "spectator_onchain_enabled", lambda: True)
    monkeypatch.setattr(soc, "close_book_onchain", _boom)
    monkeypatch.setattr(soc, "resolve_book", lambda mid, side, chain_id="arc": {"tx_hash": None})
    mid = _onchain_table(monkeypatch)
    from gaming.src.stack.agentic.matches import get_match_service

    out = get_match_service().settle_result(
        mid, {"result": "white_win", "winner_agent_id": RAJA, "termination": "CHECKMATE", "moves": []}
    )
    assert out["status"] == "settled"


class _Sent(Exception):
    pass


def _fake_pool(monkeypatch, *, status: int = 1, close_in: int = 600) -> list[str]:
    import time

    sends: list[str] = []
    monkeypatch.setattr(
        soc, "read_book", lambda mid, chain_id="arc": {"status": status, "status_name": "Open", "close_at": int(time.time()) + close_in}
    )

    def _no_chain(*a, **k):
        sends.append("chain")
        raise _Sent("a depositFor would have been sent")

    monkeypatch.setattr(soc, "_pool_cfg", _no_chain)
    monkeypatch.setattr(soc, "open_book_onchain", _no_chain)
    return sends


@pytest.mark.parametrize("match_status", ["settling", "settled", "cancelled"])
def test_h01_deposit_for_refuses_a_finished_match(store, monkeypatch, match_status):
    """An approval tapped after the game ended must not reach the pool."""
    sends = _fake_pool(monkeypatch)
    with pytest.raises(soc.SpectatorOnchainError):
        soc.deposit_for("agm_x1", "0x" + "ab" * 20, Decimal("5"), "a",
                        match={"match_id": "agm_x1", "status": match_status})
    assert sends == []


def test_h01_deposit_for_refuses_after_the_offchain_freeze(store, monkeypatch):
    """Ply-N freeze closed the off-chain book; the async on-chain close() may
    not have landed (or failed). The House path must not bet past the freeze."""
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    sends = _fake_pool(monkeypatch)
    SpectatorBook().open_book("agm_x2", agent_a_id=RAJA, agent_b_id=NERO)
    SpectatorBook().mark_onchain("agm_x2", pool="0xpool")
    SpectatorBook().close_book("agm_x2", reason="ply_24")
    with pytest.raises(soc.SpectatorOnchainError):
        soc.deposit_for("agm_x2", "0x" + "ab" * 20, Decimal("5"), "a",
                        match={"match_id": "agm_x2", "status": "playing"})
    assert sends == []


def test_h01_deposit_for_still_works_while_betting_is_open(store, monkeypatch):
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    sends = _fake_pool(monkeypatch)
    SpectatorBook().open_book("agm_x3", agent_a_id=RAJA, agent_b_id=NERO)
    SpectatorBook().mark_onchain("agm_x3", pool="0xpool")
    with pytest.raises(_Sent):
        soc.deposit_for("agm_x3", "0x" + "ab" * 20, Decimal("5"), "a",
                        match={"match_id": "agm_x3", "status": "playing"})
    assert sends == ["chain"]


# ── M-01: never refund a pulled stake whose pool deposit landed or may land ──


def _apply_bet(monkeypatch, deposit_exc: BaseException | None, *, projection_fails: bool = False) -> tuple[dict, list]:
    from gaming.src.backend import db_layer_blockchain as dlb
    from gaming.src.backend.api import rematch_web as rw
    from gaming.src.backend.services import tx_approval as ta

    refunds: list[Any] = []
    stored: list[dict] = []
    monkeypatch.setattr(ta, "get_approval_row", lambda aid: {"status": "approved", "payload": {}})
    monkeypatch.setattr(ta, "claim_apply", lambda aid: {"id": aid})
    monkeypatch.setattr(ta, "store_apply_result", lambda aid, res: stored.append(res))
    monkeypatch.setattr(rw, "_approved_flow_refusal", lambda *a, **k: None)
    monkeypatch.setattr(soc, "spectator_onchain_enabled", lambda: True)

    async def _pull(profile_id, amount):
        return None

    async def _debit(profile_id, amount):
        return None

    async def _balance(profile_id, **kw):
        return 0

    from gaming.src.backend.services import clawstation_circle as cc

    monkeypatch.setattr(rw, "_pull_play_usdc", _pull)
    monkeypatch.setattr(dlb, "debit_wallet", _debit)
    monkeypatch.setattr(cc, "get_usdc_balance", _balance)
    monkeypatch.setattr(soc, "refund_float_to_user", lambda addr, amt, **k: refunds.append((addr, amt)) or {"tx_hash": "0xrefund"})

    if projection_fails:
        # The pool deposit confirms; the JSON projection afterwards blows up.
        monkeypatch.setattr(soc, "deposit_for", lambda *a, **k: {"tx_hash": "0xdep", "pool": "0xpool"})

        def _svc():
            raise RuntimeError("projection store unavailable")

        import gaming.src.stack.agentic.matches as m

        monkeypatch.setattr(m, "get_match_service", lambda: type("S", (), {"get": lambda self, mid: {"match_id": mid}})())
        from gaming.src.stack.agentic.economy import spectator as spec

        monkeypatch.setattr(spec.SpectatorBook, "project_deposit", lambda self, *a, **k: _svc())
        import gaming.src.stack.agentic.house as house

        monkeypatch.setattr(house, "resolve_side", lambda match, side: side)
    else:
        async def _dep(**kw):
            raise deposit_exc

        monkeypatch.setattr(rw, "_deposit_spectator_onchain", _dep)

    out = asyncio.run(
        rw._apply_approved_spectator_bet(
            approval_id="ap1", profile_id="p1", match_id="agm_m01", side="a", amount=5.0,
            summary={"address": "0x" + "cd" * 20, "ledger_usdc": 0},
        )
    )
    return out, refunds


def test_m01_pending_deposit_is_not_refunded(store, monkeypatch):
    from gaming.src.stack.agentic.db.nonces import TxPendingConfirmation

    out, refunds = _apply_bet(monkeypatch, TxPendingConfirmation("depositFor", "0x" + "11" * 32))
    assert refunds == [], "refunded a deposit that may still mine (user would be paid twice)"
    assert out["success"] is False and out.get("pending") is True


def test_m01_failed_deposit_is_still_refunded(store, monkeypatch):
    out, refunds = _apply_bet(monkeypatch, RuntimeError("depositFor reverted tx=0xdead"))
    assert len(refunds) == 1
    assert out["success"] is False and out.get("refunded") is True


def test_m01_projection_error_after_a_landed_deposit_is_not_refunded(store, monkeypatch):
    out, refunds = _apply_bet(monkeypatch, None, projection_fails=True)
    assert refunds == [], "refunded a deposit that already landed in the pool"


# ── L-02: a transient RPC error must not pin the v1 ABI ─────────────────────


def test_l02_version_probe_does_not_cache_a_transient_failure(monkeypatch):
    from gaming.src.stack.agentic import onchain

    monkeypatch.delenv("BOARDMAN_ESCROW_VERSION", raising=False)
    monkeypatch.delenv("SPECTATOR_POOL_VERSION", raising=False)
    onchain._ESCROW_VERSION_CACHE.clear()
    soc._POOL_VERSION_CACHE.clear()
    state = {"down": True}

    class _Fn:
        def call(self):
            if state["down"]:
                raise ConnectionError("rpc timeout")
            return 2

    class _C:
        class functions:  # noqa: N801
            ESCROW_VERSION = staticmethod(lambda: _Fn())
            POOL_VERSION = staticmethod(lambda: _Fn())

    class _Eth:
        def contract(self, address, abi):
            return _C()

    class _W3:
        eth = _Eth()

        @staticmethod
        def to_checksum_address(a):
            return a

    w3 = _W3()
    with pytest.raises(ConnectionError):
        onchain.escrow_version(w3, {"escrow": "0xE"})
    with pytest.raises(ConnectionError):
        soc.pool_version(w3, {"pool": "0xP"})
    state["down"] = False
    assert onchain.escrow_version(w3, {"escrow": "0xE"}) == 2
    assert soc.pool_version(w3, {"pool": "0xP"}) == 2


def test_l02_a_contract_without_the_probe_is_v1(monkeypatch):
    from web3.exceptions import ContractLogicError

    from gaming.src.stack.agentic import onchain

    monkeypatch.delenv("BOARDMAN_ESCROW_VERSION", raising=False)
    onchain._ESCROW_VERSION_CACHE.clear()

    class _Fn:
        def call(self):
            raise ContractLogicError("execution reverted")

    class _C:
        class functions:  # noqa: N801
            ESCROW_VERSION = staticmethod(lambda: _Fn())

    class _W3:
        class eth:  # noqa: N801
            @staticmethod
            def contract(address, abi):
                return _C()

        @staticmethod
        def to_checksum_address(a):
            return a

    assert onchain.escrow_version(_W3(), {"escrow": "0xV1"}) == 1


# ── L-03: never treat a settled on-chain match as freshly locked ────────────


@pytest.mark.parametrize("status", [3, 4])
def test_l03_dual_lock_refuses_a_settled_onchain_match(monkeypatch, status):
    from gaming.src.stack.agentic import onchain

    calls: list[str] = []

    class _Fn:
        def __init__(self, ret):
            self.ret = ret

        def call(self):
            return self.ret

        def build_transaction(self, tx):
            calls.append("build")
            return {}

    class _Funcs:
        def balanceOf(self, a):
            return _Fn(10**12)

        def matches(self, mid):
            return _Fn(("0x" + "a1" * 20, "0x" + "b2" * 20, 5_000_000, status, 1, 1))

        def approve(self, *a):
            return _Fn(True)

    class _K:
        functions = _Funcs()

    class _Acct:
        def __init__(self, a):
            self.address = a

    monkeypatch.setattr(onchain, "_chain_config", lambda cid: {"escrow": "0xE", "chain_id": cid})
    monkeypatch.setattr(onchain, "_w3", lambda cfg: type("W", (), {"to_checksum_address": staticmethod(lambda a: a)})())
    monkeypatch.setattr(onchain, "_contracts", lambda w3, cfg: (_K(), _K()))
    monkeypatch.setattr(onchain, "load_agent_private_key", lambda aid: aid)
    monkeypatch.setattr(onchain, "_account", lambda pk: _Acct("0x" + ("a1" if pk == "A" else "b2") * 20))
    monkeypatch.setattr(onchain, "_send", lambda *a, **k: calls.append("send") or "0xh")
    with pytest.raises(RuntimeError, match="already"):
        onchain.dual_lock_onchain(
            "agm_l03", agent_a_id="A", agent_b_id="B", agent_a_wallet="0x" + "a1" * 20,
            agent_b_wallet="0x" + "b2" * 20, stake_usdc=Decimal("5"),
        )
    assert "send" not in calls
