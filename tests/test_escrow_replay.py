"""Replay harness — the automated core of the mainnet go-live gate.

Bar: ``BOARDMAN_REPLAY_CYCLES`` full match lifecycles must converge with
zero stuck funds and zero double-payments. Shapes per cycle:

  A. create → join → resolve    (happy path payout)
  B. create → join → cancel     (mutual refund)
  C. create → creator_locked    (ghosted → sweep auto-refund)

The real ``clawstation_escrow`` + ``bot.jobs.expiry`` code runs unmodified
on top of an in-memory ledger; only I/O seams are patched. The fake chain
mirrors BoardmanEscrow.sol exactly (OPEN → LOCKED → RESOLVED/CANCELLED,
freshness on player1, web3-style raises at the BL seam, Circle-style
revert dicts at the wallet seam). Chaos tests inject crashes between the
chain move and the DB write and assert the flow *converges* on retry.

Run with BOARDMAN_REPLAY_CYCLES=1000 for the go-live evidence run.
"""
from __future__ import annotations

import hashlib
import os
import sys
import types
from collections import defaultdict
from decimal import Decimal
from typing import Optional

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CYCLES = int(os.getenv("BOARDMAN_REPLAY_CYCLES", "60"))
STAKE = Decimal("5")
FEE = STAKE * 2 * Decimal("0.07")
PAYOUT = STAKE * 2 - FEE

ESCROW_ADDR = "0xescrow"
FEE_RECIPIENT = "fee_recipient"
USDC = "USDC_CONTRACT"


# ────────────────────────────────────────────────────────────────────────────
# In-memory ledger + fake chain (mirrors BoardmanEscrow.sol)
# ────────────────────────────────────────────────────────────────────────────


class Ledger:
    def __init__(self):
        self.balances: dict[str, Decimal] = defaultdict(Decimal)
        self.txs: list[dict] = []
        self._next = 0

    def send(self, frm: str, to: str, amount: Decimal, tag: str) -> str:
        assert self.balances[frm] >= amount, f"{frm} overdrawn: {tag}"
        self.balances[frm] -= amount
        self.balances[to] += amount
        self._next += 1
        self.txs.append(
            {"tx_hash": f"0x{self._next:064x}", "frm": frm, "to": to, "amount": amount, "tag": tag}
        )
        return self.txs[-1]["tx_hash"]

    def movements(self, tag: str) -> list[dict]:
        return [t for t in self.txs if t["tag"] == tag]

    def sum(self, tag: str) -> Decimal:
        return sum((t["amount"] for t in self.movements(tag)), Decimal("0"))


LEDGER = Ledger()
CHAINS: dict[str, "FakeMatch"] = {}
WALLETS: dict[str, str] = {}


def _wallet_for(user_id: str) -> str:
    return WALLETS.setdefault(user_id, f"0xw_{user_id}")


class FakeMatch:
    """Mirrors BoardmanEscrow.Match: status OPEN once creator staked."""

    def __init__(self, match_id: str):
        self.match_id = match_id
        self.stake: Optional[Decimal] = None
        self.p1: Optional[str] = None
        self.p2: Optional[str] = None
        self.status: str = "OPEN"


def _b32(match_id: str) -> str:
    return "0x" + hashlib.sha256(match_id.encode()).hexdigest()


class FakeCircle:
    """User-side wallet ops — Circle seam: failures are dicts, not raises."""

    def __init__(self, sb: "FakeSupabase"):
        self.sb = sb

    def approve_usdc_transfer(self, wallet_id, amount, spender):
        if self.sb.failpoints["approve"] > 0:
            self.sb.failpoints["approve"] -= 1
            raise RuntimeError("injected approve failure")
        return {"success": True, "transaction_id": f"ap-{wallet_id}"}

    async def wait_for_transaction_async(self, tx_id, max_wait_seconds=120):
        return {"success": True, "tx_hash": f"0x{tx_id}", "time_waited": 1}

    def execute_contract_function(self, wallet_id, contract, signature, args):
        assert contract == ESCROW_ADDR
        if self.sb.failpoints["contract_call"] > 0:
            self.sb.failpoints["contract_call"] -= 1
            return {"success": False, "error": "injected contract failure"}
        m = CHAINS.setdefault(args[0], FakeMatch(args[0]))
        if signature == "createMatch(bytes32,uint256)":
            if m.p1 is not None:  # contract: freshness on player1
                return {"success": False, "error": "MatchAlreadyExists"}
            stake = Decimal(int(args[1])) / Decimal(10**6)
            LEDGER.send(wallet_id, ESCROW_ADDR, stake, "lock")
            m.stake, m.p1, m.status = stake, wallet_id, "OPEN"
        elif signature == "joinMatch(bytes32)":
            if m.status != "OPEN" or m.p2 is not None:
                return {"success": False, "error": "MatchNotOpen"}
            LEDGER.send(wallet_id, ESCROW_ADDR, m.stake, "lock")
            m.p2, m.status = wallet_id, "LOCKED"
        else:
            raise AssertionError(signature)
        return {"success": True, "transaction_id": f"cx-{signature[:4]}-{args[0][:8]}"}


