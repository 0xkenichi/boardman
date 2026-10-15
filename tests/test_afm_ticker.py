"""The football clock must run in production and survive bad AFM state."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_afm_is_a_default_supervisor_role(monkeypatch):
    sa = _load("deploy/start_akash.py", "start_akash_under_test")
    monkeypatch.delenv("BOARDMAN_PROCS", raising=False)
    assert "afm" in sa._roles()
    monkeypatch.setenv("BOARDMAN_PROCS", "webhooks,house,afm")
    assert sa._roles() >= {"house", "afm"}


def test_compose_runs_exactly_one_ticker():
    text = (ROOT / "docker-compose.yml").read_text()
    assert text.count("afm") == 1 and '"webhooks,house,afm"' in text


def test_tick_once_swallows_failures(monkeypatch, capsys):
    ticker = _load("scripts/afm_ticker.py", "afm_ticker_under_test")
    from gaming.src.stack.agentic.games.football_managers import cup, season

    def boom(*a, **k):
        raise RuntimeError("bad state")

    monkeypatch.setattr(season, "tick", boom)
    monkeypatch.setattr(cup, "tick", boom)
    ticker.tick_once()  # must not raise
    out = capsys.readouterr().out
    assert "season tick failed" in out and "cup tick failed" in out
