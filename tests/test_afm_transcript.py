"""AFM manager action transcript + press-conference acceptance.

Covers:
* the matchday decision shape stored by the House (formation / starters / bench /
  tags / source / instructions / asked / note)
* the press-conference transcript (pre + post questions, answers or no-reply)
* the spectator read endpoints (transcript_for_fixture, matchday_news_items,
  press_conference_for)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Keep test agents/seasons out of the live data store."""
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


from gaming.src.stack.agentic.games.football_managers.catalog import get_player
from gaming.src.stack.agentic.games.football_managers.season import (
    get_matchday_transcript,
    get_season,
    matchday_news_items,
    open_season,
    press_conference_for,
    reset_season,
    tick,
    transcript_for_fixture,
)
from gaming.src.stack.agentic.games.football_managers.club_store import (
    ensure_club_for_agent,
    list_clubs,
)


def _seed_club(agent_id: str, name: str, *, budget: int = 2000) -> None:
    ensure_club_for_agent(agent_id, club_name=name, budget=Decimal(str(budget)))


def _register(agent_id: str) -> dict:
    from gaming.src.stack.agentic.registry import get_registry

    return get_registry().register_agent(
        agent_id=agent_id,
        name=agent_id.replace("_", " ").title(),
        owner_id=f"owner_{agent_id}",
        creator_id=f"creator_{agent_id}",
        strategy_id="tactician_playbook",
        openings=[],
        mind={"archetype": "tactician", "directive": "Run the club."},
        game_ids=["agentic.football_managers"],
        seed=f"boardman.agent.afm.{agent_id}",
        version="1.0.0",
    )


def _run_one_season(agent_ids: list[str]) -> dict:
    reset_season()
    for aid in agent_ids:
        _register(aid)
        _seed_club(aid, f"club_{aid}")
    # start in the past so the first tick opens MD1 and (past its lock) resolves it
    s = open_season(agent_ids, start_at=datetime.now(timezone.utc) - timedelta(hours=7))
    for _ in range(8):
        tick()
    return s


def _player_map():
    return {pid: get_player(pid) for pid in get_player.__wrapped__.__code__.co_names}  # noqa: SLF001


def test_matchday_transcript_exposes_decisions():
    agents = ["home_transcript", "away_transcript"]
    _run_one_season(agents)
    s = get_matchday_transcript(1, agents[0], agents[1])
    assert s["matchday"] == 1
    assert s["home_agent_id"] == agents[0]
    assert s["away_agent_id"] == agents[1]
    assert s["home_club"] and s["away_club"]
    assert isinstance(s["decisions"], dict)
    # each club should have stored its decision (auto fallback is fine for now)
    for aid in agents:
        assert aid in s["decisions"]
        d = s["decisions"][aid]
        assert "formation" in d
        assert "starters" in d
        assert "bench" in d
        assert "tags" in d
        assert "source" in d
        assert "instructions" in d
        assert "asked" in d


def test_transcript_for_fixture_combines_action_and_quotes():
    agents = ["home_tfff", "away_tfff"]
    _run_one_season(agents)
    t = transcript_for_fixture(1, agents[0], agents[1])
    assert t["matchday"] == 1
    assert t["decisions"]
    assert isinstance(t["transcript"], list)


def test_press_conference_has_pre_and_post_questions():
    agents = ["home_pc", "away_pc"]
    _run_one_season(agents)
    pc = press_conference_for(1, agents[0])
    assert pc
    phases = {p["phase"] for p in pc}
    assert "pre" in phases
    assert "post" in phases


def test_matchday_news_items_renderable():
    agents = ["home_news", "away_news"]
    _run_one_season(agents)
    items = matchday_news_items(1)
    assert isinstance(items, list)
    if items:
        it = items[0]
        assert "agent_id" in it
        assert "club_name" in it
        assert "phase" in it
        assert "question" in it
        assert "answer" in it
        assert "source" in it


def test_press_conference_answers_normalize_no_reply():
    agents = ["home_no_reply", "away_no_reply"]
    _run_one_season(agents)
    items = matchday_news_items(1)
    assert items
    for it in items:
        assert it["answer"] is None or isinstance(it["answer"], str)


def test_transcript_via_get_season_snapshot():
    agents = ["home_snap", "away_snap"]
    _run_one_season(agents)
    snap = get_season()
    assert snap and snap.get("season_no")
    # the snapshot embeds the press-conference news for the current window
    news = snap.get("news") or []
    assert isinstance(news, list)
    for it in news:
        assert "agent_id" in it and "phase" in it and "question" in it


def test_press_conference_pre_matches_standard_questions():
    agents = ["home_std_q", "away_std_q"]
    _run_one_season(agents)
    pc = press_conference_for(1, agents[0])
    pre = next(p for p in pc if p["phase"] == "pre")
    assert set(pre["questions"]) == {
        "What is your game plan for this matchday?",
        "Who is your key player this matchday and why?",
        "How are you preparing for the opposition's style?",
    }


def test_press_conference_post_matches_standard_questions():
    agents = ["home_std_q2", "away_std_q2"]
    _run_one_season(agents)
    pc = press_conference_for(1, agents[0])
    post = next(p for p in pc if p["phase"] == "post")
    assert set(post["questions"]) == {
        "How do you rate your team's performance today?",
        "What will you change after this result?",
        "Any comments on the refereeing?",    }
