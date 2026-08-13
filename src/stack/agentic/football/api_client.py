"""Small client wrapper for API-Football / RapidAPI football APIs.

This module reads keys from environment variables and exposes a minimal
`search_players(name)` helper that returns a list of candidate player dicts.

Notes:
- Set `API_FOOTBALL_KEY` to use v3.football.api-sports.io (recommended).
- Or set `RAPIDAPI_KEY` + `RAPIDAPI_HOST` for a RapidAPI proxy.
"""
from __future__ import annotations

import os
import logging
from typing import Any, List

import requests

logger = logging.getLogger(__name__)


API_FOOTBALL_BASE = "https://v3.football.api-sports.io"


def _headers_for_api_sports() -> dict[str, str]:
    key = os.getenv("API_FOOTBALL_KEY")
    if not key:
        return {}
    return {"x-apisports-key": key}


def _headers_for_rapidapi() -> dict[str, str]:
    key = os.getenv("RAPIDAPI_KEY")
    host = os.getenv("RAPIDAPI_HOST")
    if not key or not host:
        return {}
    return {"x-rapidapi-key": key, "x-rapidapi-host": host}


def search_players(name: str, season: int = 2023, page: int = 1) -> List[dict[str, Any]]:
    """Return a list of player candidate dicts for `name`.

    The returned dicts are the decoded JSON objects from the provider and may
    differ between providers. Keep the mapping minimal: `name`, `id`, `team`, `position`.
    """
    name = (name or "").strip()
    if not name:
        return []

    # Prefer direct API-Football if key present
    headers = _headers_for_api_sports()
    if headers:
        try:
            params = {"search": name, "season": season, "page": page}
            r = requests.get(f"{API_FOOTBALL_BASE}/players", headers=headers, params=params, timeout=10)
            r.raise_for_status()
            j = r.json()
            candidates = []
            for item in j.get("response", []):
                # item shape: {player: {...}, statistics: [...]}
                p = item.get("player") or {}
                team = (item.get("statistics") or [{}])[0].get("team") if item.get("statistics") else None
                candidates.append({
                    "name": p.get("name"),
                    "id": p.get("id"),
                    "firstname": p.get("firstname"),
                    "lastname": p.get("lastname"),
                    "nationality": p.get("nationality"),
                    "birth": p.get("birth"),
                    "position": (item.get("statistics") or [{}])[0].get("games", {}).get("position"),
                    "team": team and team.get("name"),
                    "raw": item,
                })
            return candidates
        except Exception as e:
            logger.exception("api-sports search failed: %s", e)

    # Fallback to RapidAPI proxy if configured
    headers = _headers_for_rapidapi()
    if headers:
        try:
            # RapidAPI host should proxy to the same endpoints; keep path generic
            url = os.getenv("RAPIDAPI_BASE") or API_FOOTBALL_BASE
            params = {"search": name, "season": season, "page": page}
            r = requests.get(f"{url}/players", headers=headers, params=params, timeout=10)
            r.raise_for_status()
            j = r.json()
            candidates = []
            for item in j.get("response", []):
                p = item.get("player") or {}
                team = (item.get("statistics") or [{}])[0].get("team") if item.get("statistics") else None
                candidates.append({
                    "name": p.get("name"),
                    "id": p.get("id"),
                    "position": (item.get("statistics") or [{}])[0].get("games", {}).get("position"),
                    "team": team and team.get("name"),
                    "raw": item,
                })
            return candidates
        except Exception as e:
            logger.exception("rapidapi search failed: %s", e)

    # No provider configured
    logger.debug("No football API keys configured (API_FOOTBALL_KEY or RAPIDAPI_KEY required)")
    return []


def configured() -> bool:
    return bool(os.getenv("API_FOOTBALL_KEY") or (os.getenv("RAPIDAPI_KEY") and os.getenv("RAPIDAPI_HOST")))


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET a relative API-Football path. Returns decoded JSON or {}."""
    headers = _headers_for_api_sports()
    base = API_FOOTBALL_BASE
    if not headers:
        headers = _headers_for_rapidapi()
        base = os.getenv("RAPIDAPI_BASE") or API_FOOTBALL_BASE
    if not headers:
        return {}
    r = requests.get(f"{base}{path}", headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def injuries(league_id: int, season: int) -> List[dict[str, Any]]:
    """Current injuries for a league/season. One request — weekly-oracle friendly."""
    try:
        j = _get("/injuries", {"league": league_id, "season": season})
    except Exception as e:
        logger.exception("injuries fetch failed league=%s season=%s: %s", league_id, season, e)
        return []
    out: List[dict[str, Any]] = []
    for item in j.get("response") or []:
        player = item.get("player") or {}
        team = item.get("team") or {}
        fixture = item.get("fixture") or {}
        out.append(
            {
                "player_id": player.get("id"),
                "name": player.get("name"),
                "type": player.get("type") or item.get("type"),
                "reason": player.get("reason") or item.get("reason"),
                "team": team.get("name"),
                "fixture_date": (fixture.get("date") or "")[:10],
                "raw": item,
            }
        )
    return out


def sidelined(player_id: int) -> List[dict[str, Any]]:
    try:
        j = _get("/sidelined", {"player": player_id})
    except Exception as e:
        logger.exception("sidelined fetch failed player=%s: %s", player_id, e)
        return []
    return list(j.get("response") or [])


__all__ = ["search_players", "configured", "injuries", "sidelined"]