class FakeBL:
    """Resolver-side chain ops — web3 seam: reverts RAISE, like the real layer."""

    def __init__(self, sb: "FakeSupabase"):
        self.sb = sb

    async def resolve_match_onchain(self, match_id, winner_address):
        m = CHAINS[_b32(match_id)]
        if m.status != "LOCKED":
            raise RuntimeError(f"revert: cannot resolve from {m.status}")
        pot = m.stake * 2
        fee = pot * Decimal("0.07")
        LEDGER.send(ESCROW_ADDR, winner_address, pot - fee, "payout")
        LEDGER.send(ESCROW_ADDR, FEE_RECIPIENT, fee, "fee")
        m.status = "RESOLVED"
        return {"tx_hash": f"0xres{match_id[:8]}", "block": 1, "gas_used": 21000}

    async def cancel_match_onchain(self, match_id):
        m = CHAINS[_b32(match_id)]
        if m.status == "OPEN":  # ghosted: creator gets their stake back
            LEDGER.send(ESCROW_ADDR, m.p1, m.stake, "refund")
        elif m.status in ("LOCKED", "DISPUTED"):
            LEDGER.send(ESCROW_ADDR, m.p1, m.stake, "refund")
            LEDGER.send(ESCROW_ADDR, m.p2, m.stake, "refund")
        else:
            raise RuntimeError(f"revert: cannot cancel from {m.status}")
        m.status = "CANCELLED"
        return {"tx_hash": f"0xcxl{match_id[:8]}", "block": 1, "gas_used": 21000}

    def get_match_status(self, match_id):
        m = CHAINS.get(_b32(match_id))
        if m is None:
            raise KeyError("no match")
        return {
            "player1": m.p1,
            "player2": m.p2,
            "stake_per_player": float(m.stake or 0),
            "status": m.status,
        }

    def get_contract_usdc_balance(self):
        return float(
            LEDGER.sum("lock") - LEDGER.sum("payout") - LEDGER.sum("fee") - LEDGER.sum("refund")
        )


# ────────────────────────────────────────────────────────────────────────────
# Fake supabase: gaming.challenges + gaming.escrow_audit
# ────────────────────────────────────────────────────────────────────────────


class FakeSupabase:
    def __init__(self):
        self.challenges: dict[str, dict] = {}
        self.audits: list[dict] = []
        self.failpoints: dict[str, int] = defaultdict(int)

    def schema(self, name):
        return self

    def table(self, name):
        return _Q(self, name)

    def insert_challenge(self, row: dict):
        self.challenges[row["id"]] = dict(row)

    def fail_next(self, point: str, times: int = 1):
        self.failpoints[point] += times


class _Q:
    def __init__(self, sb: FakeSupabase, table: str):
        self.sb, self.table = sb, table
        self.op, self.filters, self.payload = "select", [], None
        self.single = False

    def select(self, cols="*"):
        self.op = "select"
        return self

    def insert(self, data):
        self.op = "insert"
        self.payload = data
        return self

    def update(self, data):
        self.op = "update"
        self.payload = data
        return self

    def eq(self, c, v):
        self.filters.append(("eq", c, v))
        return self

    def in_(self, c, vs):
        self.filters.append(("in", c, tuple(vs)))
        return self

    def lt(self, c, v):
        self.filters.append(("lt", c, v))
        return self

    def maybe_single(self):
        self.single = True
        return self

    def limit(self, n):
        return self

    def execute(self):
        def match(r):
            for kind, c, v in self.filters:
                if kind == "eq" and r.get(c) != v:
                    return False
                if kind == "lt" and not (str(r.get(c, "")) < str(v)):
                    return False
                if kind == "in" and r.get(c) not in v:
                    return False
            return True

        if self.table == "challenges":
            if self.op == "update":
                for r in self.sb.challenges.values():
                    if match(r):
                        r.update(self.payload or {})
                return SimpleNamespace(data=[])
            rows = [dict(r) for r in self.sb.challenges.values() if match(r)]
            if self.single:
                return SimpleNamespace(data=rows[0] if rows else None)
            return SimpleNamespace(data=rows)
        if self.table == "escrow_audit":
            if self.op == "insert":
                self.sb.audits.append(dict(self.payload))
                return SimpleNamespace(data=[self.payload])
            return SimpleNamespace(data=[dict(a) for a in self.sb.audits if match(a)])
        raise AssertionError(f"unexpected table {self.table}")


