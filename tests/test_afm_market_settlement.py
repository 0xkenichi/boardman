"""AFM manager sales — real buyer wallet / on-chain USDC settlement rail.

Dual mode: the demo ledger stays the default; a sale settles in real Arc USDC
from the buyer's bound Circle wallet when Circle is configured and every party
has a bound wallet. These tests exercise the rail with a fake Circle service:

  - party wallet binding + recipient resolution (incl. registered agents)
  - auto rail selection (onchain when ready, ledger fallback otherwise)
  - buy-now settling onchain (single seller leg, no ledger touch)
  - resale onchain (creator-cut + seller legs, real addresses)
  - fail-closed: not-ready / short balance / failed transfer never move
    ownership, and a forced-onchain sale never falls back silently
"""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.delenv("CIRCLE_API_KEY", raising=False)
    monkeypatch.delenv("CIRCLE_ENTITY_SECRET", raising=False)
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    """Manager + club under tmp store, plus the market service fns."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
        list_manager_for_sale,
    )

    return {"create": create_manager_agent, "list": list_manager_for_sale}


class _Transfers:
    """Record of every Circle transfer a FakeCircle was asked to send."""

    def __init__(self) -> None:
        self.calls: list[dict] = []


class FakeCircle:
    """CircleWalletService stand-in: balance read + transfer + confirm."""

    def __init__(
        self,
        *,
        balance_usdc: Decimal = Decimal("1000"),
        balance_error: str | None = None,
        fail_kinds: set[str] | None = None,
        transfers: _Transfers | None = None,
    ) -> None:
        self.balance_usdc = balance_usdc
        self.balance_error = balance_error
        self.fail_kinds = fail_kinds or set()  # {"transfer", "confirm"}
        self.transfers = transfers or _Transfers()
        self._n = 0

    def get_wallet_balance(self, address: str) -> dict:
        if self.balance_error:
            return {"success": False, "error": self.balance_error}
        return {"success": True, "balance_usdc": float(self.balance_usdc)}

    def transfer_usdc(self, from_wallet_id: str, to_address: str, amount_usdc: float) -> dict:
        self._n += 1
        if "transfer" in self.fail_kinds and self._n == 1:
            return {"success": False, "error": "circle rejected the transfer"}
        self.transfers.calls.append(
            {
                "from_wallet_id": from_wallet_id,
                "to_address": to_address,
                "amount_usdc": amount_usdc,
            }
        )
        tx_id = f"circle_tx_{self._n}"
        return {
            "success": True,
            "transaction_id": tx_id,
            "status": "PENDING",
            "tx_hash": None,
            "to_address": to_address,
            "amount_usdc": amount_usdc,
        }

    def wait_for_transaction(self, transaction_id: str) -> dict:
        if "confirm" in self.fail_kinds:
            return {"success": False, "error": "transaction failed on-chain", "status": "FAILED"}
        return {
            "success": True,
            "status": "CONFIRMED",
            "tx_hash": f"0x{'a' * 63}",
        }


@pytest.fixture()
def _live(monkeypatch):
    """Wire the real-USDC rail: Circle keys present + a fake service."""
    monkeypatch.setenv("CIRCLE_API_KEY", "test-key")
    monkeypatch.setenv("CIRCLE_ENTITY_SECRET", "0" * 64)
    transfers = _Transfers()
    fake = FakeCircle(transfers=transfers)
    from gaming.src.stack.agentic.games.football_managers import agent_market as M

    monkeypatch.setattr(M, "_circle", lambda chain_id="arc": fake)
    return {"fake": fake, "transfers": transfers, "M": M}


BUYER_ADDR = "0x1111111111111111111111111111111111111111"
DEV_ADDR = "0x2222222222222222222222222222222222222222"
ALICE_ADDR = "0x3333333333333333333333333333333333333333"


# ------------------------------------------------------------ binding store


def test_bind_resolve_and_unbind_party_wallets(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        get_party_wallet,
        party_payout_address,
        party_send_wallet,
        unbind_party_wallet,
    )

    buyer = bind_party_wallet(party_id="alice_real", address=BUYER_ADDR, wallet_id="wallet_alice")
    assert buyer["can_send"] is True
    assert buyer["address"] == BUYER_ADDR and buyer["wallet_id"] == "wallet_alice"

    # payout-only binding (recipient: no wallet_id)
    bind_party_wallet(party_id="dev_real", address=DEV_ADDR)
    w = get_party_wallet("dev_real")
    assert w["can_send"] is False and party_payout_address("dev_real") == DEV_ADDR
    assert party_send_wallet("dev_real") is None
    assert party_send_wallet("alice_real")["address"] == BUYER_ADDR

    # bad addresses rejected
    with pytest.raises(ValueError, match="invalid wallet address"):
        bind_party_wallet(party_id="x", address="0x1234")
    with pytest.raises(ValueError, match="party_id"):
        bind_party_wallet(party_id="", address=DEV_ADDR)

    # unbind removes; a mismatched address cannot unbind someone else's binding
    assert unbind_party_wallet(party_id="dev_real") is True
    assert get_party_wallet("dev_real") is None
    with pytest.raises(ValueError, match="does not match"):
        unbind_party_wallet(party_id="alice_real", address=DEV_ADDR)
    assert get_party_wallet("alice_real") is not None


def test_registered_agent_resolves_as_payout_wallet(_world):
    """A registered agent party is payable at its registry wallet_address —
    no explicit binding needed (receiving only, no send wallet_id)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        get_party_wallet,
        party_payout_address,
    )
    from gaming.src.stack.agentic.registry import get_registry

    rec = get_registry().register_agent(
        agent_id="agent_payable_test",
        name="Payable Bot",
        owner_id="someone",
        strategy_id="custom",
        openings=[],
        mind={},
    )
    w = get_party_wallet("agent_payable_test")
    assert w["can_send"] is False and w["source"] == "registry_agent"
    assert party_payout_address("agent_payable_test") == rec["wallet_address"].lower()
    assert party_payout_address("nobody_here") is None


