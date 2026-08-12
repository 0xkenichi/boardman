"""HTTP API for Boardman agentic arena — /api/stack/agentic/*

Auth (required for all routes except GET /health when keys are configured):
  X-Rematch-Key / X-Boardman-Key / X-Stack-Key / Authorization: Bearer
  See scripts/issue_stack_api_key.py and docs/developers/09-api-keys.md
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gaming.src.backend.rematch_auth import (
    ApiKeyPrincipal,
    extract_api_key,
    load_api_key_map,
    resolve_api_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stack/agentic", tags=["boardman-agentic"])


def require_stack_api_key(
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_boardman_key: Optional[str] = Header(default=None, alias="X-Boardman-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
) -> ApiKeyPrincipal:
    """
    Gate Stack agentic API.

    - If no keys configured at all → 503 (refuse open production).
    - If keys configured → must match one of them.
    Set BOARDMAN_STACK_ALLOW_OPEN=1 only for local demos without keys.
    """
    import os

    mapping = load_api_key_map()
    allow_open = os.getenv("BOARDMAN_STACK_ALLOW_OPEN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not mapping:
        if allow_open:
            return ApiKeyPrincipal(key_id="open", builder_id="open_demo", is_master=False)
        raise HTTPException(
            status_code=503,
            detail=(
                "Boardman Stack API keys not configured. "
                "Set REMATCH_API_KEY and/or BOARDMAN_STACK_API_KEYS "
                "(see docs/developers/09-api-keys.md). "
                "Local demo only: BOARDMAN_STACK_ALLOW_OPEN=1"
            ),
        )
    got = extract_api_key(
        x_rematch_key=x_rematch_key,
        x_boardman_key=x_boardman_key,
        x_stack_key=x_stack_key,
        authorization=authorization,
    )
    principal = resolve_api_key(got)
    if not principal:
        raise HTTPException(
            status_code=401,
            detail="invalid or missing Stack API key (X-Rematch-Key / Bearer)",
        )
    return principal


class CreateMatchBody(BaseModel):
    agent_a_id: str
    agent_b_id: str
    stake_usdc: float = Field(5.0, gt=0, le=1000)
    white_agent_id: Optional[str] = None
    chain_id: str = "arc"
    game_id: str = "agentic.chess_standard"


class RunBody(BaseModel):
    move_delay_sec: float = Field(0.15, ge=0, le=5)
    seed: Optional[int] = None


class DemoBody(BaseModel):
    stake_usdc: float = Field(5.0, gt=0, le=1000)
    white: str = Field("raja", description="raja | nero")
    move_delay_sec: float = Field(0.15, ge=0, le=5)
    seed: Optional[int] = None
    stream: bool = False


@router.get("/health")
async def agentic_health():
    """Liveness (no key) — does not list agents or accept writes."""
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import data_dir

    reg = get_registry()
    return {
        "status": "ok",
        "layer": "boardman-agentic",
        "data_dir": str(data_dir()),
        "agents": len(reg.list_agents()),
        "games": len(reg.list_games()),
        "auth": "X-Rematch-Key required for data routes",
    }


@router.get("/games")
async def list_games(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.games.catalog import list_games as catalog_games

    # ensure seeded
    get_registry().list_games()
    return {
        "success": True,
        "games": catalog_games(),
        "registry": get_registry().list_games(),
    }


@router.get("/agents")
async def list_agents(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.registry import get_registry

    agents = get_registry().list_agents()
    # strip nothing sensitive — private keys never in registry
    return {"success": True, "agents": agents}


@router.post("/agents/demo/seed")
async def seed_demo_agents(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.chess.personas import get_persona

    agents = get_registry().ensure_demo_agents()
    # attach mind blurb for clients
    for a in agents:
        p = get_persona(a["agent_id"])
        if p:
            a["mind"] = p["mind"]
            a["openings"] = p["openings"]
    return {"success": True, "agents": agents}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    _: ApiKeyPrincipal = Depends(require_stack_api_key),
):
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.chess.personas import get_persona
    from gaming.src.stack.agentic import ledger

    a = get_registry().get_agent(agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    p = get_persona(agent_id)
    if p:
        a = {**a, "mind": p["mind"], "openings": p["openings"]}
    a["usdc_balance"] = str(ledger.balance(a["wallet_address"]))
    return {"success": True, "agent": a}


@router.get("/matches")
async def list_matches(limit: int = 30, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.matches import get_match_service

    return {"success": True, "matches": get_match_service().list_matches(limit)}


@router.get("/matches/{match_id}")
async def get_match(match_id: str, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.matches import get_match_service

    m = get_match_service().get(match_id)
    if not m:
        raise HTTPException(404, "match not found")
    return {"success": True, "match": m}


@router.post("/matches")
async def create_match(body: CreateMatchBody, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.matches import get_match_service

    try:
        m = get_match_service().create_match(
            agent_a_id=body.agent_a_id,
            agent_b_id=body.agent_b_id,
            stake_usdc=body.stake_usdc,
            white_agent_id=body.white_agent_id,
            chain_id=body.chain_id,
            game_id=body.game_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, "match": m}


@router.post("/matches/{match_id}/lock")
async def lock_match(match_id: str, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.matches import get_match_service

    try:
        m = get_match_service().lock_both(match_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, "match": m}


@router.post("/matches/{match_id}/play")
async def play_match(match_id: str, body: RunBody = RunBody(), _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.matches import get_match_service

    try:
        m = get_match_service().run_match(
            match_id,
            move_delay_sec=body.move_delay_sec,
            seed=body.seed,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("play failed")
        raise HTTPException(500, str(e)) from e
    return {"success": True, "match": m}


class DemoGameBody(BaseModel):
    game_id: str = "agentic.connect4"
    stake_usdc: float = Field(5.0, gt=0, le=1000)
    p1: str = "raja"
    move_delay_sec: float = Field(0.05, ge=0, le=5)
    seed: Optional[int] = None


@router.post("/demo/game")
async def demo_any_game(body: DemoGameBody = DemoGameBody(), _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Raja vs Nero on any catalog game — lock, play, fees, spectator pot."""
    from gaming.src.stack.agentic.matches import get_match_service

    try:
        m = get_match_service().demo_game(
            game_id=body.game_id,
            stake_usdc=body.stake_usdc,
            p1=body.p1,
            move_delay_sec=body.move_delay_sec,
            seed=body.seed,
        )
    except Exception as e:
        logger.exception("demo game failed")
        raise HTTPException(500, str(e)) from e
    return {"success": True, "match": _public_match(m)}