from types import SimpleNamespace  # noqa: E402  (used above)


# ────────────────────────────────────────────────────────────────────────────
# Wiring: real escrow code over the fakes
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def rig(monkeypatch):
    import gaming.src.backend.services.clawstation_escrow as esc

    sb = FakeSupabase()
    LEDGER.__init__()
    CHAINS.clear()
    WALLETS.clear()
    # Faucet: every player is funded when their wallet is prepared
    LEDGER.balances["faucet"] = Decimal("10000000")

    monkeypatch.setattr(esc, "_get_supabase", lambda: sb)
    monkeypatch.setattr(esc, "_circle", lambda chain_id: FakeCircle(sb))
    monkeypatch.setattr(esc, "_prepare_wallet", _fake_prepare_wallet)
    monkeypatch.setattr(esc, "default_chain_id", lambda: "arc")
    monkeypatch.setattr(esc, "normalize_chain_id", lambda cid="": "arc")
    monkeypatch.setattr(esc, "get_escrow_address", lambda cid: ESCROW_ADDR)
    monkeypatch.setattr(esc, "get_circle_blockchain", lambda cid: "ARC-TESTNET")
    monkeypatch.setattr(esc, "get_usdc_address", lambda cid: USDC)
    monkeypatch.setattr(esc, "get_circle_usdc_token_id", lambda cid: "tok")
    monkeypatch.setattr(esc, "get_rpc_url", lambda cid: "http://rpc")
    monkeypatch.setattr(esc, "get_explorer_tx", lambda cid, h="": f"https://x/{h}")

    # blockchain_layer stub at the sys.modules seam (escrow + reconciliation
    # both do a lazy `from backend.blockchain_layer import ...`).
    bl_stub = types.ModuleType("backend.blockchain_layer")
    bl_stub.get_blockchain_layer_for_chain = lambda cid: FakeBL(sb)
    monkeypatch.setitem(sys.modules, "backend.blockchain_layer", bl_stub)
    return esc, sb


async def _fake_prepare_wallet(user_id, chain_id):
    addr = _wallet_for(user_id)
    wid = f"w_{user_id}"  # Circle signs from the wallet id — fund that
    if LEDGER.balances["faucet"] >= Decimal("1000"):
        LEDGER.send("faucet", wid, Decimal("1000"), "faucet")
    return wid, addr


