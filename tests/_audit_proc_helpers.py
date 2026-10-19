"""Spawned-process workers for the 2026-10 money audit tests.

Each worker exits 0 when it got the money action through and 3 when it was
refused, so the parent can count winners across real processes (SQLite file
or, with BOARDMAN_TEST_DATABASE_URL, the parent's Postgres schema).
"""
from __future__ import annotations

import sys
import time
from decimal import Decimal

from tests._proc_helpers import _use_store


def proc_reserve_cap(data_dir: str, profile_id: str, amount: str, barrier) -> None:
    _use_store(data_dir)
    from gaming.src.backend.services.safety import reserve_daily_withdraw

    barrier.wait(30)
    sys.exit(3 if reserve_daily_withdraw(profile_id, Decimal(amount)) else 0)


def proc_spend_lock(data_dir: str, profile_id: str, hold_s: float, barrier) -> None:
    _use_store(data_dir)
    from gaming.src.backend.services.play_adjust import PlaySpendBusy, spend_lock

    barrier.wait(30)
    try:
        with spend_lock(profile_id):
            time.sleep(hold_s)
    except PlaySpendBusy:
        sys.exit(3)
    sys.exit(0)


def proc_buy_manager(data_dir: str, agent_id: str, buyer: str, barrier) -> None:
    _use_store(data_dir)
    from gaming.src.stack.agentic.games.football_managers import agent_market as M

    real = M._execute_sale

    def _slow(*a, **k):  # the on-chain rail waits on Circle for seconds
        time.sleep(0.5)
        return real(*a, **k)

    M._execute_sale = _slow
    barrier.wait(30)
    try:
        M.purchase_manager_agent(agent_id=agent_id, buyer_id=buyer)
    except ValueError:
        sys.exit(3)
    sys.exit(0)
