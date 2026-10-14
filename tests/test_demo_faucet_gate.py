"""The demo faucet never mints money for a human buyer, and never on mainnet.

Policy (``ledger.demo_faucet_mode`` / ``demo_faucet_explicit``):

* ``BOARDMAN_DEMO_FAUCET`` unset → house faucet ON off mainnet, OFF on mainnet.
* Marketplace buyers are faucet-funded only with an explicit
  ``BOARDMAN_DEMO_FAUCET=1`` (local demos). Otherwise they pay from their real
  balance or the sale fails with nothing moved.
* Mainnet refuses the faucet even when the flag is set, and refuses the
  book-entry marketplace rail outright.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.delenv("BOARDMAN_DEMO_FAUCET", raising=False)
    monkeypatch.delenv("NETWORK", raising=False)
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


def _mainnet(monkeypatch) -> None:
    monkeypatch.setenv("NETWORK", "mainnet")


def _faucet_rows() -> list[dict]:
    from gaming.src.stack.agentic import ledger as L

    return [t for t in L.snapshot()["txs"] if t.get("reason") == "demo_faucet"]


@pytest.fixture()
def _listed():
    """A developer-built manager listed at $10 (first sale: dev keeps it all)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
        list_manager_for_sale,
    )
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    aid = create_manager_agent(manager_name="Gate FC", owner_id="dev_gate")["agent"]["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="10.00", listed_by="dev_gate")
    return aid


def _owner_of(aid: str) -> str:
    from gaming.src.stack.agentic.registry import get_registry

    return str(get_registry().get_agent(aid)["owner_id"])


# ------------------------------------------------------------ the mode switch


def test_faucet_mode_defaults(monkeypatch):
    from gaming.src.stack.agentic import ledger as L

    assert L.demo_faucet_mode() is True  # testnet, unset → house faucet on
    assert L.demo_faucet_explicit() is False  # but never for humans by default
    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "off")
    assert L.demo_faucet_mode() is False
    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "1")
    assert L.demo_faucet_mode() is True and L.demo_faucet_explicit() is True


def test_production_testnet_deploy_is_not_mainnet(monkeypatch):
    from gaming.src.stack.agentic import ledger as L

    monkeypatch.setenv("BOARDMAN_ENV", "production")
    assert L.demo_faucet_mode() is True


def test_faucet_off_is_a_noop(monkeypatch):
    from gaming.src.stack.agentic import ledger as L

    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "0")
    assert L.ensure_funded("0xhouse_agent", Decimal("100")) == 0
    assert L.balance("0xhouse_agent") == 0
    assert _faucet_rows() == []


def test_mainnet_refuses_faucet_even_when_flag_set(monkeypatch, caplog):
    from gaming.src.stack.agentic import ledger as L

    _mainnet(monkeypatch)
    assert L.demo_faucet_mode() is False
    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "1")
    with caplog.at_level(logging.CRITICAL, logger=L.logger.name):
        assert L.demo_faucet_mode() is False
        assert L.demo_faucet_explicit() is False
        assert L.ensure_funded("0xhouse_agent", Decimal("100")) == 0
    assert L.balance("0xhouse_agent") == 0
    assert _faucet_rows() == []
    assert any("REFUSED" in r.getMessage() for r in caplog.records)


# ------------------------------------------------------------ marketplace buyers


def test_broke_buyer_cannot_buy_and_nothing_moves(_listed):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        InsufficientBalance,
        purchase_manager_agent,
    )

    with pytest.raises(InsufficientBalance, match="insufficient balance"):
        purchase_manager_agent(agent_id=_listed, buyer_id="broke_buyer")
    assert _owner_of(_listed) == "dev_gate"
    assert L.balance("owner:broke_buyer") == 0
    assert L.balance("owner:dev_gate") == 0
    assert _faucet_rows() == []


def test_partly_funded_buyer_is_refused_without_partial_debit(_listed):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        InsufficientBalance,
        purchase_manager_agent,
    )

    L.credit("owner:short_buyer", Decimal("9.99"), reason="test_deposit")
    with pytest.raises(InsufficientBalance):
        purchase_manager_agent(agent_id=_listed, buyer_id="short_buyer", settlement="ledger")
    assert str(L.balance("owner:short_buyer")) == "9.99"
    assert L.balance("owner:dev_gate") == 0
    assert _owner_of(_listed) == "dev_gate"


def test_funded_buyer_pays_exactly_the_price(_listed):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        purchase_manager_agent,
    )

    L.credit("owner:rich_buyer", Decimal("15.00"), reason="test_deposit")
    res = purchase_manager_agent(agent_id=_listed, buyer_id="rich_buyer")
    assert res["sale"]["mode"] == "ledger"
    assert res["agent"]["owner_id"] == "rich_buyer"
    assert str(L.balance("owner:rich_buyer")) == "5.00"
    assert str(L.balance("owner:dev_gate")) == "10.00"
    assert _faucet_rows() == []


