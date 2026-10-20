"""Money audit 2026-10 — tournament pot refunds and prize math.

PoCs for AUDIT_2026-10_money.md:

* M-06  /tleave sent twice (aiogram runs handlers concurrently), or a cancel
        racing a leave, refunded the same entry twice out of the shared pot:
        each refund used a random Circle idempotency key.
* M-07  Prize shares were rounded half-even per place and could sum to more
        than the distributable pot; a stale pot_usdc (or the entry x preset
        fallback) could pay out more than the locked entries put in.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

import gaming.src.backend.services.tournament as tmod
from gaming.src.backend.services import tournament_money as tm


class FakeCircle:
    """Circle dedups on the idempotency key; a missing key never dedups."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.by_key: dict[str, dict] = {}

    def transfer_usdc(self, wallet_id, to_address, amount_usdc, *, idempotency_key=None):
        self.calls.append((wallet_id, to_address, amount_usdc, idempotency_key))
        if idempotency_key and idempotency_key in self.by_key:
            return self.by_key[idempotency_key]
        out = {"success": True, "transaction_id": f"tx{len(self.calls)}", "tx_hash": f"0xh{len(self.calls)}"}
        if idempotency_key:
            self.by_key[idempotency_key] = out
        return out

    def wait_for_transaction(self, transaction_id, max_wait_seconds=120):
        return {"success": True, "tx_hash": f"0x{transaction_id}"}

    def sent_from(self, wallet_id: str) -> list[float]:
        """Distinct transfers out of a wallet (Circle collapses equal keys)."""
        seen, out = set(), []
        for wid, _to, amt, key in self.calls:
            if wid != wallet_id:
                continue
            if key is not None and key in seen:
                continue
            seen.add(key)
            out.append(amt)
        return out


@pytest.fixture()
def cup(tmp_path, monkeypatch):
    fake = FakeCircle()
    monkeypatch.setenv("TOURNAMENT_FORCE_JSON", "1")
    monkeypatch.setenv("TOURNAMENTS_ENABLED", "1")
    monkeypatch.setenv("TOURNAMENTS_MONEY_LIVE", "1")
    monkeypatch.setenv("TOURNAMENT_POT_WALLET_ID", "pot-wallet")
    monkeypatch.setenv("TOURNAMENT_POT_ADDRESS", "0x" + "70" * 20)
    monkeypatch.setenv("TOURNAMENT_MONEY_MODE", "transfer")
    monkeypatch.setattr(tmod, "_STORE_PATH", tmp_path / "tournaments.json")
    monkeypatch.setattr(tmod, "_use_supabase", False)
    monkeypatch.setattr(tm, "_circle_for_arc", lambda: (fake, "arc"))

    async def _ok(*_a, **_k):
        return None

    async def _wallet(pid, chain_id="arc"):
        return {"address": f"0xaddr_{pid}", "wallet_id": f"w_{pid}"}

    import gaming.src.backend.services.clawstation_circle as cc

    monkeypatch.setattr(tm, "assert_can_pay_entry", _ok)
    monkeypatch.setattr(cc, "ensure_user_wallet", _wallet)
    t = tmod.create_tournament(
        host_profile_id="host", game_id="mobile.8_ball_pool", preset=4, entry_usdc=5, title="Audit Cup"
    )
    return fake, t["code"]


