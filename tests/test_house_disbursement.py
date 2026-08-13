"""Boardman House cannot send funds except via BoardmanEscrow triggers."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "0")
    monkeypatch.setenv("BOARDMAN_ALLOW_LEDGER_FALLBACK", "0")
    monkeypatch.setenv("BOARDMAN_HOUSE_TABLES", "5")
    monkeypatch.setattr(
        "gaming.src.stack.agentic.onchain.onchain_enabled", lambda: False
    )
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.matches import get_match_service

    get_registry.cache_clear()
    get_match_service.cache_clear()
    from gaming.src.stack.agentic import house as house_mod

    with house_mod._floor_lock:
        house_mod._workers.clear()
        if house_mod._pool is not None:
            house_mod._pool.shutdown(wait=False)
            house_mod._pool = None
    return get_registry()


def _match_shell(a_wallet: str, b_wallet: str, **extra):
    rec = {
        "match_id": "agm_deadbeef12",
        "status": "locked",
        "stake_usdc": "5",
        "chain_id": "arc",
        "agent_a_id": "agent_a",
        "agent_b_id": "agent_b",
        "white_agent_id": "agent_a",
        "black_agent_id": "agent_b",
        "agent_a_wallet": a_wallet,
        "agent_b_wallet": b_wallet,
    }
    rec.update(extra)
    return rec


A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"
RND = "0x3333333333333333333333333333333333333333"


def test_resolve_requires_authorization():
    from gaming.src.stack.agentic.disbursement import DisbursementDenied
    from gaming.src.stack.agentic.onchain import resolve_onchain

    try:
        resolve_onchain("agm_x", RND, draw=False)
        assert False, "must refuse unsigned resolve"
    except DisbursementDenied as e:
        assert "AuthorizedDisbursement" in str(e)


def test_refuse_random_winner():
    from gaming.src.stack.agentic.disbursement import (
        DisbursementDenied,
        authorize_skill_settlement,
    )

    white = {"agent_id": "agent_a", "wallet_address": A}
    black = {"agent_id": "agent_b", "wallet_address": B}
    m = _match_shell(A, B)
    try:
        authorize_skill_settlement(
            m,
            {"result": "white_win", "winner_agent_id": "agent_stranger"},
            white=white,
            black=black,
        )
        assert False
    except DisbursementDenied:
        pass


def test_refuse_malformed_result_as_draw():
    from gaming.src.stack.agentic.disbursement import (
        DisbursementDenied,
        authorize_skill_settlement,
    )

    white = {"agent_id": "agent_a", "wallet_address": A}
    black = {"agent_id": "agent_b", "wallet_address": B}
    try:
        authorize_skill_settlement(
            _match_shell(A, B),
            {"result": "", "winner_agent_id": None},
            white=white,
            black=black,
        )
        assert False, "empty result must not become a draw refund"
    except DisbursementDenied as e:
        assert "not terminal" in str(e)


def test_refuse_contradictory_result():
    from gaming.src.stack.agentic.disbursement import (
        DisbursementDenied,
        authorize_skill_settlement,
    )

    white = {"agent_id": "agent_a", "wallet_address": A}
    black = {"agent_id": "agent_b", "wallet_address": B}
    try:
        authorize_skill_settlement(
            _match_shell(A, B),
            {"result": "white_win", "winner_agent_id": "agent_b"},
            white=white,
            black=black,
        )
        assert False
    except DisbursementDenied:
        pass


def test_win_authorization_binds_player_wallet():
    from gaming.src.stack.agentic.disbursement import authorize_skill_settlement

    white = {"agent_id": "agent_a", "wallet_address": A}
    black = {"agent_id": "agent_b", "wallet_address": B}
    auth = authorize_skill_settlement(
        _match_shell(A, B),
        {"result": "white_win", "winner_agent_id": "agent_a"},
        white=white,
        black=black,
    )
    assert auth.trigger == "MATCH_RESOLVE_WIN"
    assert auth.action == "resolve"
    assert auth.winner_wallet == A
    auth.assert_for_resolve("agm_deadbeef12", A, False)
    try:
        auth.assert_for_resolve("agm_deadbeef12", RND, False)
        assert False
    except Exception:
        pass


def test_draw_is_cancel_not_resolve():
    from gaming.src.stack.agentic.disbursement import authorize_skill_settlement

    white = {"agent_id": "agent_a", "wallet_address": A}
    black = {"agent_id": "agent_b", "wallet_address": B}
    auth = authorize_skill_settlement(
        _match_shell(A, B),
        {"result": "draw"},
        white=white,
        black=black,
    )
    assert auth.action == "cancel"
    assert auth.trigger == "MATCH_RESOLVE_DRAW"
    assert auth.winner_wallet is None


def test_winner_wallet_when_white_is_agent_b():
    from gaming.src.stack.agentic.disbursement import winner_wallet_for_match

    m = _match_shell(
        A,
        B,
        white_agent_id="agent_b",
        black_agent_id="agent_a",
        winner_agent_id="agent_a",
        onchain_player1=B,  # white created = agent_b
        onchain_player2=A,
    )
    # Old bug: p1 if winner==agent_a else p2 → would pay B (the loser).
    assert winner_wallet_for_match(m) == A


def test_abort_refused_while_playing():
    from gaming.src.stack.agentic.disbursement import DisbursementDenied, authorize_abort

    try:
        authorize_abort(_match_shell(A, B, status="playing"), reason="ops_abort")
        assert False
    except DisbursementDenied:
        pass


def test_house_escrow_call_rejects_erc20_transfer():
    from gaming.src.stack.agentic.disbursement import (
        DisbursementDenied,
        assert_house_escrow_call,
    )

    escrow = "0x3cD57447490c81598Bd8CaCBe3843b24E5735A77"
    try:
        assert_house_escrow_call(
            {"to": escrow, "data": "0xa9059cbb" + "00" * 64},
            escrow,
            "transfer",
        )
        assert False
    except DisbursementDenied as e:
        assert "transfer" in str(e).lower() or "cannot" in str(e).lower()

    try:
        assert_house_escrow_call(
            {"to": RND, "data": "0x60ffcc74" + "00" * 64},
            escrow,
            "resolveMatch",
        )
        assert False
    except DisbursementDenied as e:
        assert "BoardmanEscrow" in str(e)

    assert_house_escrow_call(
        {"to": escrow, "data": "0x60ffcc74" + "00" * 128},
        escrow,
        "resolveMatch",
    )


def test_faucet_refuses_resolver_key_and_random_dest(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.disbursement import (
        DisbursementDenied,
        assert_faucet_destination,
        assert_not_resolver_funder,
    )
    from gaming.src.stack.agentic.house import ensure_house

    ensure_house()
    resolver = "0x" + "11" * 32
    monkeypatch.setenv("BOARDMAN_RESOLVER_KEY", resolver)
    try:
        assert_not_resolver_funder(resolver)
        assert False
    except DisbursementDenied:
        pass

    try:
        assert_faucet_destination(RND)
        assert False
    except DisbursementDenied:
        pass


def test_fund_agent_from_key_no_resolver_fallback(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.delenv("BOARDMAN_FUNDER_KEY", raising=False)
    monkeypatch.setenv("BOARDMAN_RESOLVER_KEY", "0x" + "11" * 32)
    from gaming.src.stack.agentic.disbursement import DisbursementDenied
    from gaming.src.stack.agentic.onchain import fund_agent_from_key
    from decimal import Decimal

    try:
        fund_agent_from_key(A, Decimal("1"))
        assert False
    except DisbursementDenied as e:
        assert "FUNDER" in str(e) or "resolver" in str(e).lower()


def test_onchain_lock_does_not_silently_fallback(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "1")
    monkeypatch.setenv("BOARDMAN_ALLOW_LEDGER_FALLBACK", "0")
    monkeypatch.setattr(
        "gaming.src.stack.agentic.onchain.onchain_enabled", lambda: True
    )
    from gaming.src.stack.agentic.disbursement import DisbursementDenied
    from gaming.src.stack.agentic.house import get_house

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    raja = agents["agent_raja_kia_alekhine"]["agent_id"]
    nero = agents["agent_nero_sicilian_french"]["agent_id"]
    rt = get_house()
    m = rt.open_match(agent_a_id=raja, agent_b_id=nero, stake_usdc=1)

    def _boom(*_a, **_k):
        raise RuntimeError("rpc down")

    monkeypatch.setattr(
        "gaming.src.stack.agentic.onchain.dual_lock_onchain", _boom
    )
    try:
        rt.lock(m["match_id"])
        assert False, "must not fall back to demo ledger"
    except DisbursementDenied as e:
        assert "fallback" in str(e).lower() or "on-chain lock" in str(e).lower()
    from gaming.src.stack.agentic.matches import get_match_service

    saved = get_match_service().get(m["match_id"])
    assert saved["status"] == "lock_failed"


def test_house_cannot_bet_on_itself(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from decimal import Decimal
    from gaming.src.stack.agentic.house import HOUSE_ID, get_house

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
    )
    try:
        rt.take_bet(m["match_id"], bettor_id=HOUSE_ID, side="a", amount_usdc=Decimal("1"))
        assert False
    except ValueError as e:
        assert "cannot bet" in str(e).lower()


def test_house_secrets_sealed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import HOUSE_ID, ensure_house
    from gaming.src.stack.agentic.onchain import load_agent_private_key
    from gaming.src.stack.agentic.store import load_json

    ensure_house()
    secrets = load_json(f"secrets_{HOUSE_ID}.json", {})
    assert secrets.get("private_key") in {None, ""}
    assert secrets.get("sealed") is True
    try:
        load_agent_private_key(HOUSE_ID)
        assert False, "house key must not be re-derived from seed"
    except RuntimeError as e:
        assert "no spend key" in str(e).lower()


def test_snapshot_advertises_guardrails(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import get_house

    snap = get_house().snapshot()
    assert snap["can_erc20_transfer"] is False
    g = snap["guardrails"]
    assert g["can_pick_recipient"] is False
    assert g["can_pick_amount"] is False
    assert "MATCH_RESOLVE_WIN" in g["allowed_triggers"]
    assert "resolveMatch" in g["allowed_house_calls"]
    assert "transfer" in g["forbidden_house_calls"]
    assert g["funds_held_by"] == "BoardmanEscrow"


def test_lock_refuses_settled_match(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.disbursement import DisbursementDenied, authorize_skill_lock
    from gaming.src.stack.agentic.house import get_house

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
    )
    m["status"] = "settled"
    try:
        authorize_skill_lock(m)
        assert False
    except DisbursementDenied:
        pass