# ------------------------------------------------------------ rail selection


def test_buy_now_settles_onchain_when_wallets_bound(_world, _live):
    """Auto mode: with Circle keys + every party bound, a purchase moves real
    USDC from the buyer's Circle wallet to the seller — and never touches the
    demo ledger."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Forge Real", owner_id="dev_real")["agent"]
    aid = dev["agent_id"]
    bind_party_wallet(party_id="dev_real", address=DEV_ADDR)  # receives
    bind_party_wallet(party_id="alice_real", address=BUYER_ADDR, wallet_id="wallet_alice")  # pays
    _world["list"](agent_id=aid, price_usdc="40.00", creator_cut_bps=500, listed_by="dev_real")

    res = purchase_manager_agent(agent_id=aid, buyer_id="alice_real", settlement="auto")
    sale = res["sale"]
    assert sale["mode"] == "onchain"
    assert sale["first_sale"] is True
    assert sale["seller_payout_usdc"] == "40.00" and sale["creator_cut_usdc"] == "0"
    assert sale["buyer_wallet"] == BUYER_ADDR
    assert sale["seller_wallet"] == DEV_ADDR

    # one leg to the developer's payout address from the buyer's Circle wallet
    legs = sale["settlement"]["legs"]
    assert len(legs) == 1
    leg = legs[0]
    assert leg["kind"] == "seller_payout" and leg["to_address"] == DEV_ADDR
    assert leg["amount_usdc"] == "40.00"
    assert leg["transaction_id"] and leg["tx_hash"] and leg["status"] == "CONFIRMED"
    assert _live["transfers"].calls == [
        {"from_wallet_id": "wallet_alice", "to_address": DEV_ADDR, "amount_usdc": 40.0}
    ]

    # ownership moved, listing closed, mode recorded on the stored agent record
    assert res["agent"]["owner_id"] == "alice_real" and res["agent"]["listed"] is False
    assert res["agent"]["sales_count"] == 1
    from gaming.src.stack.agentic.registry import get_registry

    stored = get_registry().get_agent(aid)
    assert stored["last_sale"]["mode"] == "onchain"
    assert stored["last_sale"]["settlement"]["legs"][0]["transaction_id"]

    # the demo ledger saw no sale money
    snap = L.snapshot()
    assert not any(
        str(tx.get("reason") or "").startswith("afm_agent_sale") for tx in snap["txs"]
    )


def test_resale_onchain_pays_creator_cut_as_second_leg(_world, _live):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Royalty Real", owner_id="dev_two")["agent"]
    aid = dev["agent_id"]
    bind_party_wallet(party_id="dev_two", address=DEV_ADDR)  # developer
    # alice's Circle wallet both pays for the first sale AND receives the resale
    bind_party_wallet(party_id="alice_real", address=ALICE_ADDR, wallet_id="wallet_alice")
    bind_party_wallet(party_id="bob_real", address=BUYER_ADDR, wallet_id="wallet_bob")

    _world["list"](agent_id=aid, price_usdc="60.00", creator_cut_bps=1000, listed_by="dev_two")
    first = purchase_manager_agent(agent_id=aid, buyer_id="alice_real")  # dev keeps $60
    assert first["sale"]["mode"] == "onchain" and len(first["sale"]["settlement"]["legs"]) == 1

    # alice relists; bob buys onchain → two legs: 10% to the dev, rest to alice
    _world["list"](agent_id=aid, price_usdc="50.00", creator_cut_bps=1000, listed_by="alice_real")
    res = purchase_manager_agent(agent_id=aid, buyer_id="bob_real")
    sale = res["sale"]
    assert sale["mode"] == "onchain" and sale["first_sale"] is False
    assert sale["creator_cut_usdc"] == "5.00" and sale["seller_payout_usdc"] == "45.00"
    legs = sale["settlement"]["legs"]
    assert [(lg["kind"], lg["to_address"], lg["amount_usdc"]) for lg in legs] == [
        ("creator_cut", DEV_ADDR, "5.00"),
        ("seller_payout", ALICE_ADDR, "45.00"),
    ]
    assert res["agent"]["owner_id"] == "bob_real"

    calls = _live["transfers"].calls
    assert calls[-2] == {"from_wallet_id": "wallet_bob", "to_address": DEV_ADDR, "amount_usdc": 5.0}
    assert calls[-1] == {
        "from_wallet_id": "wallet_bob",
        "to_address": ALICE_ADDR,
        "amount_usdc": 45.0,
    }
    assert L.balance("owner:dev_two") == 0 and L.balance("owner:alice_real") == 0


def test_auto_falls_back_to_ledger_and_force_ledger_never_touches_circle(_world, _live):
    """Not ready → ledger; forcing ledger skips Circle even when ready."""
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Dual Mode FC", owner_id="dev_dual")["agent"]
    aid = dev["agent_id"]
    _world["list"](agent_id=aid, price_usdc="25.00", listed_by="dev_dual")

    # nobody bound → auto settles on the demo ledger exactly as before
    res = purchase_manager_agent(agent_id=aid, buyer_id="buyer_x")
    assert res["sale"]["mode"] == "ledger"
    assert str(L.balance("owner:dev_dual")) == "25.00"
    assert _live["transfers"].calls == []

    # now ready, but forced ledger must still skip Circle entirely
    dev2 = _world["create"](manager_name="Dual Mode B", owner_id="dev_dual2")["agent"]
    aid2 = dev2["agent_id"]
    bind_party_wallet(party_id="dev_dual2", address=DEV_ADDR)
    bind_party_wallet(party_id="payer_y", address=BUYER_ADDR, wallet_id="wallet_y")
    _world["list"](agent_id=aid2, price_usdc="10.00", listed_by="dev_dual2")
    res2 = purchase_manager_agent(agent_id=aid2, buyer_id="payer_y", settlement="ledger")
    assert res2["sale"]["mode"] == "ledger"
    assert _live["transfers"].calls == []


def test_force_onchain_raises_when_rail_not_ready(_world, monkeypatch):
    monkeypatch.setenv("CIRCLE_API_KEY", "test-key")
    monkeypatch.setenv("CIRCLE_ENTITY_SECRET", "0" * 64)
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Wants Real", owner_id="dev_wants")["agent"]
    aid = dev["agent_id"]
    _world["list"](agent_id=aid, price_usdc="20.00", listed_by="dev_wants")

    # no wallets bound anywhere → onchain impossible, no silent ledger
    with pytest.raises(ValueError, match="real-USDC settlement unavailable"):
        purchase_manager_agent(agent_id=aid, buyer_id="buyer_z", settlement="onchain")
    # nothing moved, listing intact
    assert dev["owner_id"] == "dev_wants"


def test_short_balance_fails_closed(_world, _live):
    """Buyer's real wallet must cover the price before any leg is sent."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        purchase_manager_agent,
    )

    _live["fake"].balance_usdc = Decimal("10.00")
    dev = _world["create"](manager_name="Poor Buyer FC", owner_id="dev_poor")["agent"]
    aid = dev["agent_id"]
    bind_party_wallet(party_id="dev_poor", address=DEV_ADDR)
    bind_party_wallet(party_id="poor_alice", address=BUYER_ADDR, wallet_id="wallet_poor")
    _world["list"](agent_id=aid, price_usdc="40.00", listed_by="dev_poor")

    with pytest.raises(RuntimeError, match="has \\$10"):
        purchase_manager_agent(agent_id=aid, buyer_id="poor_alice", settlement="onchain")
    assert _live["transfers"].calls == []  # balance gate → zero legs
    # listing intact, ownership untouched
    from gaming.src.stack.agentic.registry import get_registry

    assert get_registry().get_agent(aid)["owner_id"] == "dev_poor"


