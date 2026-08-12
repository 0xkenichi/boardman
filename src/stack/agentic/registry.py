"""Agent + game registry for Boardman Stack agentic layer."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json, save_json
from gaming.src.stack.agentic.wallets import provision_agent_crypto

AGENTS_FILE = "agents.json"
GAMES_FILE = "games.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRegistry:
    def __init__(self) -> None:
        self._ensure_games()

    def _ensure_games(self) -> None:
        from gaming.src.stack.agentic.games.catalog import GAME_CATALOG

        games = load_json(GAMES_FILE, {"games": {}})
        changed = False
        for gid, meta in GAME_CATALOG.items():
            if gid not in games.get("games", {}):
                games.setdefault("games", {})[gid] = {
                    **meta,
                    "enabled": True,
                    "creator_id": "boardman",
                    "creator_fee_bps": 100,
                }
                changed = True
            else:
                # refresh display fields
                games["games"][gid] = {**games["games"][gid], **meta, "enabled": True}
                changed = True
        if changed:
            save_json(GAMES_FILE, games)

    def _agents(self) -> dict[str, Any]:
        return load_json(AGENTS_FILE, {"agents": {}})

    def list_games(self) -> list[dict[str, Any]]:
        return list(load_json(GAMES_FILE, {"games": {}})["games"].values())

    def list_agents(self) -> list[dict[str, Any]]:
        return list(self._agents()["agents"].values())

    def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        return self._agents()["agents"].get(agent_id)

    def register_agent(
        self,
        *,
        agent_id: str,
        name: str,
        owner_id: str,
        strategy_id: str,
        openings: list[str],
        mind: dict[str, Any],
        game_ids: Optional[list[str]] = None,
        seed: Optional[str] = None,
        version: str = "1.0.0",
        creator_id: Optional[str] = None,
        creator_fee_bps: int = 500,
        economy: Optional[dict[str, Any]] = None,
        preferred_time_controls: Optional[list[str]] = None,
        silo: Optional[str] = None,
        local_books: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        from gaming.src.stack.agentic.economy.fees import clamp_creator_fee_bps
        from gaming.src.stack.agentic.chess.openings import register_book

        data = self._agents()
        crypto = provision_agent_crypto(agent_id, seed=seed or agent_id)
        from gaming.src.stack.agentic.wallets import seed_to_private_key

        secret = {"private_key": seed_to_private_key(seed or agent_id)}
        save_json(f"secrets_{agent_id}.json", secret)

        eco = dict(economy or {})
        c_bps = clamp_creator_fee_bps(
            int(eco.get("creator_fee_bps", creator_fee_bps))
        )
        eco["creator_fee_bps"] = c_bps
        prefs = preferred_time_controls or eco.get("preferred_time_controls") or [
            "blitz_3|2",
            "blitz_5|0",
            "rapid_10|0",
        ]
        eco["preferred_time_controls"] = list(prefs)

        # Register siloed opening books if shipped with the agent
        for book_id, lines in (local_books or {}).items():
            if isinstance(lines, list) and lines:
                register_book(str(book_id), lines)

        rec = {
            "agent_id": agent_id,
            "name": name,
            "owner_id": owner_id,
            "creator_id": creator_id or owner_id,
            "creator_fee_bps": c_bps,
            "version": version,
            "strategy_id": strategy_id,
            "openings": openings,
            "mind": mind,
            "economy": eco,
            "preferred_time_controls": list(prefs),
            "silo": silo,
            "game_ids": game_ids or ["agentic.chess_standard"],
            "wallet_address": crypto["wallet_address"],
            "identity_contract": crypto["identity_contract"],
            "chain_id": crypto["chain_id"],
            "stats": {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "matches": 0,
                "creator_fees_usdc": "0",
            },
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["agents"][agent_id] = rec
        save_json(AGENTS_FILE, data)
        return rec

    def register_from_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Deploy path for third-party agents (YAML/JSON manifest)."""
        eco = manifest.get("economy") or {}
        return self.register_agent(
            agent_id=manifest["agent_id"],
            name=manifest["name"],
            owner_id=manifest.get("owner_id") or manifest.get("creator_id") or "unknown",
            creator_id=manifest.get("creator_id") or manifest.get("owner_id"),
            strategy_id=manifest.get("strategy_id") or "custom",
            openings=list(manifest.get("openings") or []),
            mind=dict(manifest.get("mind") or {}),
            game_ids=list(manifest.get("game_ids") or ["agentic.chess_standard"]),
            seed=manifest.get("seed") or manifest["agent_id"],
            version=str(manifest.get("version") or "1.0.0"),
            creator_fee_bps=int(eco.get("creator_fee_bps", 500)),
            economy=eco,
            preferred_time_controls=list(
                eco.get("preferred_time_controls")
                or manifest.get("preferred_time_controls")
                or []
            )
            or None,
            silo=manifest.get("silo"),
            local_books=manifest.get("local_books"),
        )

    def update_stats(self, agent_id: str, result: str) -> None:
        """result: win | loss | draw"""
        data = self._agents()
        a = data["agents"].get(agent_id)
        if not a:
            return
        a["stats"]["matches"] = int(a["stats"].get("matches", 0)) + 1
        if result == "win":
            a["stats"]["wins"] = int(a["stats"].get("wins", 0)) + 1
        elif result == "loss":
            a["stats"]["losses"] = int(a["stats"].get("losses", 0)) + 1
        else:
            a["stats"]["draws"] = int(a["stats"].get("draws", 0)) + 1
        a["updated_at"] = _now()
        data["agents"][agent_id] = a
        save_json(AGENTS_FILE, data)

    def ensure_demo_agents(self) -> list[dict[str, Any]]:
        """Register siloed Raja + Nero demo agents if missing / upgrade economy fields."""
        from gaming.src.stack.agentic.agents import load_demo_manifests
        from gaming.src.stack.agentic.chess.personas import get_persona

        out = []
        for manifest in load_demo_manifests():
            existing = self.get_agent(manifest["agent_id"])
            if existing and existing.get("version") == manifest.get("version"):
                # Refresh mind from silo for play (not persisted strategy leak)
                p = get_persona(manifest["agent_id"])
                if p:
                    existing = {**existing, **{k: p[k] for k in ("mind", "economy", "creator_fee_bps", "preferred_time_controls", "openings", "creator_id") if k in p}}
                out.append(existing)
                continue
            out.append(self.register_from_manifest(manifest))
        return out

    def credit_creator_fee(self, agent_id: str, amount: str) -> None:
        data = self._agents()
        a = data["agents"].get(agent_id)
        if not a:
            return
        from decimal import Decimal

        prev = Decimal(str((a.get("stats") or {}).get("creator_fees_usdc") or "0"))
        a.setdefault("stats", {})
        a["stats"]["creator_fees_usdc"] = str(prev + Decimal(str(amount)))
        a["updated_at"] = _now()
        data["agents"][agent_id] = a
        save_json(AGENTS_FILE, data)


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    return AgentRegistry()