def _mk_challenge(sb: FakeSupabase, cid: str):
    sb.insert_challenge(
        {
            "id": cid,
            "issuer_id": f"creator_{cid}",
            "target_id": f"opponent_{cid}",
            "stake_amount": float(STAKE),
            "status": "accepted",
            "game_type": "EA FC",
            "theme": "private",
            "settlement_chain": "arc",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


async def _do_locks(esc, cid: str):
    await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)
    await esc.approve_and_join_match(f"opponent_{cid}", cid, STAKE)


# ────────────────────────────────────────────────────────────────────────────
# Shape A: create → join → resolve
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_resolve_cycles(rig):
    esc, sb = rig
    for i in range(CYCLES):
        cid = f"res-{i}"
        _mk_challenge(sb, cid)
        await _do_locks(esc, cid)
        assert sb.challenges[cid]["status"] == "locked"

        res = await esc.resolve_match(cid, _wallet_for(f"opponent_{cid}"))
        assert res["success"] is True
        assert sb.challenges[cid]["status"] == "resolved"

    # ── Invariants over the whole run ──
    assert LEDGER.sum("lock") == STAKE * 2 * CYCLES
    assert LEDGER.sum("payout") == PAYOUT * CYCLES
    assert LEDGER.sum("fee") == FEE * CYCLES
    # Conservation: every locked dollar is paid out, kept as fee, or refunded
    assert LEDGER.sum("lock") == LEDGER.sum("payout") + LEDGER.sum("fee") + LEDGER.sum("refund")
    # Exactly one payout + one fee per cycle — no double-payments
    assert len(LEDGER.movements("payout")) == CYCLES
    assert len(LEDGER.movements("fee")) == CYCLES
    # Escrow fully drained; DB converged — nothing stuck
    assert FakeBL(sb).get_contract_usdc_balance() == 0
    stuck = [c for c in sb.challenges.values() if c["status"] != "resolved"]
    assert stuck == []

    # Re-resolving a completed match is rejected (idempotency at the guard)
    with pytest.raises(esc.EscrowError):
        await esc.resolve_match("res-0", _wallet_for("opponent_res-0"))
    assert len(LEDGER.movements("payout")) == CYCLES


# ────────────────────────────────────────────────────────────────────────────
# Shape B: create → join → cancel
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_cancel_cycles(rig):
    esc, sb = rig
    for i in range(CYCLES):
        cid = f"cxl-{i}"
        _mk_challenge(sb, cid)
        await _do_locks(esc, cid)
        res = await esc.cancel_match(cid)
        assert res["success"] is True
        assert sb.challenges[cid]["status"] == "cancelled"

    refunds = LEDGER.movements("refund")
    assert len(refunds) == 2 * CYCLES
    assert LEDGER.sum("refund") == STAKE * 2 * CYCLES
    for t in refunds:
        assert t["amount"] == STAKE and t["frm"] == ESCROW_ADDR
    assert FakeBL(sb).get_contract_usdc_balance() == 0

    # Re-cancelling a completed match is rejected; nobody refunded twice
    with pytest.raises(esc.EscrowError):
        await esc.cancel_match("cxl-0")
    assert len(LEDGER.movements("refund")) == 2 * CYCLES


# ────────────────────────────────────────────────────────────────────────────
# Shape C: creator_locked → ghosted → sweep auto-refund
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_ghosted_sweep_cycles(rig, monkeypatch):
    esc, sb = rig
    from gaming.src.bot.jobs.expiry import sweep_stale_creator_locks

    sent: list[tuple] = []

    async def _notify(uid, text, **kw):
        sent.append((uid, text))

    monkeypatch.setattr("gaming.src.bot.utils.notify.notify_user", _notify)
    monkeypatch.setattr("gaming.src.bot.jobs.expiry._get_supabase", lambda: sb)

    for i in range(CYCLES):
        cid = f"gho-{i}"
        _mk_challenge(sb, cid)
        await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)
        assert sb.challenges[cid]["status"] == "creator_locked"
        sb.challenges[cid]["expires_at"] = "2000-01-01T00:00:00+00:00"

    swept = await sweep_stale_creator_locks()
    assert swept == CYCLES

    # Exactly one refund per ghosted match — the creator's stake only
    refunds = LEDGER.movements("refund")
    assert len(refunds) == CYCLES
    assert LEDGER.sum("refund") == STAKE * CYCLES
    assert FakeBL(sb).get_contract_usdc_balance() == 0
    assert all(c["status"] == "cancelled" for c in sb.challenges.values())
    assert len([1 for uid, _ in sent if str(uid).startswith("creator_gho-")]) == CYCLES

    # Sweeping again is a no-op
    assert await sweep_stale_creator_locks() == 0
    assert len(LEDGER.movements("refund")) == CYCLES


# ────────────────────────────────────────────────────────────────────────────
# Guards: the checks that make the 1,000,000 bar credible
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guard_join_requires_creator_locked(rig):
    esc, sb = rig
    cid = "guard-1"
    _mk_challenge(sb, cid)
    with pytest.raises(esc.EscrowError, match="Creator must lock"):
        await esc.approve_and_join_match(f"opponent_{cid}", cid, STAKE)
    assert sb.audits == []
    assert LEDGER.txs == []


@pytest.mark.asyncio
async def test_guard_double_lock_rejected(rig):
    esc, sb = rig
    cid = "guard-2"
    _mk_challenge(sb, cid)
    await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)
    with pytest.raises(esc.EscrowError, match="already locked"):
        await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)
    assert len(LEDGER.movements("lock")) == 1


# ────────────────────────────────────────────────────────────────────────────
# Chaos: crashes between chain and DB must converge
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chaos_lock_failure_leaves_no_state(rig):
    """Approve raises mid-flight → nothing recorded; retry succeeds cleanly."""
    esc, sb = rig
    cid = "chaos-1"
    _mk_challenge(sb, cid)
    sb.fail_next("approve", times=1)

    with pytest.raises(RuntimeError, match="injected approve failure"):
        await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)

    assert sb.audits == []
    assert sb.challenges[cid]["status"] == "accepted"
    assert LEDGER.sum("lock") == 0  # nothing locked, faucet noise aside

    await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)
    assert sb.challenges[cid]["status"] == "creator_locked"
    assert LEDGER.sum("lock") == STAKE


