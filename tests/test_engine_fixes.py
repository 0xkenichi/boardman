"""Regression tests for chess runtime fixes (webhook server, silo fallback, UCI retry)."""
from __future__ import annotations

import chess
import pytest


def test_builder_webhook_uses_threading_server():
    import inspect

    import gaming.src.stack.agentic.runtime.webhook as wh

    src = inspect.getsource(wh.serve_builder_webhook)
    assert "ThreadingHTTPServer((host" in src, "health checks must survive long thinks"
    assert not __import__("re").search(r"=\s*HTTPServer\(", src), "no bare single-thread server"


def test_clocks_kwargs_from_state():
    from gaming.src.stack.agentic.runtime.webhook import clocks_kwargs_from_state

    out = clocks_kwargs_from_state(
        {
            "clocks": {
                "wtime_ms": 60000,
                "btime_ms": 55000,
                "inc_ms": 2000,
                "movetime_ms": 0,  # dropped
                "junk": "x",
            }
        }
    )
    assert out == {
        "wtime_ms": 60000,
        "btime_ms": 55000,
        "winc_ms": 2000,
        "binc_ms": 2000,
    }
    assert clocks_kwargs_from_state({}) == {}
    assert clocks_kwargs_from_state({"clocks": "garbage"}) == {}
    assert clocks_kwargs_from_state(None) == {}


def test_silo_fallback_forwards_clocks(monkeypatch):
    import gaming.src.stack.agentic.runtime.webhook as wh

    seen = {}

    def fake_pick(**kwargs):
        seen.update(kwargs)
        return "e2e4"

    monkeypatch.setitem(
        __import__("sys").modules,
        "gaming.src.stack.agentic.agents.raja.runtime",
        type("M", (), {"pick_move": staticmethod(fake_pick)}),
    )
    mv = wh.ask_agent_move(
        {"agent_id": "agent_raja_kia_alekhine"},  # no webhook_url → silo path
        game_id="agentic.chess_standard",
        state={
            "fen": chess.Board().fen(),
            "clocks": {"wtime_ms": 60000, "btime_ms": 55000, "inc_ms": 2000},
        },
        legal_moves=["e2e4", "d2d4"],
    )
    assert mv == "e2e4"
    assert seen.get("wtime_ms") == 60000
    assert seen.get("binc_ms") == 2000


class _DyingEngine:
    """Stands in for a Stockfish process that dies mid-session."""

    def play(self, *a, **k):
        raise RuntimeError("engine died")


def test_uci_retry_recovers_from_dead_session(monkeypatch):
    """A crashed Stockfish must restart on the next call, not fail forever."""
    from gaming.src.stack.agentic.chess import lichess_uci

    if not lichess_uci.engine_ready():
        pytest.skip("no local Stockfish")

    calls = {"n": 0}
    real_get = lichess_uci._get_engine  # capture BEFORE patching

    def dying_then_alive():
        calls["n"] += 1
        if calls["n"] == 1:
            return _DyingEngine()  # play() will raise → reset + retry
        return real_get()  # fresh real session

    monkeypatch.setattr(lichess_uci, "_get_engine", dying_then_alive)
    board = chess.Board()
    legal = [m.uci() for m in board.legal_moves]
    mv = lichess_uci.best_move(board.fen(), legal_moves=legal, movetime_ms=80)
    assert mv in legal
    assert calls["n"] == 2


def test_last_source_resets_between_requests(monkeypatch):
    """LAST_SOURCE must describe the current move, not the last engine hit."""
    # Since 853f9ae Raja's runtime delegates to the shared brain
    # (agent_brain.pick_with_brain → HybridEngine); LAST_SOURCE is whatever
    # engine step produced THIS move.
    from gaming.src.stack.agentic.agents.raja import runtime as raja
    from gaming.src.stack.agentic.chess import agent_brain

    board = chess.Board()
    legal = [m.uci() for m in board.legal_moves]
    script = [("e2e4", "opening_book"), ("d2d4", "local_sf+gm_d18")]

    class FakeEngine:
        def __init__(self, *a, **k):
            self.uci, self.last_source = script.pop(0)
            self.last_eval = None

        def choose_move(self, b):
            return chess.Move.from_uci(self.uci)

    monkeypatch.setattr(agent_brain, "HybridEngine", FakeEngine)
    assert raja.pick_move(fen=board.fen(), legal_moves=legal) == "e2e4"
    assert raja.LAST_SOURCE == "opening_book"

    # A different engine step on the next request replaces the old source
    assert raja.pick_move(fen=board.fen(), legal_moves=legal) == "d2d4"
    assert raja.LAST_SOURCE == "local_sf+gm_d18"

    # A request that fails must not keep reporting the previous move's source
    class BrokenEngine(FakeEngine):
        def __init__(self, *a, **k):
            self.last_source = "never_reported"

        def choose_move(self, b):
            raise RuntimeError("engine died")

    monkeypatch.setattr(agent_brain, "HybridEngine", BrokenEngine)
    with pytest.raises(RuntimeError):
        raja.pick_move(fen=board.fen(), legal_moves=legal)
    assert raja.LAST_SOURCE != "local_sf+gm_d18"
