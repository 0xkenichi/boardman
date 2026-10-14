"""Raja's lichess-bot-style UCI path (local Stockfish via python-chess)."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import chess
import pytest

_REPO = Path(__file__).resolve().parents[1]


def test_find_stockfish_respects_env(tmp_path, monkeypatch):
    from gaming.src.stack.agentic.chess import lichess_uci

    fake = tmp_path / "stockfish"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("STOCKFISH_PATH", str(fake))
    monkeypatch.delenv("RAJA_STOCKFISH", raising=False)
    assert lichess_uci.find_stockfish() == str(fake)


def test_find_stockfish_missing(monkeypatch):
    from gaming.src.stack.agentic.chess import lichess_uci

    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    monkeypatch.delenv("RAJA_STOCKFISH", raising=False)
    monkeypatch.setattr(lichess_uci, "_repo_root", lambda: Path("/no/such/boardman"))
    monkeypatch.setattr(lichess_uci.shutil, "which", lambda _n: None)
    assert lichess_uci.find_stockfish() == ""
    assert lichess_uci.engine_ready() is False
    assert lichess_uci.best_move("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") is None


def test_best_move_startpos_when_binary_present():
    from gaming.src.stack.agentic.chess import lichess_uci

    if not lichess_uci.engine_ready():
        pytest.skip("no local Stockfish")
    board = chess.Board()
    legal = [m.uci() for m in board.legal_moves]
    mv = lichess_uci.best_move(board.fen(), legal_moves=legal, movetime_ms=80)
    assert mv in legal


# Since 853f9ae the shared brain (agent_brain → HybridEngine) plays
# mate → authored opening book → LLM → local UCI multipv (best_candidates) →
# remote API → styled fallback. These tests use quiet middlegame positions
# past the book's ply limit so the local-engine step is what's exercised,
# and stub the engine so results never depend on a Stockfish binary.
_W_MIDDLEGAME = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"
_B_MIDDLEGAME = "r1bq1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P3/2NP1N2/PPP2PPP/R2Q1RK1 b - - 1 7"
# Sources that can only come from lichess_uci.best_candidates (local engine).
_LOCAL_UCI_SOURCES = ("local_sf", "blend")


def _legal(fen: str) -> list[str]:
    return [m.uci() for m in chess.Board(fen).legal_moves]


def _local_engine(monkeypatch, move: str | None, seen: dict | None = None):
    """Stockfish on, local UCI returns ``move`` (or nothing), remote API off.

    Match-play threads left running by earlier tests can call the same
    patched engine (and pick moves for Raja/Nero) while these tests run, so
    the stub records only calls from the test's own thread, and the asserts
    read ``runtime.last_source()`` (per thread), never the process-wide
    ``LAST_SOURCE`` another game may have overwritten.
    """
    from gaming.src.stack.agentic.chess import lichess_uci
    from gaming.src.stack.agentic.chess import stockfish_client

    monkeypatch.setenv("BOARDMAN_USE_STOCKFISH", "1")
    monkeypatch.setenv("BOARDMAN_GM_PURE", "1")
    monkeypatch.setenv("BOARDMAN_BOOK_PLIES", "10")
    owner = threading.get_ident()

    def fake_candidates(fen, **kwargs):
        if seen is not None and threading.get_ident() == owner:
            seen["fen"] = fen
            seen.update(kwargs)
        return [{"uci": move, "eval_pawns": 0.3, "mate": None}] if move else []

    def no_remote(*_a, **_k):
        raise RuntimeError("remote Stockfish disabled in tests")

    monkeypatch.setattr(lichess_uci, "best_candidates", fake_candidates)
    monkeypatch.setattr(stockfish_client, "analyze", no_remote)


def test_raja_uses_uci_when_ready(monkeypatch):
    from gaming.src.stack.agentic.agents.raja import runtime

    seen: dict = {}
    _local_engine(monkeypatch, "c1g5", seen)
    legal = _legal(_W_MIDDLEGAME)
    assert "c1g5" in legal
    mv = runtime.pick_move(fen=_W_MIDDLEGAME, legal_moves=legal)
    assert mv == "c1g5"
    assert runtime.last_source().startswith(_LOCAL_UCI_SOURCES), runtime.last_source()
    assert seen["fen"] == _W_MIDDLEGAME


def test_raja_falls_back_when_uci_missing(monkeypatch):
    from gaming.src.stack.agentic.agents.raja import runtime

    _local_engine(monkeypatch, None)
    legal = _legal(_W_MIDDLEGAME)
    mv = runtime.pick_move(fen=_W_MIDDLEGAME, legal_moves=legal)
    assert mv in legal
    assert runtime.last_source() == "local_styled_fallback"


def test_handle_webhook_reads_clocks(monkeypatch):
    from gaming.src.stack.agentic.agents.raja import runtime
    from gaming.src.stack.agentic.chess import lichess_uci

    body = {
        "game_id": "agentic.chess_standard",
        "state": {
            "fen": _B_MIDDLEGAME,
            "clocks": {"wtime_ms": 20000, "btime_ms": 10000, "inc_ms": 2000},
        },
        "legal_moves": _legal(_B_MIDDLEGAME),
    }
    clocks = lichess_uci.clocks_from_webhook(body)
    assert clocks["wtime_ms"] == 20000
    assert clocks["btime_ms"] == 10000
    assert clocks["winc_ms"] == 2000
    assert clocks["binc_ms"] == 2000

    seen: dict = {}
    _local_engine(monkeypatch, "h7h6", seen)
    mv = runtime.handle_webhook(body)
    assert mv == "h7h6"
    # Clock-aware budget: 5% of the tighter clock (10s) → 500 ms think.
    assert seen.get("movetime_ms") == 500


def test_homemade_raja_search_legal(monkeypatch):
    import sys

    sys.path.insert(0, str(_REPO / "builders" / "lichess_raja"))
    import homemade as homemade_mod

    monkeypatch.setattr(
        homemade_mod,
        "raja_search",
        homemade_mod.raja_search,
    )
    board = chess.Board()
    mv = homemade_mod.raja_search(board, movetime_ms=50)
    assert mv in board.legal_moves


def test_nero_uses_uci_when_ready(monkeypatch):
    from gaming.src.stack.agentic.agents.nero import runtime

    _local_engine(monkeypatch, "h7h6")
    legal = _legal(_B_MIDDLEGAME)
    assert runtime.pick_move(fen=_B_MIDDLEGAME, legal_moves=legal) == "h7h6"
    assert runtime.last_source().startswith(_LOCAL_UCI_SOURCES), runtime.last_source()


def test_lichess_identity_links_wallet_without_storing_token(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "0")
    env = {
        "LICHESS_RAJA_API_TOKEN": "lip_test_raja_token_xx",
        "RAJA_LICHESS_USER": "myrajafromboardman",
    }
    from gaming.src.stack.agentic.lichess_identity import public_identity, token_for

    ident = public_identity("agent_raja_kia_alekhine", live=False, env=env)
    assert ident["linked"] is True
    assert ident["username"] == "myrajafromboardman"
    assert ident["token_env"] == "LICHESS_RAJA_API_TOKEN"
    assert "lip_" not in str(ident)
    assert token_for("agent_nero_sicilian_french", env) == ""
    nero = public_identity("agent_nero_sicilian_french", live=False, env=env)
    assert nero["linked"] is False
    assert nero["token_env"] == "LICHESS_NERO_API_TOKEN"


def test_raja_uci_adapter_speaks_uci():
    import subprocess

    script = _REPO / "builders" / "lichess_raja" / "raja_uci.py"
    env = os.environ.copy()
    env["RAJA_UCI_MOVETIME_MS"] = "80"
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [env.get("PYTHON") or "python3", str(script)],
        input="uci\nisready\nposition startpos\ngo movetime 80\nquit\n",
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        cwd=str(_REPO),
    )
    out = proc.stdout
    assert "uciok" in out
    assert "readyok" in out
    assert "bestmove " in out
    best = [ln.split()[1] for ln in out.splitlines() if ln.startswith("bestmove ")][0]
    board = chess.Board()
    assert best in {m.uci() for m in board.legal_moves}
