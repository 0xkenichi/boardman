"""Spectator books conserve money across every rail.

A ticket's stake is taken on one rail and paid back on the same rail:

* ledger   (builder / stack API) — place_bet debits the agentic ledger with
           the ticket; payouts and refunds are agentic-ledger credits;
* profile  (web / Telegram)      — rematch_web takes the stake off the play
           balance (play_adjust here); payouts go back through play_adjust.

Before this, settlement credited the agentic ledger for every winning ticket
and every draw win — including web tickets it never debited (they were paid
twice: ledger + play_adjust) and builder tickets that were never debited at
all. Here the whole system is summed: agentic-ledger balances + stakes held in
escrow + play-wallet overlays. Across a full table — lock, bets, settle (win,
draw, nobody-backed-it) or void — that total does not move; the only thing
the house keeps is the explicit fee, booked to the treasury wallet.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic import matches as matches_mod
from gaming.src.stack.agentic.db import leases
from gaming.src.stack.agentic.db.money import to_micro
from gaming.src.stack.agentic.db.tables import MATCHES

RAJA = "agent_raja_kia_alekhine"
NERO = "agent_nero_sicilian_french"

LEDGER_FANS = {"fan_l1": ("a", "1.5"), "fan_l2": ("b", "2"), "fan_l3": ("draw", "0.5")}
PROFILE_FANS = {"fan_p1": ("a", "0.75"), "fan_p2": ("draw", "1.25"), "fan_p3": ("b", "0.333333")}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_BET_WINDOW_SEC", "0")
    monkeypatch.setattr(matches_mod, "_notify_spectator_outcomes", lambda *a, **k: None)
    monkeypatch.setattr(matches_mod, "_SETTLE_STEP_HOOK", None)
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry.cache_clear()
    get_match_service.cache_clear()
    leases.forget_local_state()
    yield
    leases.forget_local_state()


def _adjust_total() -> int:
    from gaming.src.stack.agentic.store import load_json

    profiles = load_json("play_adjust.json", {"profiles": {}}).get("profiles") or {}
    return sum(to_micro(r.get("adjust") or "0") for r in profiles.values())


def _escrow_held() -> int:
    return sum(
        2 * to_micro(e.get("stake_usdc") or "0")
        for e in ledger.escrows({"locked"}).values()
    )


def _books_held() -> int:
    """Stakes and seeds sitting in books that have not paid out yet."""
    from gaming.src.stack.agentic.economy.spectator import all_books, funded_seeds_from_ledger

    held = 0
    for book in all_books().values():
        if book.get("status") in {"settled", "void"} or book.get("onchain"):
            continue
        held += sum(to_micro(b.get("amount") or "0") for b in book.get("bets") or [])
        mid = str(book["match_id"])
        rec = MATCHES.get(mid) or {}
        seeds = funded_seeds_from_ledger(mid, rec.get("agent_a_wallet") or "", rec.get("agent_b_wallet") or "")
        held += sum(to_micro(v) for v in seeds.values())
    return held


def _system_total() -> int:
    """Every micro-USDC the platform accounts for, on every rail: agentic
    ledger balances, stakes locked in escrow, money held by open books and
    the play-wallet overlays."""
    return ledger.total_micro() + _escrow_held() + _books_held() + _adjust_total()


def _table_with_tickets() -> tuple[str, dict[str, int]]:
    """Lock Raja v Nero (seeded book) and sell tickets on both rails."""
    from gaming.src.backend.services.play_adjust import add_adjust
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    rt = get_house()
    mid = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=5, white_agent_id=RAJA)["match_id"]
    for fan in LEDGER_FANS:
        ledger.credit(fan, Decimal("10"), reason="test_deposit")
    before = {"total": _system_total(), "treasury": to_micro(ledger.balance(ledger.TREASURY_WALLET))}

    rt.lock(mid)
    rec = MATCHES.get(mid)
    eco = rec.get("economy") or {}
    assert Decimal(eco.get("spectator_seed_a") or "0") > 0, "scenario needs a seeded book"
    for fan, (side, amt) in LEDGER_FANS.items():
        rt.take_bet(mid, bettor_id=fan, side=side, amount_usdc=Decimal(amt), funding="ledger")
    for fan, (side, amt) in PROFILE_FANS.items():
        # What rematch_web does for a web/Telegram ticket when the Circle
        # pull is not used: book it, then take the stake off the play balance.
        rt.take_bet(mid, bettor_id=fan, side=side, amount_usdc=Decimal(amt), funding="profile")
        add_adjust(fan, -Decimal(amt), reason=f"bet:{mid}:{side}")
    # Tickets moved money between rails/pots, never created or destroyed it.
    assert _system_total() == before["total"]
    return mid, before


def _assert_conserved(mid: str, before: dict[str, int]) -> dict[str, Any]:
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    book = SpectatorBook().get(mid)
    pay = book["payouts"]
    after_total = _system_total()
    assert after_total == before["total"], (
        f"money created/destroyed: {after_total - before['total']} micro-USDC"
    )
    # The only thing the house keeps is explicit: escrow fee + spectator fee
    # (+ rounding dust), all booked to the treasury wallet.
    esc = ledger.get_escrow(mid) or {}
    esc_fee = to_micro(esc.get("fee") or "0") if esc.get("result") == "win" else 0
    treasury_delta = to_micro(ledger.balance(ledger.TREASURY_WALLET)) - before["treasury"]
    assert treasury_delta == esc_fee + to_micro(pay.get("house_take") or "0")
    # Web tickets are never paid on the agentic ledger...
    for fan in PROFILE_FANS:
        assert ledger.balance(fan) == 0, fan
        assert not [t for t in ledger.txs(wallet=fan)], fan
    # ...and the book never pays out more than it took in.
    paid = sum(to_micro(b["amount"]) for b in pay.get("bettors") or [])
    paid += sum(to_micro(c["amount"]) for c in pay.get("creators") or [])
    paid += sum(to_micro(s["amount"]) for s in pay.get("seed_refunds") or [])
    paid += sum(to_micro(s["amount"]) for s in (pay.get("draw_book") or {}).get("agent_split") or [])
    taken = sum(to_micro(b["amount"]) for b in book["bets"]) + sum(to_micro(v) for v in pay["funded_seeds"].values())
    assert paid + to_micro(pay["house_take"]) == taken
    return pay


def _rail_of(pay: dict[str, Any], fan: str) -> int:
    return sum(to_micro(b["amount"]) for b in pay["bettors"] if b["bettor_id"] == fan)


def _adjust_of(fan: str) -> int:
    from gaming.src.backend.services.play_adjust import get_adjust

    return to_micro(get_adjust(fan))


def test_win_conserves_money_and_pays_each_rail_back(monkeypatch):
    from gaming.src.stack.agentic.matches import get_match_service

    mid, before = _table_with_tickets()
    out = get_match_service().settle_result(
        mid, {"result": "white_win", "winner_agent_id": RAJA, "termination": "CHECKMATE", "moves": []}
    )
    assert out["status"] == "settled"
    pay = _assert_conserved(mid, before)
    assert pay["mode"] == "winner_take_side" and pay["winner_side"] == "a"
    # Winners on side a: one ledger ticket, one web ticket — each on its rail.
    assert to_micro(ledger.balance("fan_l1")) == to_micro("10") - to_micro("1.5") + _rail_of(pay, "fan_l1")
    assert _rail_of(pay, "fan_l1") > to_micro("1.5")
    assert _adjust_of("fan_p1") == -to_micro("0.75") + _rail_of(pay, "fan_p1")
    # Losers paid nothing back.
    assert ledger.balance("fan_l2") == Decimal("8")
    assert _adjust_of("fan_p3") == -to_micro("0.333333")
    # Draw tickets lost to the agents that underwrote them.
    assert ledger.balance("fan_l3") == Decimal("9.5")
    assert _adjust_of("fan_p2") == -to_micro("1.25")
    split = (pay["draw_book"] or {}).get("agent_split") or []
    assert sum(to_micro(s["amount"]) for s in split) == to_micro("1.75")


def test_draw_conserves_money(monkeypatch):
    from gaming.src.stack.agentic.matches import get_match_service

    mid, before = _table_with_tickets()
    get_match_service().settle_result(
        mid, {"result": "draw", "winner_agent_id": None, "termination": "STALEMATE", "moves": []}
    )
    pay = _assert_conserved(mid, before)
    assert pay["mode"] == "draw_hits"
    # Draw tickets win the pool, on their own rails; side tickets lose.
    assert {b["bettor_id"] for b in pay["bettors"]} == {"fan_l3", "fan_p2"}
    assert to_micro(ledger.balance("fan_l3")) == to_micro("9.5") + _rail_of(pay, "fan_l3")
    assert _adjust_of("fan_p2") == -to_micro("1.25") + _rail_of(pay, "fan_p2")
    assert ledger.balance("fan_l1") == Decimal("8.5")


def test_nobody_backed_the_winner_refunds_every_ticket_and_seed(monkeypatch):
    from gaming.src.backend.services.play_adjust import add_adjust
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    rt = get_house()
    mid = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=5, white_agent_id=RAJA)["match_id"]
    ledger.credit("fan_l2", Decimal("10"), reason="test_deposit")
    before = {"total": _system_total(), "treasury": to_micro(ledger.balance(ledger.TREASURY_WALLET))}
    rt.lock(mid)
    rt.take_bet(mid, bettor_id="fan_l2", side="b", amount_usdc=Decimal("2"), funding="ledger")
    rt.take_bet(mid, bettor_id="fan_p3", side="b", amount_usdc=Decimal("1"), funding="profile")
    add_adjust("fan_p3", Decimal("-1"), reason=f"bet:{mid}:b")
    get_match_service().settle_result(
        mid, {"result": "white_win", "winner_agent_id": RAJA, "termination": "CHECKMATE", "moves": []}
    )
    pay = _assert_conserved(mid, before)
    assert pay["mode"] == "refund_no_winner" and pay["house_take"] == "0"
    assert ledger.balance("fan_l2") == Decimal("10")
    assert _adjust_of("fan_p3") == 0


def test_void_refunds_each_rail_and_conserves_money(monkeypatch):
    from gaming.src.stack.agentic.house import abort_table

    mid, before = _table_with_tickets()
    out = abort_table(mid, reason="interrupted")
    assert out["status"] == "cancelled"
    total_after = _system_total()
    assert total_after == before["total"]
    assert to_micro(ledger.balance(ledger.TREASURY_WALLET)) == before["treasury"]  # no fee on a void
    for fan in LEDGER_FANS:
        assert ledger.balance(fan) == Decimal("10"), fan
    for fan in PROFILE_FANS:
        assert _adjust_of(fan) == 0, fan
        assert ledger.balance(fan) == 0


def test_ledger_ticket_needs_the_money_and_books_nothing_without_it():
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    rt = get_house()
    mid = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=1, white_agent_id=RAJA)["match_id"]
    rt.lock(mid)
    ledger.credit("fan_poor", Decimal("0.5"), reason="test_deposit")
    with pytest.raises(ledger.InsufficientFunds):
        rt.take_bet(mid, bettor_id="fan_poor", side="a", amount_usdc=Decimal("1"))
    assert not [b for b in SpectatorBook().get(mid)["bets"] if b["bettor_id"] == "fan_poor"]
    assert ledger.balance("fan_poor") == Decimal("0.5")
    # A system wallet can never be the debited bettor.
    for bad in ("creator:dev", "owner:someone", "0xabc", "agent_raja_kia_alekhine"):
        with pytest.raises(ValueError, match="system wallet"):
            SpectatorBook().place_bet(mid, bettor_id=bad, side="a", amount_usdc=Decimal("0.25"))


def test_settle_is_journaled_and_idempotent_on_retry(monkeypatch):
    from gaming.src.stack.agentic.db import journal
    from gaming.src.stack.agentic.matches import get_match_service

    mid, before = _table_with_tickets()
    result = {"result": "white_win", "winner_agent_id": RAJA, "termination": "CHECKMATE", "moves": []}
    get_match_service().settle_result(mid, result)
    snap = (ledger.balances(), _adjust_total())
    get_match_service().settle_result(mid, result)
    assert (ledger.balances(), _adjust_total()) == snap
    steps = {r["step"] for r in journal.steps(mid)}
    assert "spectator_settle" in steps
    assert any(s.startswith("play_adjust:") for s in steps)
    _assert_conserved(mid, before)


def test_onchain_book_pays_no_fan_from_the_ledger():
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    book = SpectatorBook()
    book.open_book(
        "agm_chainbook", agent_a_id="a", agent_b_id="b", seed_a=Decimal("0.5"), seed_b=Decimal("0.5"),
        seed_draw=Decimal("0.25"), creator_a_id="ca", creator_b_id="cb",
        agent_a_wallet="0xa", agent_b_wallet="0xb",
    )
    book.mark_onchain("agm_chainbook", pool="0xpool")
    book.project_deposit("agm_chainbook", bettor_id="p1", side="a", amount_usdc=Decimal("3"), tx_hash="0x1")
    out = book.settle("agm_chainbook", winner_side="a")
    pay = out["payouts"]
    assert pay["mode"] == "onchain"
    assert pay["bettors"] == [] and pay["creators"] == [] and pay["house_take"] == "0"
    # The ledger-debited seeds were never in the pool: all four go back.
    assert sorted((s["wallet"], s["amount"]) for s in pay["seed_refunds"]) == [
        ("0xa", "0.25"), ("0xa", "0.5"), ("0xb", "0.25"), ("0xb", "0.5"),
    ]
    credits = SpectatorBook.ledger_credits(pay)
    assert {w for w, _, _ in credits} == {"0xa", "0xb"}


def test_unfunded_seeds_are_not_paid_out():
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    book = SpectatorBook()
    book.open_book(
        "agm_noseed", agent_a_id="a", agent_b_id="b", seed_a=Decimal("1"), seed_b=Decimal("1"),
        agent_a_wallet="0xa", agent_b_wallet="0xb",
    )
    book.place_bet("agm_noseed", bettor_id="p1", side="a", amount_usdc=Decimal("1"), funding="profile")
    # The lock never debited the seeds: the pot is the ticket alone.
    out = book.settle("agm_noseed", winner_side="b", funded_seeds={"a": "0", "b": "0", "draw_a": "0", "draw_b": "0"})
    pay = out["payouts"]
    assert pay["mode"] == "refund_no_winner" and pay["pot"] == "1"
    assert pay["seed_refunds"] == []
    assert [(b["bettor_id"], b["amount"]) for b in pay["bettors"]] == [("p1", "1")]


def test_stack_api_tickets_debit_the_caller_only(monkeypatch):
    """Builder / stack-API tickets are ledger-funded and the bettor is the
    caller: a builder key cannot spend someone else's ledger wallet."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from gaming.src.stack.agentic import api as api_mod
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry

    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_ALLOW_OPEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", "sk_master_test")
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", "sk_builder_alice:alice_lab")
    get_registry().ensure_demo_agents()
    rt = get_house()
    mid = rt.open_match(agent_a_id=RAJA, agent_b_id=NERO, stake_usdc=1, white_agent_id=RAJA)["match_id"]
    rt.lock(mid)
    ledger.credit("victim", Decimal("5"), reason="test_deposit")
    ledger.credit("alice_lab", Decimal("5"), reason="test_deposit")
    app = FastAPI()
    app.include_router(api_mod.router)
    c = TestClient(app)
    builder = {"X-Boardman-Key": "sk_builder_alice"}
    for path in (f"/api/stack/agentic/matches/{mid}/spectator/bet", f"/api/stack/agentic/house/matches/{mid}/bets"):
        r = c.post(path, headers=builder, json={"bettor_id": "victim", "side": "a", "amount_usdc": 1})
        assert r.status_code == 403, r.text
        r = c.post(path, headers=builder, json={"bettor_id": "alice_lab", "side": "a", "amount_usdc": 1})
        assert r.status_code == 200, r.text
    assert ledger.balance("victim") == Decimal("5")
    assert ledger.balance("alice_lab") == Decimal("3")
    r = c.post(
        f"/api/stack/agentic/matches/{mid}/spectator/bet",
        headers=builder, json={"bettor_id": "alice_lab", "side": "draw", "amount_usdc": 4},
    )
    assert r.status_code == 402, r.text
    assert ledger.balance("alice_lab") == Decimal("3")