def test_failed_transfer_never_moves_ownership(_world, _live):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        list_manager_for_sale,
        list_market_agents,
        purchase_manager_agent,
    )

    _live["fake"].fail_kinds.add("transfer")
    dev = _world["create"](manager_name="Fail Closed FC", owner_id="dev_fail")["agent"]
    aid = dev["agent_id"]
    bind_party_wallet(party_id="dev_fail", address=DEV_ADDR)
    bind_party_wallet(party_id="buyer_f", address=BUYER_ADDR, wallet_id="wallet_f")
    list_manager_for_sale(agent_id=aid, price_usdc="30.00", listed_by="dev_fail")

    with pytest.raises(RuntimeError, match="failed"):
        purchase_manager_agent(agent_id=aid, buyer_id="buyer_f", settlement="onchain")

    # still the developer's, still listed, no transfer recorded
    from gaming.src.stack.agentic.registry import get_registry

    assert get_registry().get_agent(aid)["owner_id"] == "dev_fail"
    listed = [a for a in list_market_agents() if a["agent_id"] == aid][0]
    assert listed["listed"] is True and listed["owner_id"] == "dev_fail"
    assert _live["transfers"].calls == []


def test_unconfirmed_transfer_fails_closed(_world, _live):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        purchase_manager_agent,
    )

    _live["fake"].fail_kinds.add("confirm")
    dev = _world["create"](manager_name="Confirm FC", owner_id="dev_conf")["agent"]
    aid = dev["agent_id"]
    bind_party_wallet(party_id="dev_conf", address=DEV_ADDR)
    bind_party_wallet(party_id="buyer_g", address=BUYER_ADDR, wallet_id="wallet_g")
    _world["list"](agent_id=aid, price_usdc="15.00", listed_by="dev_conf")

    with pytest.raises(RuntimeError, match="not confirmed"):
        purchase_manager_agent(agent_id=aid, buyer_id="buyer_g", settlement="onchain")


