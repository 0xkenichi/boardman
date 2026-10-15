"""One football wallet per person (AFM deep dive B9).

AFM bets used the bare ``<profile_id>`` ledger key; marketplace buys and
proceeds used ``owner:<profile_id>``. Now the bridge, AFM bets (stake,
payout, refund), marketplace buys and stack-API chess tickets all use
``owner:<profile_id>``; a legacy bare-key balance is migrated into it on
first use — except chess spectator credits minted onto bare keys before
tickets were funded, which stay behind for ops review.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.party_wallet import (
    football_wallet,
    is_person,
    legacy_spectator_mints,
    merge_legacy_wallet,
)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield


def test_canonical_key_and_people_only():
    assert football_wallet("8f1c-Profile") == "owner:8f1c-profile"
    for system in ("agent_raja_kia_alekhine", "afm_season_1_pot", "0xabc", "owner:p1", "creator_x", "house", "lp:a"):
        assert not is_person(system)
        with pytest.raises(ValueError):
            football_wallet(system)
        assert merge_legacy_wallet(system) == 0


def test_legacy_balance_is_migrated_once_and_conserved():
    ledger.credit("p1", Decimal("12.5"), reason="afm_bet_payout", ref="fx")  # old AFM winnings
    total = ledger.total_micro()
    assert merge_legacy_wallet("p1") == Decimal("12.5")
    assert ledger.balance("p1") == 0 and ledger.balance("owner:p1") == Decimal("12.5")
    assert merge_legacy_wallet("p1") == 0  # idempotent
    assert ledger.total_micro() == total
    reasons = [t["reason"] for t in ledger.txs(ref="owner:p1")] + [t["reason"] for t in ledger.txs(ref="p1")]
    assert "football_wallet_merge_out" in reasons and "football_wallet_merge_in" in reasons


def test_minted_chess_spectator_credits_are_never_made_spendable():
    ledger.credit("p2", Decimal("3"), reason="afm_bet_payout", ref="fx")
    ledger.credit("p2", Decimal("4"), reason="spectator_win", ref="agm_old")  # minted by the old settle
    ledger.credit("p2", Decimal("1"), reason="draw_win", ref="agm_old")
    assert legacy_spectator_mints("p2") == Decimal("5")
    assert merge_legacy_wallet("p2") == Decimal("3")
    assert ledger.balance("owner:p2") == Decimal("3") and ledger.balance("p2") == Decimal("5")
    assert merge_legacy_wallet("p2") == 0


def test_bridge_bets_and_marketplace_share_one_wallet(monkeypatch):
    """Legacy betting balance + a bridge deposit are spendable on a manager
    buy; AFM winnings land where the marketplace can spend them."""
    from gaming.src.stack.agentic import wallet_bridge as wb
    from gaming.src.stack.agentic.games.football_managers.betting import _payee

    ledger.credit("p3", Decimal("4"), reason="afm_bet_payout", ref="fx")  # legacy key
    out = wb.deposit("p3", "6", "dep-one-wallet", chain_usdc=Decimal("10"))
    assert out["status"] == "completed"
    assert out["ledger_balance_usdc"] == "10"  # 4 migrated + 6 bridged
    assert ledger.balance("p3") == 0
    assert _payee("p3") == "owner:p3"
    assert _payee("afm_season_1_pot") == "afm_season_1_pot"


def test_merge_script_dry_run_then_apply(capsys):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "merge_football_wallets", Path(__file__).resolve().parents[1] / "scripts" / "merge_football_wallets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ledger.credit("p4", Decimal("2"), reason="afm_bet_payout", ref="fx")
    ledger.credit("p4", Decimal("1"), reason="spectator_win", ref="agm_old")
    ledger.credit("afm_season_1_pot", Decimal("9"), reason="x", ref="x")
    assert mod.main([], bootstrap=False) == 0
    out = capsys.readouterr().out
    assert "p4: balance 3" in out and "held back 1" in out and "afm_season" not in out
    assert ledger.balance("owner:p4") == 0
    assert mod.main(["--apply"], bootstrap=False) == 0
    assert ledger.balance("owner:p4") == Decimal("2") and ledger.balance("p4") == Decimal("1")
