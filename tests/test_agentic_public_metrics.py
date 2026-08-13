"""Public PNL aggregator + unauthenticated /public/metrics route."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gaming.src.stack.agentic.metrics import (  # noqa: E402
    NERO_ID,
    RAJA_ID,
    build_public_metrics,
)


def _match(
    *,
    mid: str,
    status: str = "settled",
    result: str = "white_win",
    winner: str | None = RAJA_ID,
    stake: str = "5.000000",
    owner_payout: str = "9.700000",
    white: str = RAJA_ID,
    black: str = NERO_ID,
    onchain: bool = True,
    created_at: str = "2026-08-12T22:00:00+00:00",
) -> dict:
    rec = {
        "match_id": mid,
        "game_id": "agentic.chess_standard",
        "status": status,
        "result": result,
        "winner_agent_id": winner,
        "stake_usdc": stake,
        "settlement_mode": "onchain" if onchain else "demo_ledger",
        "chain_id": "arc",
        "agent_a_id": RAJA_ID,
        "agent_b_id": NERO_ID,
        "white_agent_id": white,
        "black_agent_id": black,
        "agent_a_wallet": "0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029",
        "agent_b_wallet": "0xe430C73cF2beD38aBE83DF8309763191624373E1",
        "created_at": created_at,
        "settled_at": created_at if status == "settled" else None,
        "fee_split": {
            "owner_payout": owner_payout,
            "platform_fee": "0.300000",
        },
        "economy": {"spectator_seed_a": "0.300000", "spectator_seed_b": "0.250000"},
        "spectator_book": {
            "status": "settled" if status == "settled" else "open",
            "totals": {"a": "0.300000", "b": "0.250000"},
            "payouts": {"mode": "winner_take_side" if winner else "refund"},
        },
        "pgn": "1. e4 e5 1-0",
    }
    if onchain:
        rec["onchain"] = {
            "create_tx_hash": "0xaaa",
            "join_tx_hash": "0xbbb",
            "escrow": "0x3cD57447490c81598Bd8CaCBe3843b24E5735A77",
            "txs": [
                {"step": "createMatch", "tx_hash": "0xaaa", "explorer": "https://testnet.arcscan.app/tx/0xaaa"},
                {"step": "joinMatch", "tx_hash": "0xbbb", "explorer": "https://testnet.arcscan.app/tx/0xbbb"},
            ],
        }
        rec["onchain_settle"] = {"tx_hash": "0xccc"}
    return rec


def test_win_loss_pnl_and_colors():
    matches = {
        "matches": {
            "m1": _match(mid="m1", owner_payout="9.700000"),
        }
    }
    out = build_public_metrics(matches=matches, agents={"agents": {}}, lp_pools={"pools": {}})
    by_id = {a["agent_id"]: a for a in out["agents"]}
    assert by_id[RAJA_ID]["wins"] == 1
    assert by_id[RAJA_ID]["white_games"] == 1
    assert by_id[NERO_ID]["losses"] == 1
    assert by_id[NERO_ID]["black_games"] == 1
    assert Decimal(by_id[RAJA_ID]["skill_pnl_usdc"]) == Decimal("4.700000")
    assert Decimal(by_id[NERO_ID]["skill_pnl_usdc"]) == Decimal("-5.000000")
    row = out["matches"][0]
    assert row["white"]["name"] == "Raja"
    assert row["black"]["name"] == "Nero"
    assert row["winner"]["name"] == "Raja"
    assert row["proofs"]["create_tx_hash"] == "0xaaa"
    assert row["proofs"]["settle_tx_hash"] == "0xccc"


def test_draw_is_zero_pnl_and_refund_seeds():
    matches = {
        "matches": {
            "d1": _match(
                mid="d1",
                result="draw",
                winner=None,
                owner_payout="0",
            ),
        }
    }
    matches["matches"]["d1"]["spectator_book"]["payouts"] = {"mode": "refund"}
    out = build_public_metrics(matches=matches, agents={"agents": {}}, lp_pools={"pools": {}})
    by_id = {a["agent_id"]: a for a in out["agents"]}
    assert by_id[RAJA_ID]["draws"] == 1
    assert by_id[NERO_ID]["draws"] == 1
    assert by_id[RAJA_ID]["skill_pnl_usdc"] == "0.000000"
    assert by_id[NERO_ID]["seed_spent_usdc"] == "0.000000"


def test_volume_counts_locked_and_settled():
    matches = {
        "matches": {
            "s": _match(mid="s", stake="1.000000"),
            "l": _match(mid="l", status="locked", result=None, winner=None, stake="2.000000"),
        }
    }
    out = build_public_metrics(matches=matches, agents={"agents": {}}, lp_pools={"pools": {}})
    vol = out["volume"]
    assert vol["matches_total"] == 2
    assert vol["matches_settled"] == 1
    assert vol["matches_locked"] == 1
    assert Decimal(vol["skill_volume_usdc"]) == Decimal("6.000000")  # 2*(1+2)


def test_public_route_no_api_key():
    from gaming.src.backend.main import app

    client = TestClient(app)
    r = client.get("/api/stack/agentic/public/metrics?limit=5")
    assert r.status_code == 200
    j = r.json()
    assert j.get("success") is True
    assert "volume" in j
    assert "agents" in j
    assert "matches" in j
    # no private material
    blob = str(j)
    assert "private_key" not in blob
    assert "secrets_" not in blob
