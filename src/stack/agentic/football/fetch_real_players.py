"""Fetch real players via the configured football API and produce a frontend-ready
players JSON with in-game price and wages.

Usage:
  export API_FOOTBALL_KEY=...
  python gaming/src/stack/agentic/football/fetch_real_players.py

The script reads `data/real_player_names.txt` (one name per line) and attempts
to match each name via `search_players()` from `api_client.py`. For each match
it builds a player record with `id`, `name`, `rating` (heuristic), `ranking`,
`price`, `wage`, `stars`, and `stats` (goals/assists/appearances when available).

The output overwrites `frontend/public/agentic/players_top100.json` so the
site shows real players immediately. This is a pragmatic approach — later we
should seed the DB and switch the API to read from Supabase.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import sys

# Ensure repo root on path when running directly
_p = Path(__file__).resolve()
search_p = _p
while search_p.name != "gaming" and search_p.parent != search_p:
    search_p = search_p.parent
if search_p.name == "gaming":
    repo_root = search_p.parent
    sys.path.insert(0, str(repo_root))

from gaming.src.stack.agentic.football.api_client import search_players

logger = logging.getLogger(__name__)


def heuristic_rating(goals: int, assists: int, appearances: int) -> int:
    # Simple heuristic: base 60 + weighted contributions, cap at 95
    r = 60 + goals * 2 + assists * 1 + (appearances // 2)
    return max(60, min(95, r))


def stars_from_rating(r: int) -> int:
    if r >= 90:
        return 5
    if r >= 85:
        return 4
    if r >= 75:
        return 3
    if r >= 65:
        return 2
    return 1


def build_player_from_candidate(candidate: dict, rank: int) -> dict:
    # candidate expected keys: name, id, team, position, raw
    raw = candidate.get("raw") or {}
    stats = {}
    # many providers put stats in `statistics` list
    stats_block = None
    if isinstance(raw, dict):
        stats_block = (raw.get("statistics") or [{}])[0] if raw.get("statistics") else {}
    if stats_block:
        games = stats_block.get("games") or {}
        goals = int((stats_block.get("goals") or 0) if isinstance(stats_block.get("goals"), int) else (stats_block.get("goals", {}).get("total") or 0))
        assists = int((stats_block.get("goals") or 0) if isinstance(stats_block.get("assists"), int) else (stats_block.get("goals", {}).get("total") or stats_block.get("goals", {}).get("assists") or 0))
        # Try common shapes
        if isinstance(stats_block.get("goals"), dict):
            goals = int(stats_block.get("goals", {}).get("total") or 0)
        if isinstance(stats_block.get("assists"), dict):
            assists = int(stats_block.get("assists", {}).get("total") or 0)
        appearances = int(games.get("appearances") or games.get("appearances") or 0)
        # fallback: check games.appearances or games.captain etc.
        try:
            appearances = int(games.get("appearances") or 0)
        except Exception:
            appearances = 0
    else:
        goals = assists = appearances = 0

    rating = heuristic_rating(goals, assists, appearances)
    price = int(max(500, rating * 150))
    wage = int(price * 0.06)
    player = {
        "id": str(candidate.get("id") or f"auto_{rank:03d}"),
        "name": candidate.get("name") or "",
        "rating": rating,
        "ranking": rank,
        "price": price,
        "wage": wage,
        "stars": stars_from_rating(rating),
        "stats": {"goals": goals, "assists": assists, "appearances": appearances},
    }
    return player


def main():
    names_file = Path(__file__).parent.parent / "data" / "real_player_names.txt"
    if not names_file.exists():
        print("No names file found at", names_file)
        return
    names = [l.strip() for l in names_file.read_text().splitlines() if l.strip()]
    out_players = []
    rank = 1
    for name in names:
        print("Searching:", name)
        try:
            candidates = search_players(name)
        except Exception as e:
            logger.exception("search failed for %s: %s", name, e)
            candidates = []
        if not candidates:
            print("No candidate found for", name)
            continue
        # choose the first candidate
        player = build_player_from_candidate(candidates[0], rank)
        out_players.append(player)
        rank += 1
        if rank > 100:
            break

    # write to frontend static file
    out_path = Path(__file__).resolve().parents[5] / "frontend" / "public" / "agentic" / "players_top100.json"
    out_path.write_text(json.dumps(out_players, indent=2))
    print("Wrote", out_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
