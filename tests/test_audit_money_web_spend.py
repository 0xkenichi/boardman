"""Money audit 2026-10 — web spends off the play balance (rematch_web).

PoCs for AUDIT_2026-10_money.md:

* M-01  Approved web bets / LP deposits never re-checked the play balance and
        took the stake with an unconditional ``add_adjust`` when the Circle
        pull failed, so N approvals created while the balance covered one
        stake booked N tickets and left the play balance negative (betting on
        credit: keep the win, walk away from the loss).
* M-02  LP withdraw sent real USDC before (and without) recording the
        withdrawal against the LP position, and sent it on a *pending*
        approval: two concurrent requests both passed the cap and both sent.
"""
from __future__ import annotations

import asyncio
import threading
import time
from decimal import Decimal

import pytest

MASTER = "sk_master_test"
ADDR = "0x" + "ab" * 20


class FakePlayWallet:
    """Circle play wallet: on-chain USDC that a transfer can never overdraw."""

    def __init__(self, chain: str) -> None:
        self.chain = Decimal(chain)
        self.lock = threading.Lock()
        self.pulls: list[Decimal] = []

    async def pull(self, profile_id, amount, **_kw):
        amt = Decimal(str(amount))
        with self.lock:
            if self.chain < amt:
                raise ValueError(f"Circle transfer failed: wallet has {self.chain}, need {amt}")
            self.chain -= amt
            self.pulls.append(amt)
        return {"success": True, "tx_hash": "0xpull"}


@pytest.fixture()
def web(monkeypatch):
    from gaming.src.backend.api import rematch_web
    from gaming.src.backend.services import clawstation_circle, play_adjust, tx_approval

    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    wallet = FakePlayWallet("4")

    async def _strict(user_id, chain_id=None):
        return wallet.chain, None

    async def _bal(user_id, chain_id=None):
        return max(Decimal("0"), wallet.chain + play_adjust.get_adjust(user_id))

    async def _summary(user_id, chain_id=None):
        adj = play_adjust.get_adjust(user_id)
        return {
            "spendable_usdc": max(Decimal("0"), wallet.chain + adj),
            "chain_usdc": wallet.chain,
            "adjust_usdc": adj,
            "ledger_usdc": Decimal("0"),
            "address": ADDR,
            "chain_id": "arc",
        }

    monkeypatch.setattr(clawstation_circle, "get_usdc_balance_strict", _strict)
    monkeypatch.setattr(clawstation_circle, "get_usdc_balance", _bal)
    monkeypatch.setattr(clawstation_circle, "get_balance_summary", _summary)
    monkeypatch.setattr(rematch_web, "_pull_play_usdc", wallet.pull)

    rows: dict[str, dict] = {}
    monkeypatch.setattr(tx_approval, "get_approval_row", lambda aid: rows.get(aid))

    def _claim(aid):
        row = rows.get(aid)
        if not row or row["status"] != "approved":
            return None
        row["status"] = "applied"
        return row

    def _store(aid, result):
        rows[aid]["payload"]["_result"] = result

    monkeypatch.setattr(tx_approval, "claim_apply", _claim)
    monkeypatch.setattr(tx_approval, "store_apply_result", _store)
    return {"wallet": wallet, "rows": rows, "mod": rematch_web}


def _house_match() -> str:
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    m = get_house().open_match(
        agent_a_id="agent_raja_kia_alekhine", agent_b_id="agent_nero_sicilian_french", stake_usdc=5
    )
    return m["match_id"]


def _tickets(match_id: str, bettor: str) -> list[dict]:
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    book = SpectatorBook().get(match_id) or {}
    return [b for b in book.get("bets") or [] if b.get("bettor_id") == bettor]


# ── M-01 ─────────────────────────────────────────────────────────────────────


def test_two_approved_bets_cannot_spend_one_balance_twice(web):
    from gaming.src.backend.services import play_adjust

    mid = _house_match()
    rw = web["mod"]
    # Both approvals were requested while the play balance ($4) covered one.
    for aid in ("ap1", "ap2"):
        web["rows"][aid] = {"status": "approved", "profile_id": "fan1",
                            "payload": {"amount": 4, "side": "a", "match_id": mid}}
    summary = asyncio.run(__import__(
        "gaming.src.backend.services.clawstation_circle", fromlist=["x"]).get_balance_summary("fan1"))

    outs = [
        asyncio.run(rw._apply_approved_spectator_bet(
            approval_id=aid, profile_id="fan1", match_id=mid, side="a", amount=4.0, summary=summary))
        for aid in ("ap1", "ap2")
    ]

    assert outs[0]["success"] is True
    assert outs[1]["success"] is False, outs[1]
    assert len(_tickets(mid, "fan1")) == 1
    # Never below zero: chain 0 after the pull, nothing owed.
    assert web["wallet"].chain + play_adjust.get_adjust("fan1") == Decimal("0")


