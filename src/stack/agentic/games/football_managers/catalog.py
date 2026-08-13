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

# Pitch slots for the public catalog (top-N per slot).
SLOTS = ("GK", "RB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW")
SLOT_GROUP = {
    "GK": "GK",
    "RB": "DEF",
    "CB": "DEF",
    "LB": "DEF",
    "CDM": "MID",
    "CM": "MID",
    "CAM": "MID",
    "RW": "FWD",
    "ST": "FWD",
    "LW": "FWD",
}

# Seed: recognizable names + approximate real USD valuations (illustrative).
_SEED: list[dict[str, Any]] = [
    {"name": "Erling Haaland", "nation": "NO", "slot": "ST", "real_value_usd": 180_000_000, "base_rating": 91},
    {"name": "Harry Kane", "nation": "ENG", "slot": "ST", "real_value_usd": 90_000_000, "base_rating": 90},
    {"name": "Lautaro Martínez", "nation": "AR", "slot": "ST", "real_value_usd": 100_000_000, "base_rating": 88},
    {"name": "Victor Osimhen", "nation": "NG", "slot": "ST", "real_value_usd": 100_000_000, "base_rating": 88},
    {"name": "Kylian Mbappé", "nation": "FR", "slot": "ST", "real_value_usd": 180_000_000, "base_rating": 91},
    {"name": "Vinícius Júnior", "nation": "BR", "slot": "LW", "real_value_usd": 150_000_000, "base_rating": 90},
    {"name": "Khvicha Kvaratskhelia", "nation": "GE", "slot": "LW", "real_value_usd": 80_000_000, "base_rating": 86},
    {"name": "Rafael Leão", "nation": "PT", "slot": "LW", "real_value_usd": 90_000_000, "base_rating": 86},
    {"name": "Bukayo Saka", "nation": "ENG", "slot": "RW", "real_value_usd": 120_000_000, "base_rating": 87},
    {"name": "Mohamed Salah", "nation": "EG", "slot": "RW", "real_value_usd": 55_000_000, "base_rating": 89},
    {"name": "Rodrygo", "nation": "BR", "slot": "RW", "real_value_usd": 100_000_000, "base_rating": 86},
    {"name": "Lamine Yamal", "nation": "ES", "slot": "RW", "real_value_usd": 160_000_000, "base_rating": 86},
    {"name": "Phil Foden", "nation": "ENG", "slot": "CAM", "real_value_usd": 130_000_000, "base_rating": 88},
    {"name": "Florian Wirtz", "nation": "DE", "slot": "CAM", "real_value_usd": 130_000_000, "base_rating": 88},
    {"name": "Jamal Musiala", "nation": "DE", "slot": "CAM", "real_value_usd": 130_000_000, "base_rating": 88},
    {"name": "Kevin De Bruyne", "nation": "BE", "slot": "CAM", "real_value_usd": 40_000_000, "base_rating": 89},
    {"name": "Martin Ødegaard", "nation": "NO", "slot": "CAM", "real_value_usd": 90_000_000, "base_rating": 87},
    {"name": "Bruno Fernandes", "nation": "PT", "slot": "CAM", "real_value_usd": 70_000_000, "base_rating": 87},
    {"name": "Jude Bellingham", "nation": "ENG", "slot": "CM", "real_value_usd": 180_000_000, "base_rating": 89},
    {"name": "Pedri", "nation": "ES", "slot": "CM", "real_value_usd": 100_000_000, "base_rating": 87},
    {"name": "Federico Valverde", "nation": "UY", "slot": "CM", "real_value_usd": 100_000_000, "base_rating": 87},
    {"name": "Eduardo Camavinga", "nation": "FR", "slot": "CM", "real_value_usd": 80_000_000, "base_rating": 85},
    {"name": "Alexis Mac Allister", "nation": "AR", "slot": "CM", "real_value_usd": 75_000_000, "base_rating": 85},
    {"name": "Enzo Fernández", "nation": "AR", "slot": "CM", "real_value_usd": 80_000_000, "base_rating": 84},
    {"name": "Luka Modrić", "nation": "HR", "slot": "CM", "real_value_usd": 10_000_000, "base_rating": 86},
    {"name": "Rodri", "nation": "ES", "slot": "CDM", "real_value_usd": 110_000_000, "base_rating": 90},
    {"name": "Declan Rice", "nation": "ENG", "slot": "CDM", "real_value_usd": 100_000_000, "base_rating": 87},
    {"name": "Aurélien Tchouaméni", "nation": "FR", "slot": "CDM", "real_value_usd": 80_000_000, "base_rating": 85},
    {"name": "William Saliba", "nation": "FR", "slot": "CB", "real_value_usd": 80_000_000, "base_rating": 86},
    {"name": "Rúben Dias", "nation": "PT", "slot": "CB", "real_value_usd": 80_000_000, "base_rating": 88},
    {"name": "Virgil van Dijk", "nation": "NL", "slot": "CB", "real_value_usd": 40_000_000, "base_rating": 88},
    {"name": "Antonio Rüdiger", "nation": "DE", "slot": "CB", "real_value_usd": 30_000_000, "base_rating": 86},
    {"name": "Marquinhos", "nation": "BR", "slot": "CB", "real_value_usd": 50_000_000, "base_rating": 87},
    {"name": "Gabriel Magalhães", "nation": "BR", "slot": "CB", "real_value_usd": 70_000_000, "base_rating": 85},
    {"name": "Trent Alexander-Arnold", "nation": "ENG", "slot": "RB", "real_value_usd": 70_000_000, "base_rating": 86},
    {"name": "Achraf Hakimi", "nation": "MA", "slot": "RB", "real_value_usd": 60_000_000, "base_rating": 85},
    {"name": "Reece James", "nation": "ENG", "slot": "RB", "real_value_usd": 50_000_000, "base_rating": 84},
    {"name": "Jules Koundé", "nation": "FR", "slot": "RB", "real_value_usd": 55_000_000, "base_rating": 85},
    {"name": "Joško Gvardiol", "nation": "HR", "slot": "LB", "real_value_usd": 75_000_000, "base_rating": 85},
    {"name": "Alphonso Davies", "nation": "CA", "slot": "LB", "real_value_usd": 60_000_000, "base_rating": 84},
    {"name": "Andrew Robertson", "nation": "SCO", "slot": "LB", "real_value_usd": 35_000_000, "base_rating": 85},
    {"name": "Nuno Mendes", "nation": "PT", "slot": "LB", "real_value_usd": 70_000_000, "base_rating": 84},
    {"name": "Alisson", "nation": "BR", "slot": "GK", "real_value_usd": 45_000_000, "base_rating": 89},
    {"name": "Thibaut Courtois", "nation": "BE", "slot": "GK", "real_value_usd": 35_000_000, "base_rating": 89},
    {"name": "Ederson", "nation": "BR", "slot": "GK", "real_value_usd": 40_000_000, "base_rating": 88},
    {"name": "Gianluigi Donnarumma", "nation": "IT", "slot": "GK", "real_value_usd": 50_000_000, "base_rating": 88},
]