def test_explicit_demo_flag_faucets_a_local_buyer(_listed, monkeypatch):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        purchase_manager_agent,
    )

    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "1")
    res = purchase_manager_agent(agent_id=_listed, buyer_id="demo_buyer")
    assert res["agent"]["owner_id"] == "demo_buyer"
    assert L.balance("owner:demo_buyer") == 0
    assert str(L.balance("owner:dev_gate")) == "10.00"
    assert len(_faucet_rows()) == 1


def test_offer_accept_by_broke_buyer_moves_nothing(_listed):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        InsufficientBalance,
        accept_manager_offer,
        make_manager_offer,
    )

    offer = make_manager_offer(agent_id=_listed, offer_usdc="8.00", buyer_id="broke_offer")
    oid = offer["offer"]["offer_id"]
    with pytest.raises(InsufficientBalance):
        accept_manager_offer(agent_id=_listed, offer_id=oid, accept_by="dev_gate")
    assert _owner_of(_listed) == "dev_gate"
    assert L.balance("owner:dev_gate") == 0


def test_mainnet_refuses_the_ledger_rail(_listed, monkeypatch):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        LedgerRailRefused,
        purchase_manager_agent,
    )

    L.credit("owner:main_buyer", Decimal("50.00"), reason="test_deposit")
    _mainnet(monkeypatch)
    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "1")  # must not matter on mainnet
    with pytest.raises(LedgerRailRefused, match="mainnet"):
        purchase_manager_agent(agent_id=_listed, buyer_id="main_buyer")  # auto: no fallback
    with pytest.raises(LedgerRailRefused, match="mainnet"):
        purchase_manager_agent(agent_id=_listed, buyer_id="main_buyer", settlement="ledger")
    assert _owner_of(_listed) == "dev_gate"
    assert str(L.balance("owner:main_buyer")) == "50.00"
    assert L.balance("owner:dev_gate") == 0
    assert _faucet_rows() == []


# ------------------------------------------------------------ house side


def _house_match_env(monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "0")
    monkeypatch.setattr("gaming.src.stack.agentic.onchain.onchain_enabled", lambda: False)
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    get_registry.cache_clear()
    get_match_service.cache_clear()
    agents = {a["agent_id"]: a for a in get_registry().ensure_demo_agents()}
    return (
        get_match_service(),
        agents["agent_raja_kia_alekhine"],
        agents["agent_nero_sicilian_french"],
    )


def test_house_match_runs_on_testnet_by_default(monkeypatch):
    from gaming.src.stack.agentic import ledger as L

    svc, raja, nero = _house_match_env(monkeypatch)
    m = svc.create_match(agent_a_id=raja["agent_id"], agent_b_id=nero["agent_id"], stake_usdc=1)
    assert m["status"] == "open"
    assert L.balance(raja["wallet_address"]) > 0
    assert _faucet_rows()


def test_house_match_refuses_to_open_unfunded_when_faucet_off(monkeypatch):
    from gaming.src.stack.agentic import ledger as L

    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "0")
    svc, raja, nero = _house_match_env(monkeypatch)
    with pytest.raises(ValueError):
        svc.create_match(agent_a_id=raja["agent_id"], agent_b_id=nero["agent_id"], stake_usdc=1)
    with pytest.raises(ValueError):
        svc.create_match(
            agent_a_id=raja["agent_id"], agent_b_id=nero["agent_id"], stake_usdc=1, auto_negotiate=False
        )
    assert L.balance(raja["wallet_address"]) == 0
    assert _faucet_rows() == []


def test_house_match_opens_from_real_balances_when_faucet_off(monkeypatch):
    from gaming.src.stack.agentic import ledger as L

    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "0")
    svc, raja, nero = _house_match_env(monkeypatch)
    for ag in (raja, nero):
        L.credit(ag["wallet_address"], Decimal("100"), reason="test_deposit")
    m = svc.create_match(agent_a_id=raja["agent_id"], agent_b_id=nero["agent_id"], stake_usdc=1)
    assert m["status"] == "open"
    assert _faucet_rows() == []


def _afm_world():
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()


def test_season_runs_on_testnet_by_default():
    from gaming.src.stack.agentic.games.football_managers import season as S

    _afm_world()
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    snap = S.get_season()
    assert snap["status"] == "open"
    assert all(e["paid"] for e in snap["entries"].values())


def test_season_entry_unpaid_when_faucet_off(monkeypatch):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "0")
    _afm_world()
    with pytest.raises(ValueError, match="fewer than two clubs could pay"):
        S.open_season(
            agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
            start_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
    assert _faucet_rows() == []

    # funded for real, the same season opens
    for aid in ("agent_bluelock_demo", "agent_aoashi_demo"):
        L.credit(S._wallet(aid), Decimal("100"), reason="test_deposit")
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    assert S.get_season()["status"] == "open"
    assert _faucet_rows() == []
