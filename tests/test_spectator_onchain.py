"""SpectatorPool projection + refuse commingled 'arena' books."""
from __future__ import annotations

from decimal import Decimal

import pytest

from gaming.src.stack.agentic.economy.spectator import SpectatorBook
from gaming.src.stack.agentic.metrics import build_public_metrics
from gaming.src.stack.agentic.spectator_onchain import (
    SpectatorOnchainError,
    assert_live_match_id,
    side_to_idx,
    spectator_onchain_enabled,
)


def test_refuse_arena_and_non_agm():
    with pytest.raises(SpectatorOnchainError, match="not 'arena'"):
        assert_live_match_id("arena")
    with pytest.raises(SpectatorOnchainError, match="not 'arena'"):
        assert_live_match_id("live")
    with pytest.raises(SpectatorOnchainError, match="Boardman match"):
        assert_live_match_id("something_else")
    assert assert_live_match_id("agm_abc123") == "agm_abc123"


def test_side_to_idx():
    assert side_to_idx("a") == 0
    assert side_to_idx("b") == 1
    with pytest.raises(SpectatorOnchainError):
        side_to_idx("white")


def test_flag_requires_address(monkeypatch):
    monkeypatch.setenv("SPECTATOR_ONCHAIN", "0")
    monkeypatch.setenv("SPECTATOR_ESCROW_ADDRESS", "0x" + "ab" * 20)
    assert spectator_onchain_enabled() is False
    monkeypatch.setenv("SPECTATOR_ONCHAIN", "1")
    assert spectator_onchain_enabled() is True
    monkeypatch.delenv("SPECTATOR_ESCROW_ADDRESS", raising=False)
    monkeypatch.setattr(
        "gaming.src.stack.agentic.spectator_onchain.spectator_pool_address",
        lambda: "",
    )
    # Re-import path: patch the function used by enabled()
    import gaming.src.stack.agentic.spectator_onchain as soc

    monkeypatch.setattr(soc, "spectator_pool_address", lambda: "")
    assert soc.spectator_onchain_enabled() is False


def test_project_deposit_idempotent_and_place_bet_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    book = SpectatorBook()
    mid = "agm_spec_proj_1"
    book.open_book(mid, agent_a_id="a", agent_b_id="b", pot_cap_usdc=Decimal("20"))
    with pytest.raises(ValueError, match="only for on-chain"):
        book.project_deposit(
            mid,
            bettor_id="fan",
            side="a",
            amount_usdc=Decimal("1"),
            tx_hash="0xabc",
        )
    book.mark_onchain(mid, pool="0xpool", open_tx_hash="0xopen")
    with pytest.raises(ValueError, match="on-chain book"):
        book.place_bet(mid, bettor_id="fan", side="a", amount_usdc=Decimal("1"))
    rec = book.project_deposit(
        mid,
        bettor_id="fan",
        side="a",
        amount_usdc=Decimal("1.25"),
        tx_hash="0xdead",
        explorer="https://testnet.arcscan.app/tx/0xdead",
    )
    again = book.project_deposit(
        mid,
        bettor_id="fan",
        side="a",
        amount_usdc=Decimal("1.25"),
        tx_hash="0xdead",
    )
    assert len(rec["bets"]) == 1
    assert len(again["bets"]) == 1
    assert Decimal(again["totals"]["a"]) == Decimal("1.25")
    assert rec["bets"][0]["tx_hash"] == "0xdead"


def test_circle_deposit_refuses_arena(monkeypatch):
    import asyncio
    from backend.services import spectator_escrow

    monkeypatch.setenv("SPECTATOR_ESCROW_ADDRESS", "0x" + "ab" * 20)
    with pytest.raises(spectator_escrow.SpectatorEscrowError, match="not 'arena'"):
        asyncio.run(spectator_escrow.deposit_to_pool("p", "arena", "a", Decimal("1")))


def test_metrics_surface_spectator_hashes():
    mid = "agm_metrics_spec"
    matches = {
        "matches": {
            mid: {
                "match_id": mid,
                "game_id": "agentic.chess_standard",
                "status": "locked",
                "stake_usdc": "1",
                "settlement_mode": "onchain",
                "agent_a_id": "agent_raja_kia_alekhine",
                "agent_b_id": "agent_nero_sicilian_french",
                "white_agent_id": "agent_raja_kia_alekhine",
                "black_agent_id": "agent_nero_sicilian_french",
                "created_at": "2026-08-14T00:00:00+00:00",
                "onchain": {"create_tx_hash": "0xlock"},
                "spectator_book": {
                    "status": "open",
                    "totals": {"a": "1.000000", "b": "0"},
                    "onchain": True,
                    "pool": "0xpool",
                    "open_tx_hash": "0xopen",
                    "bets": [
                        {
                            "side": "a",
                            "amount": "1.000000",
                            "tx_hash": "0xbet",
                            "explorer": "https://testnet.arcscan.app/tx/0xbet",
                        }
                    ],
                },
            }
        }
    }
    out = build_public_metrics(matches=matches, agents={"agents": {}}, lp_pools={"pools": {}})
    spec = out["matches"][0]["spectator"]
    assert spec["ledger_only"] is False
    hashes = {t["tx_hash"] for t in spec["txs"]}
    assert "0xopen" in hashes
    assert "0xbet" in hashes
    assert spec["pool"] == "0xpool"
