"""Money audit 2026-10 — ledger guards and the mainnet decision.

PoCs for AUDIT_2026-10_money.md:

* M-13  A testnet SPECTATOR_CHAIN override replaced the settlement chain in
        the mainnet check: with a mainnet default chain, is_mainnet() said
        False, so spectator betting and the demo faucet defaulted ON.
* M-14  Defence in depth on the book-entry ledger: a non-positive escrow
        stake minted on lock(), a negative credit() was a silent debit, and a
        voided spectator book could still be settled (refund + winnings).
"""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("NETWORK", "CLAW_DEFAULT_CHAIN", "BOARDMAN_SETTLEMENT_RAIL", "SPECTATOR_CHAIN",
              "SPECTATOR_BETTING_ENABLED", "BOARDMAN_DEMO_FAUCET"):
        monkeypatch.delenv(k, raising=False)


def test_testnet_spectator_chain_cannot_mask_a_mainnet_settlement_chain(monkeypatch):
    import gaming.src.backend.services.chains as chains
    from gaming.src.backend.services import spectator_policy as sp
    from gaming.src.stack.agentic import ledger

    monkeypatch.setattr(chains, "default_chain_id", lambda: "arc_mainnet")
    monkeypatch.setenv("SPECTATOR_CHAIN", "arc")
    assert sp.is_mainnet() is True
    assert sp.spectator_betting_decision(None)[0] is False
    assert ledger.demo_faucet_mode() is False


def test_testnet_stays_testnet(monkeypatch):
    from gaming.src.backend.services import spectator_policy as sp

    monkeypatch.setenv("SPECTATOR_CHAIN", "arc")
    assert sp.is_mainnet() is False


def test_open_escrow_refuses_a_non_positive_stake():
    from gaming.src.stack.agentic import ledger

    for stake in (Decimal("-5"), Decimal("0")):
        with pytest.raises(ValueError):
            ledger.open_escrow("agm_neg", agent_a_wallet="0xa", agent_b_wallet="0xb", stake_usdc=stake)
    assert ledger.get_escrow("agm_neg") is None
    assert ledger.total_micro() == 0


def test_negative_credit_is_refused():
    from gaming.src.stack.agentic import ledger

    ledger.credit("w1", Decimal("10"), reason="fund")
    with pytest.raises(ValueError):
        ledger.credit("w1", Decimal("-4"), reason="oops")
    assert ledger.balance("w1") == Decimal("10")


def test_a_void_book_cannot_be_settled():
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    SpectatorBook().open_book("agm_void", agent_a_id="x", agent_b_id="y", pot_cap_usdc=Decimal("100"))
    SpectatorBook().place_bet("agm_void", bettor_id="fan", side="a", amount_usdc=Decimal("5"), funding="profile")
    SpectatorBook().void("agm_void", reason="aborted")
    with pytest.raises(ValueError):
        SpectatorBook().settle("agm_void", winner_side="a")
    assert SpectatorBook().get("agm_void")["status"] == "void"