class RegisterAgentBody(BaseModel):
    agent_id: str
    name: str
    creator_id: str
    owner_id: Optional[str] = None
    game_ids: list[str] = Field(default_factory=lambda: ["agentic.connect4"])
    creator_fee_bps: int = 500
    spectator_seed_bps: int = 500
    webhook_url: Optional[str] = None
    openings: list[str] = Field(default_factory=list)
    mind: dict = Field(default_factory=dict)
    preferred_time_controls: list[str] = Field(
        default_factory=lambda: ["blitz_3|2", "blitz_5|0"]
    )


@router.post("/agents/register")
async def register_agent(body: RegisterAgentBody, principal: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Deploy a third-party agent (wallet + identity + fees + optional webhook)."""
    from gaming.src.stack.agentic.registry import get_registry

    manifest = {
        "agent_id": body.agent_id,
        "name": body.name,
        "creator_id": body.creator_id,
        "owner_id": body.owner_id or body.creator_id,
        "game_ids": body.game_ids,
        "strategy_id": "custom",
        "openings": body.openings,
        "mind": body.mind or {
            "directive": "WIN",
            "think_ms_min": 400,
            "think_ms_max": 1500,
            "blurb": "Custom deployed agent",
        },
        "economy": {
            "creator_fee_bps": body.creator_fee_bps,
            "spectator_seed_bps": body.spectator_seed_bps,
            "preferred_time_controls": body.preferred_time_controls,
            "bankroll_usdc": "100",
            "max_stake_usdc": "25",
            "min_stake_usdc": "1",
            "reserve_bps": 2000,
            "auto_challenge": True,
        },
        "runtime": {
            "engine": "webhook" if body.webhook_url else "simple_ai",
            "webhook_url": body.webhook_url,
            "goal": "win",
        },
        "seed": f"boardman.agent.{body.agent_id}",
        "version": "1.0.0",
    }
    try:
        rec = get_registry().register_from_manifest(manifest)
        # persist runtime on record
        from gaming.src.stack.agentic.store import load_json, save_json

        data = load_json("agents.json", {"agents": {}})
        if rec["agent_id"] in data["agents"]:
            data["agents"][rec["agent_id"]]["runtime"] = manifest["runtime"]
            data["agents"][rec["agent_id"]]["game_ids"] = body.game_ids
            save_json("agents.json", data)
            rec = data["agents"][rec["agent_id"]]
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {
        "success": True,
        "agent": rec,
        "issued_by": principal.builder_id,
    }


@router.post("/demo/chess")
async def demo_chess(body: DemoBody = DemoBody(), _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """
    Seed Raja vs Nero, dual-lock USDC, play live chess, settle.
    """
    from gaming.src.stack.agentic.matches import get_match_service

    if body.stream:
        return _demo_stream(body)

    try:
        m = get_match_service().demo_raja_vs_nero(
            stake_usdc=body.stake_usdc,
            white=body.white,
            move_delay_sec=body.move_delay_sec,
            seed=body.seed,
        )
    except Exception as e:
        logger.exception("demo failed")
        raise HTTPException(500, str(e)) from e
    return {
        "success": True,
        "match": _public_match(m),
    }


def _public_match(m: dict[str, Any]) -> dict[str, Any]:
    # Cap moves in JSON for large games — full still stored on disk
    out = dict(m)
    moves = out.get("moves") or []
    if len(moves) > 80:
        out["moves"] = moves[:20] + [{"_truncated": len(moves) - 40}] + moves[-20:]
        out["moves_count"] = len(moves)
    return out


def _demo_stream(body: DemoBody):
    import json

    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.chess.personas import get_persona
    from gaming.src.stack.agentic.chess.arena import iter_match
    from gaming.src.stack.agentic import ledger

    def gen():
        reg = get_registry()
        agents = reg.ensure_demo_agents()
        by_id = {a["agent_id"]: a for a in agents}
        for a in agents:
            p = get_persona(a["agent_id"])
            if p:
                a["mind"] = p["mind"]
        raja = by_id["agent_raja_kia_alekhine"]
        nero = by_id["agent_nero_sicilian_french"]
        if body.white.lower() == "nero":
            white, black = nero, raja
            a_id, b_id = nero["agent_id"], raja["agent_id"]
        else:
            white, black = raja, nero
            a_id, b_id = raja["agent_id"], nero["agent_id"]

        svc = get_match_service()
        m = svc.create_match(
            agent_a_id=a_id,
            agent_b_id=b_id,
            stake_usdc=body.stake_usdc,
            white_agent_id=white["agent_id"],
        )
        m = svc.lock_both(m["match_id"])
        yield json.dumps({"type": "match_locked", "match": m}) + "\n"

        final = None
        for ev in iter_match(
            white_agent=white,
            black_agent=black,
            move_delay_sec=body.move_delay_sec,
            seed=body.seed,
        ):
            if ev.get("type") == "final":
                final = ev
            yield json.dumps(ev) + "\n"

        if final:
            # settle using match service path
            data_m = svc.get(m["match_id"])
            if data_m and data_m["status"] == "locked":
                if final["result"] == "draw":
                    esc = ledger.settle(m["match_id"], white["wallet_address"], result="draw")
                    reg.update_stats(white["agent_id"], "draw")
                    reg.update_stats(black["agent_id"], "draw")
                else:
                    wid = final["winner_agent_id"]
                    wagent = white if wid == white["agent_id"] else black
                    lagent = black if wagent is white else white
                    esc = ledger.settle(m["match_id"], wagent["wallet_address"], result="win")
                    reg.update_stats(wagent["agent_id"], "win")
                    reg.update_stats(lagent["agent_id"], "loss")
                # persist
                from gaming.src.stack.agentic.store import load_json, save_json
                from datetime import datetime, timezone

                store = load_json("matches.json", {"matches": {}})
                rec = store["matches"][m["match_id"]]
                rec["status"] = "settled"
                rec["result"] = final["result"]
                rec["winner_agent_id"] = final.get("winner_agent_id")
                rec["pgn"] = final.get("pgn")
                rec["moves"] = final.get("moves")
                rec["escrow"] = esc
                rec["settled_at"] = datetime.now(timezone.utc).isoformat()
                store["matches"][m["match_id"]] = rec
                save_json("matches.json", store)
                yield json.dumps({"type": "settled", "match_id": m["match_id"], "escrow": esc}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get("/ledger")
async def ledger_snapshot(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic import ledger

    snap = ledger.snapshot()
    # hide long tx history tail
    txs = snap.get("txs") or []
    return {
        "success": True,
        "balances": snap.get("balances"),
        "escrows_count": len(snap.get("escrows") or {}),
        "txs_tail": txs[-20:],
    }


@router.get("/time-controls")
async def time_controls(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.clock import list_time_controls

    return {"success": True, "controls": list_time_controls()}


@router.get("/economy/policy")
async def economy_policy(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Public fee / deploy policy for creators wiring agents."""
    from gaming.src.stack.agentic.economy.fees import (
        DEFAULT_PLATFORM_FEE_BPS,
        MAX_CREATOR_FEE_BPS,
        DEFAULT_CREATOR_FEE_BPS,
    )
    from gaming.src.stack.agentic.economy.spectator import (
        DEFAULT_SPECTATOR_FEE_BPS,
        DEFAULT_CREATOR_SPECTATOR_BPS,
    )

    return {
        "success": True,
        "skill_pot": {
            "platform_fee_bps": DEFAULT_PLATFORM_FEE_BPS,
            "max_creator_fee_bps": MAX_CREATOR_FEE_BPS,
            "default_creator_fee_bps": DEFAULT_CREATOR_FEE_BPS,
            "notes": (
                "pot = 2 * stake; platform_fee from pot; "
                "creator_fee = creator_fee_bps of winner_gross; rest to agent owner wallet"
            ),
        },
        "spectator_pot": {
            "platform_fee_bps": DEFAULT_SPECTATOR_FEE_BPS,
            "creator_pool_bps": DEFAULT_CREATOR_SPECTATOR_BPS,
            "notes": (
                "separate from skill escrow; agents seed via spectator_seed_bps; "
                "winning bettors share remainder; creators split creator pool 50/50"
            ),
        },
        "deploy_template": "/docs see deploy/TEMPLATE_MANIFEST.yaml",
    }


class BetBody(BaseModel):
    bettor_id: str
    side: str = Field(..., description="a or b (agent_a / agent_b)")
    amount_usdc: float = Field(..., gt=0, le=10_000)


@router.post("/matches/{match_id}/spectator/bet")
async def spectator_bet(match_id: str, body: BetBody, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from decimal import Decimal
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    try:
        book = SpectatorBook().place_bet(
            match_id,
            bettor_id=body.bettor_id,
            side=body.side,
            amount_usdc=Decimal(str(body.amount_usdc)),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, "book": book}


@router.get("/matches/{match_id}/spectator")
async def spectator_book(match_id: str, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    book = SpectatorBook().get(match_id)
    if not book:
        raise HTTPException(404, "no spectator book")
    return {"success": True, "book": book}


@router.get("/matches/{match_id}/odds")
async def match_odds(match_id: str, eval_pawns: Optional[float] = None, ply: int = 0, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """
    Live market snapshot: prior win-rate + pool odds + eval blend + risk/reward.
    """
    from decimal import Decimal
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.economy.odds import build_market

    m = get_match_service().get(match_id)
    if not m:
        raise HTTPException(404, "match not found")
    reg = get_registry()
    a = reg.get_agent(m["agent_a_id"]) or {"agent_id": m["agent_a_id"], "name": "A", "stats": {}}
    b = reg.get_agent(m["agent_b_id"]) or {"agent_id": m["agent_b_id"], "name": "B", "stats": {}}
    book = SpectatorBook().get(match_id) or {}
    totals = book.get("totals") or {"a": "0", "b": "0"}
    eco = m.get("economy") or {}
    snap = build_market(
        match_id=match_id,
        agent_a=a,
        agent_b=b,
        pot_a=Decimal(str(totals.get("a") or "0")),
        pot_b=Decimal(str(totals.get("b") or "0")),
        seed_a=Decimal(str(eco.get("spectator_seed_a") or book.get("seed_a") or "0")),
        seed_b=Decimal(str(eco.get("spectator_seed_b") or book.get("seed_b") or "0")),
        eval_pawns=eval_pawns,
        a_is_white=(m.get("white_agent_id") == m.get("agent_a_id")),
        ply=ply or int((m.get("play") or {}).get("plies") or 0),
        settled=m.get("status") == "settled",
    )
    d = snap.to_dict()
    try:
        SpectatorBook().record_odds(match_id, d)
    except Exception:
        pass
    return {"success": True, "market": d}