_DATA_DIR = Path(__file__).resolve().parent / "data"
_CATALOG_PATH = _DATA_DIR / "catalog_v0.json"

# In-memory mutable catalog for a process (v0 — later persist via store)
_catalog: dict[str, dict[str, Any]] = {}


def stars_from_rating(rating: int) -> int:
    if rating >= 90:
        return 5
    if rating >= 86:
        return 4
    if rating >= 82:
        return 3
    if rating >= 76:
        return 2
    return 1


def _normalize_row(i: int, raw: dict[str, Any]) -> dict[str, Any]:
    real = int(raw["real_value_usd"])
    price = game_price_from_real_value(real)
    wage = wage_per_matchday(price)
    pid = raw.get("player_id") or f"afm_pl_{i + 1:03d}"
    slot = str(raw.get("slot") or raw.get("primary_pos") or "CM").upper()
    if slot in {"FWD", "ST"}:
        slot = "ST" if slot == "ST" or "Haaland" in raw.get("name", "") else slot
    if slot == "FWD":
        slot = "ST"
    if slot == "DEF":
        slot = "CB"
    if slot == "MID":
        slot = "CM"
    group = SLOT_GROUP.get(slot, str(raw.get("primary_pos") or "MID"))
    rating = int(raw.get("base_rating") or 75)
    weekly = dict(raw.get("weekly") or {})
    return {
        "player_id": pid,
        "name": raw["name"],
        "nation": raw.get("nation") or "XX",
        "slot": slot,
        "primary_pos": group,
        "secondary_pos": list(raw.get("secondary_pos") or []),
        "real_value_usd": real,
        "game_price_usdc": str(raw.get("game_price_usdc") or price),
        "wage_per_matchday_usdc": str(raw.get("wage_per_matchday_usdc") or wage),
        "base_rating": rating,
        "stars": int(raw.get("stars") or stars_from_rating(rating)),
        "form": float(raw.get("form") or 6.5),
        "injury": raw.get("injury"),
        "suspension_matches": int(raw.get("suspension_matches") or 0),
        "weekly_goals": int(weekly.get("goals") or raw.get("weekly_goals") or 0),
        "weekly_assists": int(weekly.get("assists") or raw.get("weekly_assists") or 0),
        "weekly_rating": weekly.get("rating") or raw.get("weekly_rating"),
        "weekly_apps": int(weekly.get("appearances") or raw.get("weekly_apps") or 0),
        "oracle_updated_at": raw.get("oracle_updated_at"),
        "oracle_source": raw.get("oracle_source"),
        "owner_agent_id": raw.get("owner_agent_id"),
    }


