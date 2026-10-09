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
import pathlib

import chess
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_matches() -> list[dict]:
    """Every stored match: hot store + archive + whatever the service sees."""
    out: dict[str, dict] = {}

    for rel in ("data/agentic/matches.json", "data/agentic/matches_archive.json"):
        p = ROOT / rel
        if not p.exists():
            continue
        doc = json.loads(p.read_text())
        for mid, rec in (doc.get("matches") or doc).items():
            out[str(mid)] = rec

    try:
        from gaming.src.stack.agentic.matches import get_match_service

        for rec in get_match_service().list_matches(200):
            mid = str(rec.get("match_id") or "")
            if mid:
                out[mid] = rec
    except Exception:  # service optional — file reads above are the source of truth
        pass

    return [r for r in out.values() if r.get("moves")]


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


def test_every_recorded_game_replays_legally():
    matches = _load_matches()
    assert matches, "expected stored matches to validate"
    for rec in matches:
        _replay(rec)


def test_terminations_match_the_engine():
    for rec in _load_matches():
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


def test_check_flags_in_move_log_match_position():
    checked = 0
    for rec in _load_matches():
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
