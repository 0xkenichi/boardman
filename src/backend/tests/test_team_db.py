import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from gaming.src.backend.services.team_db import search_teams, is_valid_team


def test_search_teams_prefix_match():
    results = search_teams("barcelona", limit=5)
    assert "FC Barcelona" in results


def test_search_teams_substring_match():
    results = search_teams("bar", limit=20)
    assert "FC Barcelona" in results


def test_search_teams_returns_empty_for_short_query():
    assert search_teams("x", limit=5) == []


def test_search_teams_returns_empty_for_blank_query():
    assert search_teams("", limit=5) == []
    assert search_teams("   ", limit=5) == []


def test_is_valid_team_true_for_database_club():
    assert is_valid_team("Real Madrid") is True


def test_is_valid_team_false_for_unknown_club():
    assert is_valid_team("Totally Fake Club 999") is False


def test_is_valid_team_is_case_sensitive():
    # Team names are stored in title case; exact match required.
    assert is_valid_team("real madrid") is False
    assert is_valid_team("REAL MADRID") is False