def seed_catalog(*, force: bool = False) -> list[dict[str, Any]]:
    """Load or build v0 catalog (seed shortlist)."""
    global _catalog
    if _catalog and not force:
        return list(_catalog.values())

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _CATALOG_PATH.exists() and not force:
        raw_rows = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        rows = [_normalize_row(i, r) for i, r in enumerate(raw_rows)]
    else:
        rows = [_normalize_row(i, r) for i, r in enumerate(_SEED)]
        _CATALOG_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    _catalog = {r["player_id"]: r for r in rows}
    return list(_catalog.values())


def list_players(
    *,
    free_only: bool = False,
    pos: Optional[str] = None,
    slot: Optional[str] = None,
) -> list[dict[str, Any]]:
    seed_catalog()
    want_pos = (pos or "").upper()
    want_slot = (slot or "").upper()
    out = []
    for p in _catalog.values():
        if free_only and p.get("owner_agent_id"):
            continue
        if want_slot and p.get("slot") != want_slot:
            continue
        if want_pos and p.get("primary_pos") != want_pos:
            continue
        out.append(copy.deepcopy(p))
    out.sort(key=lambda x: (-int(x.get("base_rating") or 0), -int(x["real_value_usd"]), x["name"]))
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
        "slots": list(SLOTS),
    }


def export_public_json(path: Optional[Path] = None) -> Path:
    """Write a static snapshot the Vercel / laptop hub catalog page can fetch."""
    rows = seed_catalog()
    dest = path or (
        Path(__file__).resolve().parents[5] / "frontend" / "public" / "agentic" / "afm-catalog.json"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({"game_id": GAME_ID, "slots": list(SLOTS), "players": rows}, indent=2),
        encoding="utf-8",
    )
    return dest


def rebuild_from_seed() -> list[dict[str, Any]]:
    """Replace catalog_v0.json with the current seed (keeps oracle fields if names match)."""
    global _catalog
    old = {}
    if _CATALOG_PATH.exists():
        try:
            for row in json.loads(_CATALOG_PATH.read_text(encoding="utf-8")):
                old[(row.get("name") or "").lower()] = row
        except Exception:
            old = {}
    rows = []
    for i, raw in enumerate(_SEED):
        prev = old.get((raw.get("name") or "").lower()) or {}
        merged = dict(raw)
        for k in (
            "injury",
            "form",
            "suspension_matches",
            "weekly_goals",
            "weekly_assists",
            "weekly_rating",
            "weekly_apps",
            "oracle_updated_at",
            "oracle_source",
            "owner_agent_id",
        ):
            if prev.get(k) not in (None, "", 0) and k not in merged:
                merged[k] = prev[k]
        rows.append(_normalize_row(i, merged))
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CATALOG_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    _catalog = {r["player_id"]: r for r in rows}
    export_public_json()
    return list(_catalog.values())
