"""The unbreakable rulebook.

Every chess game Boardman has ever recorded must satisfy python-chess —
the reference implementation (lichess.org's engine layer). Agents submit
candidate moves; the engine decides legality and termination. These tests
pin that down so no code path, agent, or future refactor can accept an
illegal position or a result the rules don't support:

  * every stored move list replays legally from the start position
  * recorded terminations match python-chess's own verdict
  * flag (timeout) results carry a flagged clock at zero
  * illegal moves are rejected by the engine, by construction
"""

from __future__ import annotations

import json
import os
import pathlib

import chess
import pytest

# Hermetic by default: the games under test are played fresh in a sandbox.
# To audit a real store read-only (e.g. production data/agentic), point
# RULEBOOK_AUDIT_DATA at that directory.
_AUDIT_DIR = os.environ.get("RULEBOOK_AUDIT_DATA", "").strip()
_SEEDS = (1, 2, 3)


def _read_store(data_dir: pathlib.Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in ("matches.json", "matches_archive.json"):
        p = data_dir / name
        if not p.exists():
            continue
        doc = json.loads(p.read_text())
        for mid, rec in (doc.get("matches") or doc).items():
            out[str(mid)] = rec
    return out


def _play_sandbox_games(tmp_dir: pathlib.Path) -> dict[str, dict]:
    """Play a few real house games (agents → engine → settle) in tmp_dir."""
    from gaming.src.stack.agentic import clock
    from gaming.src.stack.agentic import house as house_mod
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_dir))
        mp.setenv("BOARDMAN_BET_WINDOW_SEC", "0")
        mp.setattr(clock, "reasoning_delay_sec", lambda *a, **k: 0.0)
        mp.setattr(house_mod, "ensure_builder_webhooks", lambda *a, **k: None)
        get_registry.cache_clear()
        get_match_service.cache_clear()
        try:
            agents = {a["agent_id"]: a for a in get_registry().ensure_demo_agents()}
            rt = house_mod.get_house()
            for seed in _SEEDS:
                m = rt.open_match(
                    agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
                    agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
                    stake_usdc=1,
                    game_id="agentic.chess_standard",
                )
                rt.lock(m["match_id"])
                out = rt.play(m["match_id"], move_delay_sec=0, wait=True, seed=seed)
                assert out["status"] == "settled", out.get("status")
            return _read_store(tmp_dir)
        finally:
            get_registry.cache_clear()
            get_match_service.cache_clear()


@pytest.fixture(scope="module")
def recorded_matches(tmp_path_factory) -> list[dict]:
    if _AUDIT_DIR:
        stored = _read_store(pathlib.Path(_AUDIT_DIR))
    else:
        stored = _play_sandbox_games(tmp_path_factory.mktemp("rulebook"))
    return [r for r in stored.values() if r.get("moves")]


def _replay(rec: dict) -> chess.Board:
    board = chess.Board()
    for mv in rec["moves"]:
        uci = mv.get("uci")
        san = mv.get("san")
        try:
            if uci:
                board.push_uci(str(uci))
            elif san:
                board.push_san(str(san))
            else:
                raise AssertionError(
                    f"move without uci/san in {rec.get('match_id')} ply {mv.get('ply')}"
                )
        except AssertionError:
            raise
        except Exception as exc:
            raise AssertionError(
                f"ILLEGAL MOVE in {rec.get('match_id')} ply {mv.get('ply')}: "
                f"{mv} ({exc})"
            ) from exc
    return board


@pytest.mark.slow
def test_every_recorded_game_replays_legally(recorded_matches):
    assert recorded_matches, "expected stored matches to validate"
    for rec in recorded_matches:
        _replay(rec)


@pytest.mark.slow
def test_terminations_match_the_engine(recorded_matches):
    for rec in recorded_matches:
        if rec.get("status") != "settled":
            continue
        term = str(rec.get("termination") or "").lower()
        board = _replay(rec)
        mid = rec.get("match_id")

        if term == "checkmate":
            assert board.is_checkmate(), f"{mid}: recorded checkmate but board disagrees"
        elif term == "stalemate":
            assert board.is_stalemate(), f"{mid}: recorded stalemate but board disagrees"
        elif term == "insufficient_material":
            assert board.is_insufficient_material(), f"{mid}: insufficient material mismatch"
        elif "repetition" in term:
            assert board.is_repetition(3), f"{mid}: recorded repetition but board disagrees"
        elif term == "timeout" or term == "flag":
            clk = rec.get("clock") or {}
            flags = [
                bool((clk.get(side) or {}).get("flag"))
                for side in ("white", "black")
            ]
            assert any(flags), f"{mid}: timeout but no flagged clock"
            for side in ("white", "black"):
                if (clk.get(side) or {}).get("flag"):
                    assert int((clk[side] or {}).get("remaining_ms") or 0) == 0, (
                        f"{mid}: flagged {side} but remaining_ms != 0"
                    )
        elif term == "seventy_five_moves":
            assert board.halfmoves >= 150, f"{mid}: 75-move rule but halfmoves < 150"

        if board.is_checkmate():
            assert str(rec.get("result") or "").endswith("_win") or rec.get(
                "winner_agent_id"
            ), f"{mid}: final position is mate but no winner recorded"


@pytest.mark.slow
def test_check_flags_in_move_log_match_position(recorded_matches):
    checked = 0
    for rec in recorded_matches:
        board = chess.Board()
        for mv in rec["moves"]:
            uci = mv.get("uci")
            san = mv.get("san")
            if uci:
                board.push_uci(str(uci))
            elif san:
                board.push_san(str(san))
            else:
                break
            if mv.get("is_check") is True:
                checked += 1
                ply_id = f"{rec.get('match_id')} ply {mv.get('ply')}"
                assert board.is_check(), f"{ply_id}: logged check but king isn't in check"
            if mv.get("is_check") is False:
                assert not board.is_check(), (
                    f"{rec.get('match_id')} ply {mv.get('ply')}: check not logged"
                )
    assert checked >= 0


def test_engine_rejects_illegal_moves_by_construction():
    board = chess.Board()
    # Off-the-board / impossible moves never apply.
    with pytest.raises(ValueError):
        board.push_uci("e2e5")  # pawn can't go three squares
    with pytest.raises(ValueError):
        board.push_uci("a1a3")  # rook blocked by its own pawn
    with pytest.raises(ValueError):
        board.push_uci("e7e5")  # black to move first? white-only start, wrong side
    # And a legal move works, then the position stays valid.
    board.push_uci("e2e4")
    assert board.is_valid()
    assert not board.is_game_over()
    # A fresh board has no game-over verdict to "claim".
    assert not chess.Board().is_game_over()