@pytest.mark.asyncio
async def test_chaos_crash_between_create_and_db(rig):
    """createMatch lands on-chain, process dies before the DB write.

    The DB forgets everything (audits wiped, status rewound, tx ids gone).
    The user retries the lock: the contract reverts (already created), the
    on-chain read proves the match exists with the same stake, and the flow
    converges instead of wedging. No second lock.
    """
    esc, sb = rig
    cid = "crash-1"
    _mk_challenge(sb, cid)
    await _do_locks(esc, cid)
    assert LEDGER.sum("lock") == STAKE * 2

    # ── crash: DB loses all memory of the locks ──
    sb.audits.clear()
    for row in sb.challenges.values():
        row.update(
            {
                "status": "accepted",
                "creator_lock_tx_id": None,
                "creator_lock_tx_hash": None,
                "opponent_lock_tx_id": None,
                "opponent_lock_tx_hash": None,
            }
        )

    await esc.approve_and_create_match(f"creator_{cid}", cid, STAKE)
    await esc.approve_and_join_match(f"opponent_{cid}", cid, STAKE)

    assert LEDGER.sum("lock") == STAKE * 2  # no double-lock
    assert sb.challenges[cid]["status"] == "locked"
    assert any((a.get("metadata") or {}).get("recovered") for a in sb.audits)


@pytest.mark.asyncio
async def test_chaos_crash_between_payout_and_db(rig):
    """resolveMatch pays the winner, process dies before the DB flips.

    On retry the chain says RESOLVED → converge DB + audits, never pay twice.
    """
    esc, sb = rig
    cid = "crash-2"
    _mk_challenge(sb, cid)
    await _do_locks(esc, cid)
    sb.challenges[cid]["status"] = "submitted"

    res = await esc.resolve_match(cid, _wallet_for(f"opponent_{cid}"))
    assert res["success"] is True
    assert len(LEDGER.movements("payout")) == 1

    # ── crash: DB loses the payout ──
    sb.audits.clear()
    sb.challenges[cid]["status"] = "submitted"

    res2 = await esc.resolve_match(cid, _wallet_for(f"opponent_{cid}"))
    assert res2["success"] is True
    assert res2.get("recovered") is True
    assert len(LEDGER.movements("payout")) == 1  # still exactly one
    assert sb.challenges[cid]["status"] == "resolved"
    assert FakeBL(sb).get_contract_usdc_balance() == 0
    kinds = {a["movement"] for a in sb.audits}
    assert {"payout", "fee"} <= kinds


@pytest.mark.asyncio
async def test_chaos_crash_between_refund_and_db(rig):
    """cancelMatch refunds on-chain, process dies before the DB write."""
    esc, sb = rig
    cid = "crash-3"
    _mk_challenge(sb, cid)
    await _do_locks(esc, cid)
    assert LEDGER.sum("lock") == STAKE * 2

    res = await esc.cancel_match(cid)
    assert res["success"] is True
    assert len(LEDGER.movements("refund")) == 2

    # crash: DB forgets the refund
    sb.audits.clear()
    sb.challenges[cid]["status"] = "locked"

    res2 = await esc.cancel_match(cid)
    assert res2["success"] is True
    assert res2.get("recovered") is True
    assert len(LEDGER.movements("refund")) == 2  # no double-refund
    assert sb.challenges[cid]["status"] == "cancelled"
    assert LEDGER.balances[ESCROW_ADDR] == 0


# ────────────────────────────────────────────────────────────────────────────
# Reconciliation: DB vs on-chain (the go-live gate's daily check)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconciliation_clean_and_drift(rig):
    esc, sb = rig
    from gaming.src.backend.services.escrow_reconciliation import reconcile_escrow

    # One fully locked match + one ghosted creator lock → chain holds 3×STAKE
    _mk_challenge(sb, "rec-1")
    await _do_locks(esc, "rec-1")
    _mk_challenge(sb, "rec-2")
    await esc.approve_and_create_match("creator_rec-2", "rec-2", STAKE)

    report = await reconcile_escrow(chain_ids=["arc"], sb=sb, notify=_noop_notify)
    assert report["ok"] is True, report
    arc = report["chains"]["arc"]
    assert arc["db_expected_usdc"] == pytest.approx(3 * float(STAKE))
    assert arc["contract_balance_usdc"] == pytest.approx(3 * float(STAKE))
    assert arc["drift"] == []

    # Force drift: DB thinks rec-1 is locked but chain shows CANCELLED
    CHAINS[_b32("rec-1")].status = "CANCELLED"
    report2 = await reconcile_escrow(chain_ids=["arc"], sb=sb, notify=_noop_notify)
    assert report2["ok"] is False
    assert report2["chains"]["arc"]["drift"], "held mismatch must be flagged"
    assert report2["alerts"], "alert must be raised"


async def _noop_notify(msg):
    return None