def test_market_rows_flag_onchain_payable(_world, _live):
    """Rows say whether a sale could settle in real USDC today — buyer aside."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
        list_market_agents,
        list_manager_for_sale,
    )

    dev = _world["create"](manager_name="Payable Rows", owner_id="dev_rows")["agent"]
    aid = dev["agent_id"]
    list_manager_for_sale(agent_id=aid, price_usdc="10.00", listed_by="dev_rows")

    # unbound owner → not payable onchain yet
    rows = {a["agent_id"]: a for a in list_market_agents()}
    assert rows[aid]["onchain_payable"] is False
    assert rows["agent_bluelock_demo"]["onchain_payable"] is False  # unbound studio

    bind_party_wallet(party_id="dev_rows", address=DEV_ADDR)
    rows = {a["agent_id"]: a for a in list_market_agents()}
    assert rows[aid]["onchain_payable"] is True


def test_offer_accepted_settles_onchain(_world, _live):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        accept_manager_offer,
        bind_party_wallet,
        list_manager_for_sale,
        make_manager_offer,
        purchase_manager_agent,
    )

    dev = _world["create"](manager_name="Offer Real", owner_id="dev_offer")["agent"]
    aid = dev["agent_id"]
    bind_party_wallet(party_id="dev_offer", address=DEV_ADDR)
    bind_party_wallet(party_id="offer_alice", address=ALICE_ADDR, wallet_id="wallet_offer_a")
    bind_party_wallet(party_id="offer_bob", address=BUYER_ADDR, wallet_id="wallet_offer_b")

    list_manager_for_sale(agent_id=aid, price_usdc="60.00", creator_cut_bps=500, listed_by="dev_offer")
    purchase_manager_agent(agent_id=aid, buyer_id="offer_alice")
    list_manager_for_sale(
        agent_id=aid,
        price_usdc="70.00",
        creator_cut_bps=500,
        reserve_price_usdc="40.00",
        listed_by="offer_alice",
    )
    made = make_manager_offer(agent_id=aid, offer_usdc="55.00", buyer_id="offer_bob")
    oid = next(p["offer_id"] for p in made["agent"]["pending_offers"])

    res = accept_manager_offer(agent_id=aid, offer_id=oid, accept_by="offer_alice")
    sale = res["sale"]
    assert sale["mode"] == "onchain" and sale["source"] == "offer_accepted"
    assert sale["price_usdc"] == "55.00"
    assert sale["creator_cut_usdc"] == "2.75"  # 5% → developer
    assert sale["seller_payout_usdc"] == "52.25"
    assert res["agent"]["owner_id"] == "offer_bob"

    # last two legs: creator cut to the dev, remainder to alice's wallet
    calls = _live["transfers"].calls[-2:]
    assert calls[0]["to_address"] == DEV_ADDR and calls[0]["amount_usdc"] == 2.75
    assert calls[1]["to_address"] == ALICE_ADDR and calls[1]["amount_usdc"] == 52.25
