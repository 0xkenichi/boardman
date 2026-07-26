"""
EA FC / FIFA team database lookup.
Loads the curated team list from data/eafc_teams.json and provides fuzzy search.
"""
import json
import os
import re
from difflib import get_close_matches
from typing import List

_LOGGER = None

def _logger():
    global _LOGGER
    if _LOGGER is None:
        import logging
        _LOGGER = logging.getLogger(__name__)
    return _LOGGER


def _data_path() -> str:
    # Support running from project root or from gaming/src/backend
    candidates = [
        "gaming/src/backend/data/eafc_teams.json",
        "data/eafc_teams.json",
        os.path.join(os.path.dirname(__file__), "..", "data", "eafc_teams.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "eafc_teams.json"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError("eafc_teams.json not found")


# Lazy-loaded team list
_TEAMS: List[str] = []


def _load_teams() -> List[str]:
    global _TEAMS
    if not _TEAMS:
        path = _data_path()
        with open(path, "r", encoding="utf-8") as f:
            _TEAMS = json.load(f)
        _logger().info(f"[TeamDB] Loaded {len(_TEAMS)} EA FC teams from {path}")
    return _TEAMS


def search_teams(query: str, limit: int = 10) -> List[str]:
    """
    Search team names by substring and fuzzy matching.
    Returns up to `limit` results, ordered by relevance.
    """
    query = query.strip().lower()
    if not query or len(query) < 2:
        return []

    teams = _load_teams()

    # 1. Exact prefix match (case-insensitive)
    prefix_hits = [t for t in teams if t.lower().startswith(query)]

    # 2. Substring match
    substring_hits = [t for t in teams if query in t.lower() and t not in prefix_hits]

    # 3. Fuzzy match for typos / close names
    fuzzy_hits = get_close_matches(query, [t.lower() for t in teams], n=limit, cutoff=0.6)
    fuzzy_hits = [teams[[t.lower() for t in teams].index(h)] for h in fuzzy_hits if h not in [x.lower() for x in prefix_hits + substring_hits]]

    results = (prefix_hits + substring_hits + fuzzy_hits)[:limit]
    return results


def is_valid_team(name: str) -> bool:
    """Check if a team exists in the database."""
    return name.strip() in _load_teams()


def all_teams() -> List[str]:
    return _load_teams()