def test_double_leave_refunds_once(cup, monkeypatch):
    """Two /tleave handlers (or bot + web) in flight while Circle answers."""
    import threading
    import time

    fake, code = cup
    asyncio.run(tmod.join_tournament(code, "eve"))
    real = fake.transfer_usdc

    def _slow(wallet_id, to_address, amount_usdc, *, idempotency_key=None):
        if wallet_id == "pot-wallet":
            time.sleep(0.3)
        return real(wallet_id, to_address, amount_usdc, idempotency_key=idempotency_key)

    monkeypatch.setattr(fake, "transfer_usdc", _slow)
    gate = threading.Barrier(2)
    res: list = []

    def _leave():
        gate.wait()
        try:
            res.append(asyncio.run(tmod.leave_tournament(code, "eve")))
        except Exception as exc:
            res.append(exc)

    ts = [threading.Thread(target=_leave) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert fake.sent_from("pot-wallet") == [5.0], (res, fake.calls)


def test_cancel_after_a_crashed_leave_does_not_refund_again(cup, monkeypatch):
    """The leave's refund went out but the entry was never removed (crash)."""
    fake, code = cup
    asyncio.run(tmod.join_tournament(code, "eve"))
    t = tmod.get_tournament(code)
    entry = t["entries"][0]
    asyncio.run(tm.refund_entry("eve", Decimal("5"), cup_code=code,
                                entry_tx_hash=entry.get("entry_tx_hash"), entry_id=entry.get("id")))
    asyncio.run(tmod.cancel_tournament(code, "ops"))
    assert fake.sent_from("pot-wallet") == [5.0]


def test_cancel_with_a_failed_refund_stays_retryable(cup, monkeypatch):
    fake, code = cup
    asyncio.run(tmod.join_tournament(code, "eve"))
    real = fake.transfer_usdc

    def _down(wallet_id, to_address, amount_usdc, *, idempotency_key=None):
        if wallet_id == "pot-wallet":
            return {"success": False, "error": "circle 503"}
        return real(wallet_id, to_address, amount_usdc, idempotency_key=idempotency_key)

    monkeypatch.setattr(fake, "transfer_usdc", _down)
    with pytest.raises(tmod.TournamentError):
        asyncio.run(tmod.cancel_tournament(code, "ops"))
    assert tmod.get_tournament(code)["status"] != "cancelled"
    monkeypatch.setattr(fake, "transfer_usdc", real)
    asyncio.run(tmod.cancel_tournament(code, "ops"))
    assert tmod.get_tournament(code)["status"] == "cancelled"
    assert fake.sent_from("pot-wallet") == [5.0]


def test_final_pot_is_what_the_locked_entries_paid(cup):
    """Hardening (not a live PoC: start_tournament recounts the pot): the
    real-money pot paid at the final is the sum of the locked entries, never
    a stored running total or entry x preset."""
    import json

    fake, code = cup
    for i in range(4):
        asyncio.run(tmod.join_tournament(code, f"p{i}"))
    tid = tmod.get_tournament(code)["id"]
    data = json.loads(tmod._STORE_PATH.read_text())
    data["tournaments"][tid]["pot_usdc"] = 25.0  # stale: one seat too many
    tmod._STORE_PATH.write_text(json.dumps(data))
    t = tmod.start_tournament(code)
    for m in [m for m in t["bracket"] if m["round"] == 1 and m["status"] == "ready"]:
        t = tmod.report_match_winner(code, m["match_key"], m["player_a"])
    final = next(m for m in t["bracket"] if m["match_key"] == "R2-M0")
    t = tmod.report_match_winner(code, "R2-M0", final["player_a"])
    block = t["payouts"][0]
    assert Decimal(str(block["pot_usdc"])) == Decimal("20")
    paid = sum(Decimal(str(p["amount_usdc"])) for p in block["places"])
    assert paid + Decimal(str(block["platform_fee_usdc"])) <= Decimal("20")


@pytest.mark.parametrize("pot", ["1.09", "1.99", "7.77", "13.13", "199.99"])
def test_prizes_never_exceed_the_distributable_pot(pot):
    block = tmod.compute_payouts(Decimal(pot), 1000, {"1": "a", "2": "b", "3": "c"})[0]
    paid = sum(Decimal(str(p["amount_usdc"])) for p in block["places"])
    assert paid <= Decimal(str(block["distributable_usdc"]))
    assert Decimal(str(block["distributable_usdc"])) - paid < Decimal("0.01")


def test_every_pot_from_1_to_199_dollars_conserves():
    for cents in range(100, 20000, 1):
        pot = Decimal(cents) / 100
        block = tmod.compute_payouts(pot, 1000, {"1": "a", "2": "b", "3": "c"})[0]
        paid = sum(Decimal(str(p["amount_usdc"])) for p in block["places"])
        assert paid <= Decimal(str(block["distributable_usdc"])), pot
