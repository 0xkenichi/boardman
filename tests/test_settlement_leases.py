"""Per-match leases: one driver per table across processes; takeover only after expiry."""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.stack.agentic.db import leases, transaction
from gaming.src.stack.agentic.db.tables import MATCHES


@pytest.fixture(autouse=True)
def _clean_leases():
    leases.forget_local_state()
    yield
    leases.forget_local_state()


def _as_owner(monkeypatch, owner: str) -> None:
    monkeypatch.setattr(leases, "process_owner", lambda: owner)


def test_second_owner_is_refused_until_expiry(monkeypatch):
    _as_owner(monkeypatch, "api-1")
    assert leases.try_acquire("agm_l1") is not None
    _as_owner(monkeypatch, "house-1")
    assert leases.try_acquire("agm_l1") is None
    assert leases.active_holder("agm_l1") == "api-1"
    with transaction() as tx:
        tx.execute("UPDATE match_leases SET expires_at_ms = 0 WHERE match_id = ?", ("agm_l1",))
    row = leases.try_acquire("agm_l1")
    assert row is not None and row["taken_over"] and row["epoch"] == 2
    assert leases.active_holder("agm_l1") == "house-1"


def test_renewal_keeps_the_lease(monkeypatch):
    _as_owner(monkeypatch, "house-1")
    leases.acquire("agm_l2")
    with transaction() as tx:
        tx.execute("UPDATE match_leases SET expires_at_ms = 1 WHERE match_id = ?", ("agm_l2",))
    assert leases.renew_held() == []
    assert leases.active_holder("agm_l2") == "house-1"
    leases.release("agm_l2")
    assert leases.state("agm_l2") is None


def test_refcounted_hold_releases_once(monkeypatch):
    _as_owner(monkeypatch, "house-1")
    with leases.hold("agm_l3"):
        with leases.hold("agm_l3"):
            pass
        assert leases.active_holder("agm_l3") == "house-1"
    assert leases.state("agm_l3") is None


def test_money_step_refuses_after_lease_was_taken(monkeypatch):
    _as_owner(monkeypatch, "zombie")
    leases.acquire("agm_l4")
    with transaction() as tx:
        tx.execute(
            "UPDATE match_leases SET owner = 'new-owner', expires_at_ms = ? WHERE match_id = ?",
            (10**15, "agm_l4"),
        )
    with pytest.raises(leases.LeaseLost):
        with transaction() as tx:
            leases.assert_held(tx, "agm_l4")


def _seed_playing_match(mid: str, status: str = "playing") -> None:
    MATCHES.put(
        mid,
        {
            "match_id": mid,
            "status": status,
            "agent_a_id": "agent_x",
            "agent_b_id": "agent_y",
            "white_agent_id": "agent_x",
            "black_agent_id": "agent_y",
            "stake_usdc": "5",
            "updated_at": "2026-10-14T00:00:00+00:00",
        },
    )


def test_rescue_orphans_skips_a_table_another_process_drives(monkeypatch):
    from gaming.src.stack.agentic import house

    submitted: list[str] = []

    class _Pool:
        def submit(self, fn, mid, *a, **k):
            submitted.append(mid)

            class _F:
                pass

            return _F()

    monkeypatch.setattr(house, "_executor", lambda: _Pool())
    with house._floor_lock:
        house._workers.clear()
    _seed_playing_match("agm_live")
    _seed_playing_match("agm_dead")
    _seed_playing_match("agm_settling", status="settling")
    _as_owner(monkeypatch, "house-session")
    leases.try_acquire("agm_live")  # the session is driving this one
    leases.try_acquire("agm_dead")
    with transaction() as tx:  # ...and crashed on this one long ago
        tx.execute("UPDATE match_leases SET expires_at_ms = 0 WHERE match_id = ?", ("agm_dead",))

    _as_owner(monkeypatch, "api-replica")
    resumed = house.rescue_orphans()
    assert "agm_live" not in resumed and "agm_live" not in submitted
    assert {"agm_dead", "agm_settling"} <= set(resumed)
    with house._floor_lock:
        house._workers.clear()


def test_run_match_raises_tablebusy_for_a_live_foreign_lease(monkeypatch):
    from gaming.src.stack.agentic.matches import AgentMatchService, TableBusy

    _seed_playing_match("agm_busy2")
    _as_owner(monkeypatch, "house-session")
    leases.try_acquire("agm_busy2")
    _as_owner(monkeypatch, "api-replica")
    with pytest.raises(TableBusy):
        AgentMatchService().run_match("agm_busy2")


def test_stale_whole_record_save_cannot_unsettle_a_match():
    """lock_both used to save a copy read minutes earlier over a settled match."""
    from gaming.src.stack.agentic.matches import AgentMatchService

    svc = AgentMatchService()
    _seed_playing_match("agm_stale")
    stale = svc._load()  # a writer reads the hot set...
    svc._set("agm_stale", status="settled", escrow={"result": "win"}, settled_at="2026-10-14T01:00:00+00:00")
    stale["matches"]["agm_stale"]["status"] = "playing"  # ...and saves it back late
    stale["matches"]["agm_stale"]["ply"] = 12
    svc._save(stale)
    rec = MATCHES.get("agm_stale")
    assert rec["status"] == "settled"
    assert rec["escrow"] == {"result": "win"}
    assert rec["ply"] == 12  # the field it really changed still lands


def test_snapshot_save_merges_disjoint_field_changes():
    from gaming.src.stack.agentic.matches import AgentMatchService

    svc = AgentMatchService()
    _seed_playing_match("agm_merge")
    a = svc._load()
    b = svc._load()
    a["matches"]["agm_merge"]["clerk"] = "boardman_house"
    b["matches"]["agm_merge"]["spectator_book"] = {"status": "closed"}
    svc._save(a)
    svc._save(b)
    rec = MATCHES.get("agm_merge")
    assert rec["clerk"] == "boardman_house"
    assert rec["spectator_book"] == {"status": "closed"}


def test_set_status_never_rewinds_a_settlement():
    from gaming.src.stack.agentic.house import _set_status

    _seed_playing_match("agm_nr", status="settling")
    with pytest.raises(ValueError, match="settling"):
        _set_status("agm_nr", "error", play_error="boom")
    assert MATCHES.get("agm_nr")["status"] == "settling"


def test_concurrent_bets_are_all_booked():
    """place_bet used to lose bets when two writers saved the book at once."""
    import threading

    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    SpectatorBook().open_book("agm_bets", agent_a_id="x", agent_b_id="y", pot_cap_usdc=Decimal("1000"))

    def bettor(i: int) -> None:
        for _ in range(10):
            SpectatorBook().place_bet("agm_bets", bettor_id=f"fan{i}", side="a", amount_usdc=Decimal("0.5"))

    ts = [threading.Thread(target=bettor, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    book = SpectatorBook().get("agm_bets")
    assert len(book["bets"]) == 60
    assert Decimal(book["totals"]["a"]) == Decimal("30")
