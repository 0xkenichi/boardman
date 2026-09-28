"""Fund-safety regression tests: stale creator_locked challenges must auto-refund.

A creator who locks a stake on-chain and gets ghosted must never have funds
silently stuck in escrow. The sweep in bot.jobs.expiry refunds them.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402


# ── Minimal in-memory supabase mock (only the calls the sweep makes) ─────────
class _Q:
    def __init__(self, sb, table):
        self._sb = sb
        self._table = table
        self._op = "select"
        self._filters: list[tuple[str, str, object]] = []
        self._update_data: dict | None = None

    def select(self, cols="*"):
        self._op = "select"
        return self

    def update(self, data):
        self._op = "update"
        self._update_data = data
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def lt(self, col, val):
        self._filters.append(("lt", col, val))
        return self

    def limit(self, n):
        return self

    def execute(self):
        rows = self._sb.rows
        if self._op == "select":
            out = [
                dict(r)
                for r in rows
                if all(
                    (r.get(c) == v)
                    if kind == "eq"
                    else (str(r.get(c, "")) < str(v))
                    for kind, c, v in self._filters
                )
            ]
            return SimpleNamespace(data=out)
        self._sb.updates.append(
            {"table": self._table, "filters": list(self._filters), "data": self._update_data}
        )
        for r in rows:
            if all(
                (r.get(c) == v) if kind == "eq" else (str(r.get(c, "")) < str(v))
                for kind, c, v in self._filters
            ):
                r.update(self._update_data or {})
        return SimpleNamespace(data=[])


class _MockSB:
    def __init__(self, rows):
        self.rows = rows
        self.updates: list[dict] = []

    def schema(self, name):
        return self

    def table(self, name):
        return _Q(self, name)


@pytest.fixture()
def env(monkeypatch):
    """Patch supabase, cancel_match, and notify_user for the sweep."""
    store: dict = {"sb": None, "notify": [], "cancel_calls": [], "cancel_error": None}

    async def _fake_cancel(cid):
        store["cancel_calls"].append(cid)
        if store["cancel_error"] is not None:
            raise store["cancel_error"]
        return {"success": True, "tx_hash": "0xdeadbeef"}

    async def _fake_notify(uid, text, **kwargs):
        store["notify"].append((uid, text))

    monkeypatch.setattr(
        "gaming.src.bot.jobs.expiry._get_supabase", lambda: store["sb"]
    )
    monkeypatch.setattr(
        "gaming.src.backend.services.clawstation_escrow.cancel_match", _fake_cancel
    )
    monkeypatch.setattr("gaming.src.bot.utils.notify.notify_user", _fake_notify)
    return store


def _expired_row(cid="c1", status="creator_locked"):
    # Live DB columns: issuer_id / target_id (see challenge_compat.py)
    return {
        "id": cid,
        "issuer_id": "creator_1",
        "target_id": "opp_1",
        "status": status,
        "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }


@pytest.mark.asyncio
async def test_sweep_refunds_expired_creator_lock(env):
    from gaming.src.bot.jobs.expiry import sweep_stale_creator_locks

    env["sb"] = _MockSB([_expired_row("c1")])
    swept = await sweep_stale_creator_locks()

    assert swept == 1
    assert env["cancel_calls"] == ["c1"]
    cancelled = [u for u in env["sb"].updates if u["data"] == {"status": "cancelled"}]
    assert len(cancelled) == 1
    # Creator (and ghosting opponent) both told what happened
    assert any(uid == "creator_1" for uid, _ in env["notify"])
    assert any(uid == "opp_1" for uid, _ in env["notify"])
    assert any("refunded automatically" in text for _, text in env["notify"])


@pytest.mark.asyncio
async def test_sweep_skips_when_opponent_joined_mid_sweep(env):
    """Fresh status re-check must prevent refunding a match that is now locked."""
    from gaming.src.bot.jobs.expiry import sweep_stale_creator_locks

    row = _expired_row("c2")
    row["status"] = "locked"  # opponent joined after the listing query
    env["sb"] = _MockSB([row])

    async def _boom(cid):
        raise AssertionError("cancel_match must not be called for a locked match")

    env["cancel_calls"] = []
    import gaming.src.backend.services.clawstation_escrow as esc

    original = esc.cancel_match
    esc.cancel_match = _boom
    try:
        swept = await sweep_stale_creator_locks()
    finally:
        esc.cancel_match = original

    assert swept == 0
    assert env["sb"].updates == []


@pytest.mark.asyncio
async def test_sweep_leaves_status_when_refund_fails(env):
    """On-chain refund failure must NOT mark cancelled — retried next sweep."""
    from gaming.src.backend.services.clawstation_escrow import EscrowError
    from gaming.src.bot.jobs.expiry import sweep_stale_creator_locks

    env["sb"] = _MockSB([_expired_row("c3")])
    env["cancel_error"] = EscrowError("resolver wallet not configured")

    swept = await sweep_stale_creator_locks()

    assert swept == 0
    assert env["sb"].updates == []  # status stays creator_locked → retried
    assert env["notify"] == []


@pytest.mark.asyncio
async def test_sweep_ignores_non_creator_locked_status(env):
    from gaming.src.bot.jobs.expiry import sweep_stale_creator_locks

    rows = [
        _expired_row("c4", status="locked"),  # both staked — never touched
        _expired_row("c5", status="open"),  # no funds locked
        _expired_row("c6", status="creator_locked"),  # the one to refund
    ]
    env["sb"] = _MockSB(rows)
    swept = await sweep_stale_creator_locks()

    assert swept == 1
    assert env["cancel_calls"] == ["c6"]


@pytest.mark.asyncio
async def test_scheduler_registers_sweep_job():
    """The sweep must be scheduled, or the fix never runs in production."""
    import inspect

    from gaming.src.bot.jobs import expiry

    src = inspect.getsource(expiry.start_expiry_scheduler)
    assert "sweep_stale_creator_locks" in src
    assert "clawstation_creator_lock_sweep" in src
