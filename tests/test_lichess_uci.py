"""Raja's lichess-bot-style UCI path (local Stockfish via python-chess)."""
from __future__ import annotations

import os
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


def test_raja_uses_uci_when_ready(monkeypatch):
    from gaming.src.stack.agentic.agents.raja import runtime

    called = {}

    def fake_best(fen, **kwargs):
        called["fen"] = fen
        return "e2e4"

    monkeypatch.setattr(runtime.lichess_uci, "best_move", fake_best)
    board = chess.Board()
    legal = [m.uci() for m in board.legal_moves]
    mv = runtime.pick_move(fen=board.fen(), legal_moves=legal)
    assert mv == "e2e4"
    assert runtime.LAST_SOURCE == "lichess_uci"
    assert called["fen"] == board.fen()


def test_raja_falls_back_when_uci_missing(monkeypatch):
    from gaming.src.stack.agentic.agents.raja import runtime

    monkeypatch.setattr(runtime.lichess_uci, "best_move", lambda *a, **k: None)
    board = chess.Board()
    legal = [m.uci() for m in board.legal_moves]
    mv = runtime.pick_move(fen=board.fen(), legal_moves=legal)
    assert mv in legal
    assert runtime.LAST_SOURCE != "lichess_uci"


def test_handle_webhook_reads_clocks(monkeypatch):
    from gaming.src.stack.agentic.agents.raja import runtime

    seen = {}

    def fake_best(fen, **kwargs):
        seen.update(kwargs)
        return "e7e5"

    monkeypatch.setattr(runtime.lichess_uci, "best_move", fake_best)
    mv = runtime.handle_webhook(
        {
            "game_id": "agentic.chess_standard",
            "state": {
                "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
                "clocks": {"wtime_ms": 180000, "btime_ms": 179000, "inc_ms": 2000},
            },
            "legal_moves": ["e7e5", "c7c5"],
        }
    )
    assert mv == "e7e5"
    assert seen.get("wtime_ms") == 180000
    assert seen.get("btime_ms") == 179000
    assert seen.get("winc_ms") == 2000


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

    monkeypatch.setattr(runtime.lichess_uci, "best_move", lambda *a, **k: "e7e5")
    board = chess.Board()
    board.push_uci("e2e4")
    legal = [m.uci() for m in board.legal_moves]
    assert runtime.pick_move(fen=board.fen(), legal_moves=legal) == "e7e5"
    assert runtime.LAST_SOURCE == "lichess_uci"


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
