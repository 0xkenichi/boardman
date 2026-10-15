"""Channels storage: persisted conversation state, rate limits, identity repo."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from gaming.src.channels.core import ratelimit, state, store
from gaming.src.channels.core.identity.repo import (
    Identity,
    LinkCode,
    MemoryIdentityRepo,
    SupabaseIdentityRepo,
    utcnow,
)

ROOT = Path(__file__).resolve().parents[1]


def test_state_migration_matches_store_module():
    path = ROOT / "supabase" / "migrations" / "20261016120100_channels_state.sql"
    assert path.read_text() == store.postgres_migration_sql()


def test_identity_migration_has_tables_and_rls():
    sql = (ROOT / "supabase" / "migrations" / "20261016120000_channel_identities.sql").read_text()
    for needle in (
        "CREATE TABLE IF NOT EXISTS public.channel_identities",
        "UNIQUE (channel, external_id)",
        "CREATE TABLE IF NOT EXISTS public.channel_link_codes",
        "ALTER TABLE public.channel_identities ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE public.channel_link_codes ENABLE ROW LEVEL SECURITY",
    ):
        assert needle in sql


def test_state_round_trip_survives_a_new_handle():
    st = state.load("whatsapp", "2348011112222")
    assert not st.active and st.version == 0
    st.set("withdraw", "amount", dest="0xabc")
    st.data["_menu"] = ["x"]
    state.save(st)

    # A restart: drop every cached connection, read again.
    from gaming.src.stack.agentic.db import engine

    engine.reset_databases()
    again = state.load("whatsapp", "2348011112222")
    assert (again.flow, again.step, again.data["dest"]) == ("withdraw", "amount", "0xabc")
    assert again.version == 1


def test_state_optimistic_concurrency():
    a = state.load("telegram", "1")
    a.set("balance", "shown")
    state.save(a)
    b1 = state.load("telegram", "1")
    b2 = state.load("telegram", "1")
    b1.set("deposit", "amount")
    state.save(b1)
    b2.set("withdraw", "dest")
    with pytest.raises(state.StaleState):
        state.save(b2)
    assert state.load("telegram", "1").flow == "deposit"


def test_state_expires_but_keeps_generic_keys():
    st = state.load("whatsapp", "9")
    st.set("deposit", "amount")
    st.data["_last_choice"] = {"x": 1}
    state.save(st, ttl_ms=1000, now_ms=1_000)
    later = state.load("whatsapp", "9", now_ms=10_000)
    assert not later.active
    assert later.data == {"_last_choice": {"x": 1}}


def test_rate_limit_window():
    for i in range(3):
        assert ratelimit.hit("b", limit=3, window_sec=60, now_ms=1_000 + i)
    assert not ratelimit.hit("b", limit=3, window_sec=60, now_ms=2_000)
    assert ratelimit.hit("b", limit=3, window_sec=60, now_ms=70_000)


def test_memory_repo_link_code_single_use_and_expiry():
    repo = MemoryIdentityRepo()
    now = utcnow()
    repo.put_link_code(LinkCode("h1", "p1", "link_channel", "telegram", now + timedelta(minutes=10)))
    assert repo.consume_link_code("h1", now)
    assert not repo.consume_link_code("h1", now)
    repo.put_link_code(LinkCode("h2", "p1", "link_channel", "telegram", now - timedelta(seconds=1)))
    assert not repo.consume_link_code("h2", now)


def test_memory_repo_identity_upsert_and_move():
    repo = MemoryIdentityRepo()
    a = repo.upsert(Identity("telegram", "42", "p1"))
    b = repo.upsert(Identity("telegram", "42", "p1", handle="new"))
    assert a.id == b.id and b.handle == "new"
    repo.upsert(Identity("whatsapp", "234", "p2"))
    assert repo.move_identities("p2", "p1") == 1
    assert {i.channel for i in repo.for_profile("p1")} == {"telegram", "whatsapp"}
    with pytest.raises(ValueError):
        repo.upsert(Identity("sms", "1", "p1"))


class _Q:
    """Records a PostgREST chain and answers from canned rows."""

    def __init__(self, log, table, rows):
        self.log, self.table, self.rows, self.ops = log, table, rows, []

    def __getattr__(self, name):
        def call(*a, **k):
            self.ops.append((name, a, k))
            return self
        return call

    @property
    def not_(self):
        self.ops.append(("not_", (), {}))
        return self

    def execute(self):
        self.log.append((self.table, self.ops))
        return SimpleNamespace(data=self.rows)


def test_supabase_repo_consume_is_one_conditional_update(monkeypatch):
    log: list = []
    sb = SimpleNamespace(table=lambda t: _Q(log, t, [{"code_hash": "h"}]))
    monkeypatch.setattr("backend.supabase_client.get_supabase", lambda: sb)
    assert SupabaseIdentityRepo().consume_link_code("h", utcnow())
    table, ops = log[0]
    names = [o[0] for o in ops]
    assert table == "channel_link_codes"
    assert names[0] == "update" and "is_" in names and "gt" in names


def test_supabase_repo_upsert_uses_conflict_key(monkeypatch):
    log: list = []
    sb = SimpleNamespace(table=lambda t: _Q(log, t, [{"channel": "telegram", "external_id": "7", "profile_id": "p"}]))
    monkeypatch.setattr("backend.supabase_client.get_supabase", lambda: sb)
    out = SupabaseIdentityRepo().upsert(Identity("telegram", "7", "p"))
    assert out.profile_id == "p"
    (table, ops), = log
    assert table == "channel_identities"
    assert ops[0][0] == "upsert" and ops[0][2] == {"on_conflict": "channel,external_id"}
