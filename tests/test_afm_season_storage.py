"""The season file stays small enough to serve.

Live, afm_season.json reached 19.5MB for a two-club season; a ten-club
season measured ~110MB, re-parsed by every cold GET /football/season and
rewritten by every matchday tick. The board's phase stream was ~90% of
each stored result and is a pure function of the feed + lineups, so it is
rebuilt on replay instead of stored, and the file is written compact.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

DERBY = ["agent_bluelock_demo", "agent_aoashi_demo"]


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs

    reg = get_registry()
    reg.ensure_demo_agents()
    seed_demo_clubs()
    return reg


def test_replay_rebuilds_the_exact_phase_stream_the_engine_built(_world, monkeypatch, tmp_path):
    from gaming.src.stack.agentic.games.football_managers import match_engine as M
    from gaming.src.stack.agentic.games.football_managers import season as S

    played: dict[str, list] = {}
    real = M.simulate_match

    def recording(match_id, **kw):
        res = real(match_id, **kw)
        played[match_id] = list(res.to_dict()["phases"])
        return res

    monkeypatch.setattr(M, "simulate_match", recording)  # season imports it at call time
    S.open_season(agent_ids=DERBY, start_at=datetime.now(timezone.utc) - timedelta(hours=31))
    S.tick()  # matchdays 1 and 2 resolve
    assert len(played) == 2

    view = S._state_view()["season"]
    for md in ("1", "2"):
        for stored in view["matchdays"][md]["results"]:
            assert "phases" not in stored  # not carried in the season file
            rep = S.get_replay(int(md), stored["home_agent_id"], stored["away_agent_id"])
            assert rep["result"]["phases"] == played[stored["match_id"]]
            assert rep["result"]["feed"] == stored["feed"]

    raw = (tmp_path / "afm_season.json").read_text()
    assert not raw.startswith("{\n")  # compact, not indent=2