def test_bet_falls_back_to_the_play_overlay_only_when_it_covers_the_stake(web):
    """Positive overlay (an unpaid win) may fund a stake the chain cannot."""
    from gaming.src.backend.services import play_adjust

    mid = _house_match()
    rw = web["mod"]
    web["wallet"].chain = Decimal("0")
    play_adjust.apply_once("fan2", Decimal("6"), key="seed-win")
    for aid, amt in (("ap3", 5), ("ap4", 5)):
        web["rows"][aid] = {"status": "approved", "profile_id": "fan2",
                            "payload": {"amount": amt, "side": "b", "match_id": mid}}
    first = asyncio.run(rw._apply_approved_spectator_bet(
        approval_id="ap3", profile_id="fan2", match_id=mid, side="b", amount=5.0, summary={}))
    second = asyncio.run(rw._apply_approved_spectator_bet(
        approval_id="ap4", profile_id="fan2", match_id=mid, side="b", amount=5.0, summary={}))
    assert first["success"] is True
    assert second["success"] is False
    assert play_adjust.get_adjust("fan2") == Decimal("1")
    assert len(_tickets(mid, "fan2")) == 1


def test_direct_bets_racing_never_overdraw(web, monkeypatch):
    """'always' mode: concurrent requests each saw $4 spendable."""
    from fastapi.testclient import TestClient

    from gaming.src.backend.main import create_app
    from gaming.src.backend.services import play_adjust, tx_approval

    mid = _house_match()

    async def _always(*_a, **_k):
        return {"status": "approved", "mode": "always"}

    monkeypatch.setattr(tx_approval, "start_approval", _always)
    gate = threading.Barrier(3)
    real_pull = web["wallet"].pull

    async def _slow_pull(profile_id, amount, **kw):
        await asyncio.sleep(0.2)  # both requests are past the balance check
        return await real_pull(profile_id, amount, **kw)

    monkeypatch.setattr(web["mod"], "_pull_play_usdc", _slow_pull)
    client = TestClient(create_app())
    results = []

    def _bet():
        gate.wait()
        r = client.post(
            "/api/rematch/web/spectator/bet",
            json={"profile_id": "fan3", "amount": 4, "side": "a", "match_id": mid},
            headers={"X-Rematch-Key": MASTER},
        )
        results.append(r.json())

    ts = [threading.Thread(target=_bet) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    ok = [r for r in results if r.get("success")]
    assert len(ok) == 1, results
    assert len(_tickets(mid, "fan3")) == 1
    assert web["wallet"].chain + play_adjust.get_adjust("fan3") >= Decimal("0")


def test_approved_lp_deposit_cannot_overdraw(web):
    from gaming.src.backend.services import play_adjust
    from gaming.src.stack.agentic.economy.lp import AgentLPPool

    rw = web["mod"]
    web["wallet"].chain = Decimal("10")
    for aid in ("lp1", "lp2"):
        web["rows"][aid] = {"status": "approved", "profile_id": "fan4",
                            "payload": {"amount": 10, "agent_id": "agent_raja_kia_alekhine"}}
    stale = {"spendable_usdc": Decimal("10"), "ledger_usdc": Decimal("0"), "address": ADDR}
    outs = [
        asyncio.run(rw._apply_approved_lp(approval_id=aid, profile_id="fan4",
                                          agent_id="agent_raja_kia_alekhine", agent_name="", amount=10.0,
                                          summary=stale))
        for aid in ("lp1", "lp2")
    ]
    assert [o["success"] for o in outs] == [True, False], outs
    pos = AgentLPPool().get_pool("agent_raja_kia_alekhine")["positions"]["fan4"]
    assert Decimal(pos["amount"]) == Decimal("10")
    assert web["wallet"].chain + play_adjust.get_adjust("fan4") == Decimal("0")


# ── M-02 ─────────────────────────────────────────────────────────────────────


@pytest.fixture()
def lp_withdraw(web, monkeypatch):
    from gaming.src.stack.agentic import ledger, spectator_onchain
    from gaming.src.stack.agentic.economy.lp import AgentLPPool
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()
    agent = reg.get_agent("agent_raja_kia_alekhine")
    ledger.credit(agent["wallet_address"], Decimal("1000"), reason="fund")
    AgentLPPool().deposit("agent_raja_kia_alekhine", lp_id="lpfan", amount_usdc=Decimal("10"))
    sent: list[Decimal] = []

    def _send(user, amount, **_kw):
        time.sleep(0.2)
        sent.append(Decimal(str(amount)))
        return {"tx_hash": f"0xsend{len(sent)}", "explorer": ""}

    monkeypatch.setattr(spectator_onchain, "refund_float_to_user", _send)
    return sent


def _withdraw(client, amount=10):
    return client.post(
        "/api/rematch/web/spectator/lp/withdraw",
        json={"profile_id": "lpfan", "amount": amount, "agent_id": "agent_raja_kia_alekhine"},
        headers={"X-Rematch-Key": MASTER},
    )


def test_lp_withdraw_never_sends_on_a_pending_approval(lp_withdraw, monkeypatch):
    from fastapi.testclient import TestClient

    from gaming.src.backend.main import create_app
    from gaming.src.backend.services import tx_approval

    async def _pending(*_a, **_k):
        return {"status": "pending", "approval_id": "apw", "mode": "ask"}

    monkeypatch.setattr(tx_approval, "start_approval", _pending)
    r = _withdraw(TestClient(create_app()))
    assert lp_withdraw == [], "USDC left the House float without the LP's Yes"
    assert r.json().get("success") is not True


def test_lp_withdraw_race_sends_at_most_the_position(lp_withdraw, monkeypatch):
    from fastapi.testclient import TestClient

    from gaming.src.backend.main import create_app
    from gaming.src.backend.services import tx_approval
    from gaming.src.stack.agentic.economy.lp import AgentLPPool

    async def _approved(*_a, **_k):
        return {"status": "approved", "mode": "always"}

    monkeypatch.setattr(tx_approval, "start_approval", _approved)
    client = TestClient(create_app())
    gate = threading.Barrier(2)
    codes = []

    def _go():
        gate.wait()
        codes.append(_withdraw(client).status_code)

    ts = [threading.Thread(target=_go) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(lp_withdraw, Decimal("0")) <= Decimal("10"), (lp_withdraw, codes)
    pos = AgentLPPool().get_pool("agent_raja_kia_alekhine")["positions"]["lpfan"]
    assert Decimal(pos["amount"]) == Decimal("10") - sum(lp_withdraw, Decimal("0"))


def test_lp_withdraw_send_failure_restores_the_position(lp_withdraw, monkeypatch):
    from fastapi.testclient import TestClient

    from gaming.src.backend.main import create_app
    from gaming.src.backend.services import tx_approval
    from gaming.src.stack.agentic import spectator_onchain
    from gaming.src.stack.agentic.economy.lp import AgentLPPool

    async def _approved(*_a, **_k):
        return {"status": "approved", "mode": "always"}

    def _boom(*_a, **_k):
        raise spectator_onchain.SpectatorOnchainError("float empty")

    monkeypatch.setattr(tx_approval, "start_approval", _approved)
    monkeypatch.setattr(spectator_onchain, "refund_float_to_user", _boom)
    r = _withdraw(TestClient(create_app()))
    assert r.status_code >= 400 or r.json().get("success") is False
    pos = AgentLPPool().get_pool("agent_raja_kia_alekhine")["positions"]["lpfan"]
    assert Decimal(pos["amount"]) == Decimal("10")


@pytest.mark.parametrize("raw", ["NaN", "nan", "inf", "-Infinity"])
def test_non_finite_amounts_are_refused(web, raw):
    """float('nan') passed every `amount < x` guard and reached the overlay."""
    from fastapi.testclient import TestClient

    from gaming.src.backend.main import create_app

    client = TestClient(create_app())
    for path, body in (
        ("/api/rematch/web/spectator/bet", {"profile_id": "fan5", "amount": raw, "side": "a", "match_id": "x"}),
        ("/api/rematch/web/spectator/lp", {"profile_id": "fan5", "amount": raw, "agent_id": "agent_raja_kia_alekhine"}),
        ("/api/rematch/web/spectator/lp/withdraw", {"profile_id": "fan5", "amount": raw,
                                                    "agent_id": "agent_raja_kia_alekhine"}),
    ):
        r = client.post(path, json=body, headers={"X-Rematch-Key": MASTER})
        assert r.status_code == 400, (path, raw, r.status_code, r.text)
