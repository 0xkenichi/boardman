"""Wallet bridge: play balance <-> football ledger wallet, exactly once.

The play balance (on-chain play-address USDC + the play_adjust overlay) and
the agentic ledger are two stores; a transfer is an outbox row written before
either side moves. These tests drive the HTTP routes as the Next BFF does
(master key + X-Boardman-Caller), crash between the two sides, and check the
reconciler finishes every transfer with the money conserved to the micro.
The chain read is faked: no Circle, no RPC, no Supabase.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic import wallet_bridge as wb

MASTER = "sk_master_test"
BUILDER = "sk_builder_alice"
BASE = "/api/stack/agentic/football/wallet"


class SimulatedCrash(BaseException):
    """The process dies between two legs (no `except Exception` catches it)."""


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_ALLOW_OPEN", "NETWORK"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", f"{BUILDER}:alice_lab")
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    yield


@pytest.fixture()
def chain(monkeypatch):
    """Per-party on-chain play-address USDC (what Circle would report)."""
    balances: dict[str, Decimal] = {"p1": Decimal("20"), "p2": Decimal("50")}

    async def _read(party: str) -> Decimal:
        if party not in balances:
            raise wb.BalanceUnavailable("rpc down")
        return balances[party]

    monkeypatch.setattr(wb, "read_play_chain_usdc", _read)
    return balances


@pytest.fixture()
def client(chain):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from gaming.src.stack.agentic import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.router)
    return TestClient(app)


def _as(caller: str | None = None, key: str = MASTER) -> dict[str, str]:
    h = {"X-Boardman-Key": key}
    if caller:
        h["X-Boardman-Caller"] = caller
    return h


def _play(party: str, chain: dict[str, Decimal]) -> Decimal:
    from gaming.src.backend.services.play_adjust import get_adjust

    return chain.get(party, Decimal("0")) + get_adjust(party)


def _football(party: str) -> Decimal:
    return ledger.balance(f"owner:{party}")


def _total(chain: dict[str, Decimal], *parties: str) -> Decimal:
    return sum((_play(p, chain) + _football(p) for p in parties), Decimal("0"))


# ── happy paths ──────────────────────────────────────────────────────────────


def test_deposit_then_withdraw_moves_exact_amounts(client, chain):
    before = _total(chain, "p1")
    r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "7.500001", "idempotency_key": "dep-0001"})
    assert r.status_code == 200, r.text
    assert r.json()["transfer"]["status"] == "completed"
    assert r.json()["ledger_balance_usdc"] == "7.500001"
    assert _football("p1") == Decimal("7.500001")
    assert _play("p1", chain) == Decimal("12.499999")

    r = client.post(f"{BASE}/withdraw", headers=_as("p1"), json={"amount": "2.25", "idempotency_key": "wd-00001"})
    assert r.status_code == 200, r.text
    assert _football("p1") == Decimal("5.250001")
    assert _play("p1", chain) == Decimal("14.749999")
    assert _total(chain, "p1") == before

    r = client.get(BASE, headers=_as("p1"))
    assert r.status_code == 200
    body = r.json()
    assert body["ledger_wallet"] == "owner:p1" and body["ledger_balance_usdc"] == "5.250001"
    assert [t["direction"] for t in body["transfers"]] == ["withdraw", "deposit"]


def test_bridged_money_buys_on_the_marketplace_ledger_rail(client, chain):
    """The point of the bridge: a fresh testnet player with no Circle wallet
    bound can pay from owner:<party> after moving play balance in."""
    client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "10", "idempotency_key": "dep-buy-1"})
    from gaming.src.stack.agentic.games.football_managers.agent_market import _owner_party_wallet

    assert _owner_party_wallet("p1") == "owner:p1"
    assert ledger.balance(_owner_party_wallet("p1")) == Decimal("10")


# ── refusals ─────────────────────────────────────────────────────────────────


def test_insufficient_funds_moves_nothing(client, chain):
    r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "20.000001", "idempotency_key": "dep-big-1"})
    assert r.status_code == 402, r.text
    assert _football("p1") == 0 and _play("p1", chain) == Decimal("20")
    assert wb.get("p1|dep-big-1")["status"] == "failed"
    # The same key answers the same way; it never half-applies later.
    r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "20.000001", "idempotency_key": "dep-big-1"})
    assert r.status_code == 402

    r = client.post(f"{BASE}/withdraw", headers=_as("p1"), json={"amount": "0.000001", "idempotency_key": "wd-empty-1"})
    assert r.status_code == 402, r.text
    assert wb.get("p1|wd-empty-1") is None  # the ledger debit and row roll back together
    assert _play("p1", chain) == Decimal("20")


def test_amounts_are_exact_and_positive(client, chain):
    for bad in ("0", "-1", "1.0000001", "abc", "10000.000001"):
        r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": bad, "idempotency_key": f"bad-{bad}-key"})
        assert r.status_code in {400, 422}, (bad, r.text)
    assert _play("p1", chain) == Decimal("20") and _football("p1") == 0


def test_unreadable_play_balance_refuses(client, chain):
    r = client.post(f"{BASE}/deposit", headers=_as("ghost"), json={"amount": "1", "idempotency_key": "dep-ghost-1"})
    assert r.status_code == 503
    assert wb.get("ghost|dep-ghost-1") is None


def test_mainnet_refuses_deposits_into_the_book_entry_wallet(client, chain, monkeypatch):
    monkeypatch.setenv("NETWORK", "mainnet")
    r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "1", "idempotency_key": "dep-main-1"})
    assert r.status_code == 400 and "testnet" in r.text


# ── idempotency ──────────────────────────────────────────────────────────────


def test_retry_with_the_same_key_moves_money_once(client, chain):
    for _ in range(3):
        r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "3", "idempotency_key": "dep-retry-1"})
        assert r.status_code == 200, r.text
        assert r.json()["transfer"]["transfer_key"] == "p1|dep-retry-1"
    assert _football("p1") == Decimal("3") and _play("p1", chain) == Decimal("17")
    for _ in range(2):
        r = client.post(f"{BASE}/withdraw", headers=_as("p1"), json={"amount": "1", "idempotency_key": "wd-retry-1"})
        assert r.status_code == 200, r.text
    assert _football("p1") == Decimal("2") and _play("p1", chain) == Decimal("18")
    # Same key, different transfer: refused, nothing moves.
    r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "4", "idempotency_key": "dep-retry-1"})
    assert r.status_code == 409
    r = client.post(f"{BASE}/withdraw", headers=_as("p1"), json={"amount": "3", "idempotency_key": "dep-retry-1"})
    assert r.status_code == 409
    assert _football("p1") == Decimal("2")


def test_keys_are_scoped_per_party(client, chain):
    assert client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "1", "idempotency_key": "shared-key-1"}).status_code == 200
    assert client.post(f"{BASE}/deposit", headers=_as("p2"), json={"amount": "2", "idempotency_key": "shared-key-1"}).status_code == 200
    assert _football("p1") == Decimal("1") and _football("p2") == Decimal("2")


# ── crash between the two sides, then the reconciler ─────────────────────────


def _crash_at(monkeypatch, leg: str) -> None:
    def _hook(name: str) -> None:
        if name == leg:
            raise SimulatedCrash(name)

    monkeypatch.setattr(wb, "_LEG_HOOK", _hook)


@pytest.mark.parametrize("leg", ["deposit:debited", "deposit:recorded"])
def test_deposit_crash_between_debit_and_credit_is_finished_by_the_reconciler(chain, monkeypatch, leg):
    before = _total(chain, "p1")
    _crash_at(monkeypatch, leg)
    with pytest.raises(SimulatedCrash):
        wb.deposit("p1", "6", "dep-crash-1", chain_usdc=chain["p1"])
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    # The play balance was debited, the ledger not yet credited: the row
    # holds the money in between.
    row = wb.get("p1|dep-crash-1")
    assert row["status"] in {"pending", "debited"}
    assert _play("p1", chain) == Decimal("14") and _football("p1") == 0
    assert [r["transfer_key"] for r in wb.pending()] == ["p1|dep-crash-1"]

    # A young row is left alone (a live request may still be finishing it).
    assert wb.reconcile() == []
    out = wb.reconcile(older_than_sec=0)
    assert [(r["transfer_key"], r["status"]) for r in out] == [("p1|dep-crash-1", "completed")]
    assert _football("p1") == Decimal("6") and _play("p1", chain) == Decimal("14")
    assert _total(chain, "p1") == before
    # Again: nothing open, nothing moves.
    assert wb.reconcile(older_than_sec=0) == []
    assert _football("p1") == Decimal("6")
    # The client's retry gets the finished transfer, not a second one.
    assert wb.deposit("p1", "6", "dep-crash-1", chain_usdc=chain["p1"])["status"] == "completed"
    assert _football("p1") == Decimal("6") and _play("p1", chain) == Decimal("14")


def test_withdraw_crash_between_debit_and_credit_is_finished_by_the_reconciler(chain, monkeypatch):
    wb.deposit("p1", "5", "dep-seed-01", chain_usdc=chain["p1"])
    before = _total(chain, "p1")
    _crash_at(monkeypatch, "withdraw:debited")
    with pytest.raises(SimulatedCrash):
        wb.withdraw("p1", "4", "wd-crash-01")
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    assert wb.get("p1|wd-crash-01")["status"] == "debited"
    assert _football("p1") == Decimal("1") and _play("p1", chain) == Decimal("15")
    out = wb.reconcile(older_than_sec=0)
    assert [r["status"] for r in out] == ["completed"]
    assert _football("p1") == Decimal("1") and _play("p1", chain) == Decimal("19")
    assert _total(chain, "p1") == before


def test_withdraw_crash_after_the_credit_is_closed_without_paying_twice(chain, monkeypatch):
    wb.deposit("p1", "5", "dep-seed-02", chain_usdc=chain["p1"])
    _crash_at(monkeypatch, "withdraw:credited")
    with pytest.raises(SimulatedCrash):
        wb.withdraw("p1", "4", "wd-crash-02")
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    assert _play("p1", chain) == Decimal("19")  # credit landed, row still open
    wb.reconcile(older_than_sec=0)
    assert wb.get("p1|wd-crash-02")["status"] == "completed"
    assert _play("p1", chain) == Decimal("19") and _football("p1") == Decimal("1")


def test_abandoned_deposit_that_never_debited_is_failed(chain):
    from gaming.src.stack.agentic.db import transaction

    with transaction() as tx:
        wb._insert(tx, "p1|dep-orphan-1", "p1", wb.DEPOSIT, 2_000_000, "owner:p1", "pending")
    out = wb.reconcile(older_than_sec=0)
    assert [r["status"] for r in out] == ["failed"]
    assert _play("p1", chain) == Decimal("20") and _football("p1") == 0


def test_ops_can_reverse_a_stuck_deposit_instead_of_finishing_it(chain, monkeypatch):
    before = _total(chain, "p1")
    _crash_at(monkeypatch, "deposit:recorded")
    with pytest.raises(SimulatedCrash):
        wb.deposit("p1", "3", "dep-undo-01", chain_usdc=chain["p1"])
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    assert [r["action"] for r in wb.reconcile(older_than_sec=0, dry_run=True, reverse_keys={"p1|dep-undo-01"})] == ["would_reverse"]
    out = wb.reconcile(older_than_sec=0, reverse_keys={"p1|dep-undo-01"})
    assert [r["status"] for r in out] == ["reversed"]
    assert _play("p1", chain) == Decimal("20") and _football("p1") == 0
    assert _total(chain, "p1") == before
    wb.reconcile(older_than_sec=0, reverse_keys={"p1|dep-undo-01"})
    assert _play("p1", chain) == Decimal("20")


def test_maintenance_tick_runs_the_reconciler(chain, monkeypatch):
    from gaming.src.stack.agentic import fee_sweep

    monkeypatch.setenv("BOARDMAN_BRIDGE_STALE_SEC", "1")
    _crash_at(monkeypatch, "deposit:debited")
    with pytest.raises(SimulatedCrash):
        wb.deposit("p1", "2", "dep-tick-01", chain_usdc=chain["p1"])
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    from gaming.src.stack.agentic.db import transaction

    with transaction() as tx:  # age the row past the stale threshold
        tx.execute("UPDATE wallet_bridge_transfers SET updated_at_ms = 0 WHERE transfer_key = ?", ("p1|dep-tick-01",))
    out = fee_sweep.maintenance_tick()
    assert [r["status"] for r in out["bridge_reconciled"]] == ["completed"]
    assert _football("p1") == Decimal("2")


# ── nobody moves someone else's money ────────────────────────────────────────


def test_caller_cannot_move_someone_elses_money(client, chain):
    client.post(f"{BASE}/deposit", headers=_as("p2"), json={"amount": "10", "idempotency_key": "dep-p2-0001"})
    snap = (_play("p1", chain), _football("p1"), _play("p2", chain), _football("p2"))
    for path in ("deposit", "withdraw"):
        # Signed-in p1 naming p2 in the body.
        r = client.post(f"{BASE}/{path}", headers=_as("p1"), json={"party_id": "p2", "amount": "1", "idempotency_key": f"steal-{path}-1"})
        assert r.status_code == 403, r.text
        # A builder key, with or without a caller header.
        r = client.post(f"{BASE}/{path}", headers=_as(None, BUILDER), json={"party_id": "p2", "amount": "1", "idempotency_key": f"steal-{path}-2"})
        assert r.status_code == 403, r.text
        r = client.post(f"{BASE}/{path}", headers=_as("p2", BUILDER), json={"amount": "1", "idempotency_key": f"steal-{path}-3"})
        assert r.status_code == 403, r.text
        # No key at all.
        r = client.post(f"{BASE}/{path}", json={"amount": "1", "idempotency_key": f"steal-{path}-4"})
        assert r.status_code == 401
    r = client.get(BASE + "?party_id=p2", headers=_as("p1"))
    assert r.status_code == 403
    # p1 re-using p2's idempotency key acts on p1's own key space only.
    r = client.post(f"{BASE}/withdraw", headers=_as("p1"), json={"amount": "10", "idempotency_key": "dep-p2-0001"})
    assert r.status_code == 402
    assert (_play("p1", chain), _football("p1"), _play("p2", chain), _football("p2")) == snap


def test_system_wallets_are_never_bridged(chain):
    for party in ("creator_studio", "agent_raja_kia_alekhine", "0xabc", "owner:p1", "house"):
        with pytest.raises(wb.BridgeError, match="own wallet"):
            wb.withdraw(party, "1", "sys-wallet-1")
        with pytest.raises(wb.BridgeError, match="own wallet"):
            wb.deposit(party, "1", "sys-wallet-2", chain_usdc=Decimal("5"))


def test_ops_script_is_dry_run_first(chain, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "reconcile_wallet_bridge", Path(__file__).resolve().parents[1] / "scripts" / "reconcile_wallet_bridge.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _crash_at(monkeypatch, "deposit:debited")
    with pytest.raises(SimulatedCrash):
        wb.deposit("p1", "1.5", "dep-script-1", chain_usdc=chain["p1"])
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    assert mod.main(["--all"], bootstrap=False) == 0
    assert "Dry run" in capsys.readouterr().out
    assert _football("p1") == 0
    assert mod.main(["--all", "--apply"], bootstrap=False) == 0
    assert _football("p1") == Decimal("1.5")
    assert mod.main(["--party", "p1"], bootstrap=False) == 0
    assert "completed" in capsys.readouterr().out


def test_admin_lists_pending_transfers(client, chain, monkeypatch):
    _crash_at(monkeypatch, "deposit:debited")
    with pytest.raises(SimulatedCrash):
        wb.deposit("p1", "1", "dep-admin-01", chain_usdc=chain["p1"])
    monkeypatch.setattr(wb, "_LEG_HOOK", None)
    r = client.get("/api/stack/agentic/admin/wallet-bridge/pending", headers=_as())
    assert r.status_code == 200
    assert [t["transfer_key"] for t in r.json()["transfers"]] == ["p1|dep-admin-01"]
    assert client.get("/api/stack/agentic/admin/wallet-bridge/pending", headers=_as("p1")).status_code == 403
