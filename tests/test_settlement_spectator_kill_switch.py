"""Spectator-betting kill switch (docs/compliance/KYC_AML_PLAN.md §6.6)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.backend.services import spectator_policy as sp

MASTER = "sk_master_test"
MAINNET_SIGNALS = [
    ("BOARDMAN_ENV", "production"),
    ("NETWORK", "mainnet"),
    ("CLAW_DEFAULT_CHAIN", "arc_mainnet"),
    ("BOARDMAN_SETTLEMENT_RAIL", "arc_mainnet"),
    ("SPECTATOR_CHAIN", "arc_mainnet"),
]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("SPECTATOR_BETTING_ENABLED", "SPECTATOR_BETTING_COUNTRIES", "BOARDMAN_ENV", "APP_ENV",
              "ENVIRONMENT", "NETWORK", "CLAW_DEFAULT_CHAIN", "BOARDMAN_SETTLEMENT_RAIL", "SPECTATOR_CHAIN"):
        monkeypatch.delenv(k, raising=False)


# ── decision function ────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,value", MAINNET_SIGNALS)
def test_default_off_on_every_mainnet_signal(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert sp.is_mainnet()
    assert sp.spectator_betting_decision("KE") == (False, "disabled")


def test_default_on_for_testnet():
    assert not sp.is_mainnet()
    assert sp.spectator_betting_decision(None) == (True, "ok")


def test_chain_resolution_error_counts_as_mainnet(monkeypatch):
    import gaming.src.backend.services.chains as chains

    monkeypatch.setattr(chains, "default_chain_id", lambda: (_ for _ in ()).throw(RuntimeError("bad yaml")))
    assert sp.is_mainnet()


@pytest.mark.parametrize("raw", ["ture", "enabled", "2", "of"])
def test_typo_value_counts_as_off(monkeypatch, raw):
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", raw)
    assert sp.spectator_betting_decision("KE") == (False, "disabled")


def test_empty_allowlist_on_mainnet_refuses_everyone(monkeypatch):
    monkeypatch.setenv("NETWORK", "mainnet")
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "1")
    assert sp.spectator_betting_decision("KE") == (False, "country_not_allowed")
    assert sp.spectator_betting_decision(None) == (False, "country_unknown")


def test_allowlisted_country_passes_and_unknown_is_refused(monkeypatch):
    monkeypatch.setenv("NETWORK", "mainnet")
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "on")
    monkeypatch.setenv("SPECTATOR_BETTING_COUNTRIES", " ke, gh ")
    assert sp.spectator_betting_decision("KE") == (True, "ok")
    assert sp.spectator_betting_decision("gh") == (True, "ok")
    assert sp.spectator_betting_decision("NG") == (False, "country_not_allowed")
    assert sp.spectator_betting_decision(None) == (False, "country_unknown")


def test_blocked_country_refused_even_when_allowlisted(monkeypatch):
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "1")
    monkeypatch.setenv("SPECTATOR_BETTING_COUNTRIES", "KP,KE")
    assert sp.spectator_betting_decision("KP") == (False, "country_blocked")


def test_testnet_allowlist_applies_only_when_set(monkeypatch):
    monkeypatch.setenv("SPECTATOR_BETTING_COUNTRIES", "KE")
    assert sp.spectator_betting_decision("NG") == (False, "country_not_allowed")
    assert sp.spectator_betting_decision("KE") == (True, "ok")


def test_global_pause_disables(monkeypatch):
    from gaming.src.backend.services import safety

    monkeypatch.setattr(safety, "is_paused", lambda: True)
    assert sp.spectator_betting_decision("KE") == (False, "disabled")


def test_refusal_bodies_and_status():
    off = sp.SpectatorBettingUnavailable("disabled")
    assert (off.status_code, off.body) == (403, {"error": "spectator_betting_disabled"})
    region = sp.SpectatorBettingUnavailable("country_unknown")
    assert region.status_code == 451
    assert region.body == {"error": "spectator_betting_unavailable_in_region", "reason": "country_unknown"}
    assert "allowlist" not in str(region).lower()


# ── service layer ────────────────────────────────────────────────────────────


def test_place_bet_refused_and_nothing_booked(monkeypatch):
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    SpectatorBook().open_book("agm_ks1", agent_a_id="x", agent_b_id="y")
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "0")
    with pytest.raises(sp.SpectatorBettingUnavailable):
        SpectatorBook().place_bet("agm_ks1", bettor_id="fan", side="a", amount_usdc=Decimal("1"))
    assert SpectatorBook().get("agm_ks1")["bets"] == []


def test_switch_off_new_tables_open_no_book_and_seed_nothing(monkeypatch):
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "0")
    agents = {a["agent_id"]: a for a in get_registry().ensure_demo_agents()}
    raja = agents["agent_raja_kia_alekhine"]
    m = get_match_service().create_match(
        agent_a_id=raja["agent_id"], agent_b_id="agent_nero_sicilian_french", stake_usdc=5
    )
    before = ledger.balance(raja["wallet_address"])
    get_match_service().lock_both(m["match_id"])
    book = SpectatorBook().get(m["match_id"])
    assert book["status"] == "closed" and book["closed_reason"] == "betting_disabled"
    assert m["economy"]["spectator_seed_a"] == "0"
    # only the stake left the bankroll — no spectator seed
    assert before - ledger.balance(raja["wallet_address"]) == Decimal("5")


def test_payouts_and_lp_withdraw_still_work_when_switch_is_off(monkeypatch):
    from gaming.src.stack.agentic.economy.lp import AgentLPPool
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    SpectatorBook().open_book("agm_ks2", agent_a_id="x", agent_b_id="y", pot_cap_usdc=Decimal("100"))
    SpectatorBook().place_bet("agm_ks2", bettor_id="fan", side="a", amount_usdc=Decimal("12"))
    AgentLPPool().deposit("agent_q", lp_id="lp1", amount_usdc=Decimal("10"))
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "off")
    settled = SpectatorBook().settle("agm_ks2", winner_side="a")
    assert settled["payouts"]["bettors"][0]["bettor_id"] == "fan"
    out = AgentLPPool().withdraw(
        "agent_q", lp_id="lp1", amount_usdc=Decimal("5"), agent_bankroll=Decimal("100"), reserve_bps=0
    )
    assert out["withdrawn"] == "5.000000"


def test_afm_bet_refused_before_debit(monkeypatch):
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.games.football_managers.betting import place_bet

    ledger.credit("fan_afm", Decimal("10"), reason="fund")
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "0")
    with pytest.raises(sp.SpectatorBettingUnavailable):
        place_bet("fan_afm", 1, 1, "home", "away", "home", "2")
    assert ledger.balance("fan_afm") == Decimal("10")


# ── routes ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def app_client(monkeypatch):
    from fastapi.testclient import TestClient

    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    from gaming.src.backend.main import create_app

    return TestClient(create_app())


def _house_match() -> str:
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    m = get_house().open_match(
        agent_a_id="agent_raja_kia_alekhine", agent_b_id="agent_nero_sicilian_french", stake_usdc=5
    )
    return m["match_id"]


def _routes(mid: str) -> list[tuple[str, dict, dict]]:
    master = {"X-Boardman-Key": MASTER, "X-Rematch-Key": MASTER}
    return [
        ("/api/rematch/web/spectator/bet", {"profile_id": "p1", "amount": 1, "side": "a", "match_id": mid}, master),
        ("/api/rematch/web/spectator/lp", {"profile_id": "p1", "amount": 1, "agent_id": "agent_raja_kia_alekhine"}, master),
        (f"/api/stack/agentic/matches/{mid}/spectator/bet", {"bettor_id": "p1", "side": "a", "amount_usdc": 1}, master),
        (f"/api/stack/agentic/house/matches/{mid}/bets", {"bettor_id": "p1", "side": "a", "amount_usdc": 1}, master),
        (
            "/api/stack/agentic/football/betting/bet",
            {"better": "p1", "season_no": 1, "matchday": 1, "home": "h", "away": "a", "side": "home", "amount": "2"},
            master,
        ),
    ]


def test_every_gated_route_returns_403_when_disabled(app_client, monkeypatch):
    mid = _house_match()
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "0")
    for path, body, headers in _routes(mid):
        r = app_client.post(path, json=body, headers=headers)
        assert r.status_code == 403, (path, r.status_code, r.text)
        assert r.json() == {"error": "spectator_betting_disabled"}, path


def test_every_gated_route_returns_451_outside_the_allowlist(app_client, monkeypatch):
    mid = _house_match()
    monkeypatch.setenv("SPECTATOR_BETTING_COUNTRIES", "KE")
    for path, body, headers in _routes(mid):
        r = app_client.post(path, json=body, headers={**headers, "x-boardman-client-country": "NG"})
        assert r.status_code == 451, (path, r.status_code, r.text)
        assert r.json() == {"error": "spectator_betting_unavailable_in_region", "reason": "country_not_allowed"}


def test_policy_endpoint_exposes_the_switch(app_client, monkeypatch):
    monkeypatch.setenv("SPECTATOR_BETTING_ENABLED", "0")
    r = app_client.get("/api/stack/agentic/economy/policy", headers={"X-Boardman-Key": MASTER})
    assert r.status_code == 200
    assert r.json()["spectator_betting"] == {"enabled": False, "reason": "disabled"}
