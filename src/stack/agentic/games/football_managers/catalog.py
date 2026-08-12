"""
Player catalog — v0 ships a seed shortlist; target 500 unique players.

Ownership is tracked on each player record: owner_agent_id is None when free.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.pricing import (
    game_price_from_real_value,
    wage_per_matchday,
)
from gaming.src.stack.agentic.games.football_managers.rules import GAME_ID

# Seed: recognizable top names with approximate real USD valuations (illustrative, not live TM).
_SEED: list[dict[str, Any]] = [
    {"name": "Erling Haaland", "nation": "NO", "primary_pos": "FWD", "real_value_usd": 180_000_000, "base_rating": 91},
    {"name": "Kylian Mbappé", "nation": "FR", "primary_pos": "FWD", "real_value_usd": 180_000_000, "base_rating": 91},
    {"name": "Jude Bellingham", "nation": "ENG", "primary_pos": "MID", "real_value_usd": 180_000_000, "base_rating": 89},
    {"name": "Vinícius Júnior", "nation": "BR", "primary_pos": "FWD", "real_value_usd": 150_000_000, "base_rating": 90},
    {"name": "Bukayo Saka", "nation": "ENG", "primary_pos": "FWD", "real_value_usd": 120_000_000, "base_rating": 87},
    {"name": "Phil Foden", "nation": "ENG", "primary_pos": "MID", "real_value_usd": 130_000_000, "base_rating": 88},
    {"name": "Pedri", "nation": "ES", "primary_pos": "MID", "real_value_usd": 100_000_000, "base_rating": 87},
    {"name": "Florian Wirtz", "nation": "DE", "primary_pos": "MID", "real_value_usd": 130_000_000, "base_rating": 88},
    {"name": "Jamal Musiala", "nation": "DE", "primary_pos": "MID", "real_value_usd": 130_000_000, "base_rating": 88},
    {"name": "Rodri", "nation": "ES", "primary_pos": "MID", "real_value_usd": 110_000_000, "base_rating": 90},
    {"name": "Declan Rice", "nation": "ENG", "primary_pos": "MID", "real_value_usd": 100_000_000, "base_rating": 87},
    {"name": "William Saliba", "nation": "FR", "primary_pos": "DEF", "real_value_usd": 80_000_000, "base_rating": 86},
    {"name": "Rúben Dias", "nation": "PT", "primary_pos": "DEF", "real_value_usd": 80_000_000, "base_rating": 88},
    {"name": "Virgil van Dijk", "nation": "NL", "primary_pos": "DEF", "real_value_usd": 40_000_000, "base_rating": 88},
    {"name": "Trent Alexander-Arnold", "nation": "ENG", "primary_pos": "DEF", "real_value_usd": 70_000_000, "base_rating": 86},
    {"name": "Achraf Hakimi", "nation": "MA", "primary_pos": "DEF", "real_value_usd": 60_000_000, "base_rating": 85},
    {"name": "Alisson", "nation": "BR", "primary_pos": "GK", "real_value_usd": 45_000_000, "base_rating": 89},
    {"name": "Thibaut Courtois", "nation": "BE", "primary_pos": "GK", "real_value_usd": 35_000_000, "base_rating": 89},
    {"name": "Ederson", "nation": "BR", "primary_pos": "GK", "real_value_usd": 40_000_000, "base_rating": 88},
    {"name": "Harry Kane", "nation": "ENG", "primary_pos": "FWD", "real_value_usd": 90_000_000, "base_rating": 90},
    {"name": "Lautaro Martínez", "nation": "AR", "primary_pos": "FWD", "real_value_usd": 100_000_000, "base_rating": 88},
    {"name": "Victor Osimhen", "nation": "NG", "primary_pos": "FWD", "real_value_usd": 100_000_000, "base_rating": 88},
    {"name": "Mohamed Salah", "nation": "EG", "primary_pos": "FWD", "real_value_usd": 55_000_000, "base_rating": 89},
    {"name": "Kevin De Bruyne", "nation": "BE", "primary_pos": "MID", "real_value_usd": 40_000_000, "base_rating": 89},
    {"name": "Martin Ødegaard", "nation": "NO", "primary_pos": "MID", "real_value_usd": 90_000_000, "base_rating": 87},
    {"name": "Bruno Fernandes", "nation": "PT", "primary_pos": "MID", "real_value_usd": 70_000_000, "base_rating": 87},
    {"name": "Luka Modrić", "nation": "HR", "primary_pos": "MID", "real_value_usd": 10_000_000, "base_rating": 86},
    {"name": "Antonio Rüdiger", "nation": "DE", "primary_pos": "DEF", "real_value_usd": 30_000_000, "base_rating": 86},
    {"name": "Marquinhos", "nation": "BR", "primary_pos": "DEF", "real_value_usd": 50_000_000, "base_rating": 87},
    {"name": "Gianluigi Donnarumma", "nation": "IT", "primary_pos": "GK", "real_value_usd": 50_000_000, "base_rating": 88},
    {"name": "Khvicha Kvaratskhelia", "nation": "GE", "primary_pos": "FWD", "real_value_usd": 80_000_000, "base_rating": 86},
    {"name": "Rodrygo", "nation": "BR", "primary_pos": "FWD", "real_value_usd": 100_000_000, "base_rating": 86},
    {"name": "Rafael Leão", "nation": "PT", "primary_pos": "FWD", "real_value_usd": 90_000_000, "base_rating": 86},
    {"name": "Federico Valverde", "nation": "UY", "primary_pos": "MID", "real_value_usd": 100_000_000, "base_rating": 87},
    {"name": "Eduardo Camavinga", "nation": "FR", "primary_pos": "MID", "real_value_usd": 80_000_000, "base_rating": 85},
    {"name": "Aurélien Tchouaméni", "nation": "FR", "primary_pos": "MID", "real_value_usd": 80_000_000, "base_rating": 85},
    {"name": "Joško Gvardiol", "nation": "HR", "primary_pos": "DEF", "real_value_usd": 75_000_000, "base_rating": 85},
    {"name": "Gabriel Magalhães", "nation": "BR", "primary_pos": "DEF", "real_value_usd": 70_000_000, "base_rating": 85},
    {"name": "Alexis Mac Allister", "nation": "AR", "primary_pos": "MID", "real_value_usd": 75_000_000, "base_rating": 85},
    {"name": "Enzo Fernández", "nation": "AR", "primary_pos": "MID", "real_value_usd": 80_000_000, "base_rating": 84},
]

_DATA_DIR = Path(__file__).resolve().parent / "data"
_CATALOG_PATH = _DATA_DIR / "catalog_v0.json"

# In-memory mutable catalog for a process (v0 — later persist via store)
_catalog: dict[str, dict[str, Any]] = {}


def _normalize_row(i: int, raw: dict[str, Any]) -> dict[str, Any]:
    real = int(raw["real_value_usd"])
    price = game_price_from_real_value(real)
    wage = wage_per_matchday(price)
    pid = raw.get("player_id") or f"afm_pl_{i + 1:03d}"
    return {
        "player_id": pid,
        "name": raw["name"],
        "nation": raw.get("nation") or "XX",
        "primary_pos": raw["primary_pos"],
        "secondary_pos": list(raw.get("secondary_pos") or []),
        "real_value_usd": real,
        "game_price_usdc": str(price),
        "wage_per_matchday_usdc": str(wage),
        "base_rating": int(raw.get("base_rating") or 75),
        "form": float(raw.get("form") or 6.5),
        "injury": raw.get("injury"),
        "suspension_matches": int(raw.get("suspension_matches") or 0),
        "owner_agent_id": raw.get("owner_agent_id"),
    }


def seed_catalog(*, force: bool = False) -> list[dict[str, Any]]:
    """Load or build v0 catalog (seed shortlist)."""
    global _catalog
    if _catalog and not force:
        return list(_catalog.values())

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _CATALOG_PATH.exists() and not force:
        rows = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    else:
        rows = [_normalize_row(i, r) for i, r in enumerate(_SEED)]
        _CATALOG_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    _catalog = {r["player_id"]: r for r in rows}
    return list(_catalog.values())


def list_players(
    *,
    free_only: bool = False,
    pos: Optional[str] = None,
) -> list[dict[str, Any]]:
    seed_catalog()
    out = []
    for p in _catalog.values():
        if free_only and p.get("owner_agent_id"):
            continue
        if pos and p.get("primary_pos") != pos.upper():
            continue
        out.append(copy.deepcopy(p))
    out.sort(key=lambda x: (-int(x["real_value_usd"]), x["name"]))
    return out


def get_player(player_id: str) -> Optional[dict[str, Any]]:
    seed_catalog()
    p = _catalog.get(player_id)
    return copy.deepcopy(p) if p else None


def set_owner(player_id: str, agent_id: Optional[str]) -> dict[str, Any]:
    seed_catalog()
    if player_id not in _catalog:
        raise KeyError(player_id)
    _catalog[player_id]["owner_agent_id"] = agent_id
    return copy.deepcopy(_catalog[player_id])


def catalog_meta() -> dict[str, Any]:
    seed_catalog()
    free = sum(1 for p in _catalog.values() if not p.get("owner_agent_id"))
    return {
        "game_id": GAME_ID,
        "count": len(_catalog),
        "target": 500,
        "free_agents": free,
        "unique_ownership": True,
        "status": "v0_seed",
    }
