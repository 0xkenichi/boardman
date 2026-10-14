from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gaming.src.backend.main import app  # noqa: E402

_KEY = "test-catalog-key"


@pytest.fixture(autouse=True)
def _stack_key(monkeypatch):
    # football routes require a Stack API key like every other data route
    monkeypatch.setenv("BOARDMAN_API_KEY", _KEY)



def test_catalog_returns_players():
    client = TestClient(app)
    r = client.get("/api/stack/agentic/football/catalog?limit=10", headers={"X-Boardman-Key": _KEY})
    assert r.status_code == 200
    j = r.json()
    assert j.get("success") is True
    assert isinstance(j.get("players"), list)
    assert len(j.get("players")) <= 10


def test_catalog_search_filters_by_name():
    client = TestClient(app)
    r = client.get("/api/stack/agentic/football/catalog?q=Haaland&limit=10", headers={"X-Boardman-Key": _KEY})
    assert r.status_code == 200
    j = r.json()
    players = j.get("players") or []
    assert any("Haaland" in (p.get("name") or "") for p in players)
    assert any(p.get("slot") == "ST" for p in players)
