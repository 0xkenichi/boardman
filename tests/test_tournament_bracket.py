"""Unit tests for tournament bracket + payout math (no Supabase)."""
from decimal import Decimal

import pytest

from gaming.src.backend.services.tournament import (
    TournamentError,
    build_bracket,
    compute_payouts,
    report_match_winner,
    create_tournament,
    join_tournament,
    start_tournament,
    get_tournament,
    money_live,
)
import gaming.src.backend.services.tournament as tmod


def test_build_bracket_8():
    ids = [f"p{i}" for i in range(8)]
    b = build_bracket(ids)
    keys = {m["match_key"] for m in b}
    assert "R1-M0" in keys
    assert "R2-M0" in keys
    assert "R3-M0" in keys  # final
    assert "R3RD-M0" in keys
    r1 = [m for m in b if m["round"] == 1]
    assert len(r1) == 4
    assert all(m["status"] == "ready" for m in r1)
    players = set()
    for m in r1:
        players.add(m["player_a"])
        players.add(m["player_b"])
    assert players == set(ids)


def test_build_bracket_4():
    b = build_bracket(["a", "b", "c", "d"])
    r1 = [m for m in b if m["round"] == 1]
    assert len(r1) == 2
    assert not any(m.get("is_third_place") for m in b)


def test_build_bracket_bad_size():
    with pytest.raises(TournamentError):
        build_bracket(["a", "b", "c"])


def test_compute_payouts():
    pot = Decimal("80")
    places = {"1": "w", "2": "r", "3": "t"}
    block = compute_payouts(pot, 1000, places)[0]
    assert block["platform_fee_usdc"] == 8.0
    assert abs(block["distributable_usdc"] - 72.0) < 0.01
    by_place = {p["place"]: p["amount_usdc"] for p in block["places"]}
    assert by_place[1] == pytest.approx(46.8, abs=0.02)  # 65% of 72
    assert by_place[2] == pytest.approx(14.4, abs=0.02)
    assert by_place[3] == pytest.approx(10.8, abs=0.02)


def test_dry_run_flow(tmp_path, monkeypatch):
    import asyncio

    store = tmp_path / "tournaments.json"
    monkeypatch.setenv("TOURNAMENT_FORCE_JSON", "1")
    monkeypatch.setenv("TOURNAMENTS_MONEY_LIVE", "0")
    monkeypatch.setenv("TOURNAMENTS_ENABLED", "1")
    monkeypatch.setattr(tmod, "_STORE_PATH", store)
    monkeypatch.setattr(tmod, "_use_supabase", False)

    t = create_tournament(
        host_profile_id="host",
        game_id="mobile.8_ball_pool",
        preset=4,
        entry_usdc=5,
        title="Test Cup",
    )
    code = t["code"]
    for i in range(4):
        asyncio.get_event_loop().run_until_complete(join_tournament(code, f"player-{i}"))
    t2 = start_tournament(code)
    assert t2["status"] == "live"
    assert len(t2["bracket"]) >= 2
    # play through R1
    r1 = [m for m in t2["bracket"] if m["round"] == 1 and m["status"] == "ready"]
    assert len(r1) == 2
    for m in r1:
        t2 = report_match_winner(code, m["match_key"], m["player_a"])
    # final should be ready
    final = next(m for m in t2["bracket"] if m["match_key"] == "R2-M0")
    assert final["status"] == "ready"
    t3 = report_match_winner(code, "R2-M0", final["player_a"])
    assert t3["status"] == "final"
    assert t3.get("payouts")
    assert money_live() is False
