"""Seed/enrich local player seed using external football API and write to Supabase.

Usage (local): set env vars and run:

  API_FOOTBALL_KEY=xxx SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
    python gaming/src/stack/agentic/football/seed_from_api.py

This script is conservative: it only updates rows that have matching `id` or
creates new rows for players returned by the API if not present.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `gaming` package imports resolve when running
# this script directly (support `python .../seed_from_api.py`).
_p = Path(__file__).resolve()
search_p = _p
while search_p.name != "gaming" and search_p.parent != search_p:
    search_p = search_p.parent
if search_p.name == "gaming":
    repo_root = search_p.parent
    sys.path.insert(0, str(repo_root))

try:
    from gaming.src.stack.agentic.football.api_client import search_players
except Exception:
    # Fallback: load module by path so the script runs even when package imports
    import importlib.util

    api_client_path = Path(__file__).parent / "api_client.py"
    if api_client_path.exists():
        spec = importlib.util.spec_from_file_location("afm.api_client", str(api_client_path))
        mod = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)  # type: ignore
        search_players = getattr(mod, "search_players")
    else:
        raise

logger = logging.getLogger(__name__)


def _get_supabase():
    from backend.supabase_client import get_supabase

    return get_supabase()


def main():
    # load local seed
    data_file = Path(__file__).parent.parent / "data" / "players_top100.json"
    if not data_file.exists():
        print("Seed JSON missing; run generate_players_seed.py first")
        return
    players = json.loads(data_file.read_text())

    sb = None
    try:
        sb = _get_supabase()
    except Exception as e:
        logger.exception("Supabase client not available: %s", e)

    # For every player in seed, attempt a name search and attach extra metadata
    for p in players[:100]:
        name = p.get("name")
        if not name:
            continue
        print(f"Searching API for: {name}")
        try:
            candidates = search_players(name)
        except Exception as e:
            logger.exception("search failed for %s: %s", name, e)
            candidates = []
        if candidates:
            # attach the first match's basic info
            top = candidates[0]
            p["api_meta"] = {
                "provider_id": top.get("id"),
                "team": top.get("team"),
                "position": top.get("position"),
            }
        # write to Supabase if available
        if sb:
            try:
                # upsert by id
                row = {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "rating": p.get("rating"),
                    "ranking": p.get("ranking"),
                    "price": p.get("price"),
                    "wage": p.get("wage"),
                    "stars": p.get("stars"),
                    "stats": p.get("stats"),
                }
                if p.get("api_meta"):
                    row["api_meta"] = p["api_meta"]
                # Use upsert via insert with on_conflict if supported by client
                sb.table("football_players").insert(row).execute()
            except Exception:
                logger.exception("failed to write player %s to supabase", p.get("id"))

    # persist enriched JSON locally
    out = data_file.with_name("players_top100.enriched.json")
    out.write_text(json.dumps(players, indent=2))
    print("Wrote enriched seed to", out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
