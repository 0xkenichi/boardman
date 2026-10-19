"""Money audit 2026-10 — the new money locks hold across real processes.

The API, the bot and the house session are separate programs, so every
fix that serializes a money action is also checked with spawned
interpreters sharing one store (SQLite here; the parent's Postgres schema
when BOARDMAN_TEST_DATABASE_URL is set).
"""
from __future__ import annotations

import multiprocessing as mp
from decimal import Decimal

import pytest


def _run(target, argsets):
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(len(argsets))
    procs = [ctx.Process(target=target, args=(*a, barrier), daemon=True) for a in argsets]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
    codes = [p.exitcode for p in procs]
    assert all(c in (0, 3) for c in codes), codes
    return codes


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    return str(tmp_path)


def test_daily_cap_is_shared_by_every_process(data_dir):
    from tests._audit_proc_helpers import proc_reserve_cap

    codes = _run(proc_reserve_cap, [(data_dir, "p_proc", "40")] * 4)
    assert codes.count(0) == 2  # 2 x 40 <= 100 < 3 x 40

    from gaming.src.backend.services.safety import _daily_total

    assert _daily_total("p_proc") == Decimal("80")


def test_one_play_spend_at_a_time_across_processes(data_dir):
    from tests._audit_proc_helpers import proc_spend_lock

    codes = _run(proc_spend_lock, [(data_dir, "p_lock", 3.0)] * 3)
    assert codes.count(0) == 1, codes


def test_two_processes_buying_one_manager_charge_one_buyer(data_dir):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import agent_market as M
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry
    from tests._audit_proc_helpers import proc_buy_manager

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    try:
        aid = M.create_manager_agent(manager_name="Proc FC", archetype="possession", owner_id="dev_p")["agent"][
            "agent_id"
        ]
        M.list_manager_for_sale(agent_id=aid, price_usdc="30.00", listed_by="dev_p")
        for b in ("buyer_p1", "buyer_p2"):
            L.credit(f"owner:{b}", Decimal("30"), reason="test_deposit")
        codes = _run(proc_buy_manager, [(data_dir, aid, "buyer_p1"), (data_dir, aid, "buyer_p2")])
        assert codes.count(0) == 1, codes
        assert L.balance("owner:dev_p") == Decimal("30")
        assert sorted([L.balance("owner:buyer_p1"), L.balance("owner:buyer_p2")]) == [Decimal("0"), Decimal("30")]
    finally:
        for p in cat.seed_catalog():
            cat.set_owner(p["player_id"], None)
