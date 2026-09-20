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
    from gaming.src.stack.agentic.chess.rule_book import rule_book_meta
    from gaming.src.stack.agentic.runtime.agent_keys import key_status

    reg = get_registry()
    agents = reg.list_agents()
    llm_status = {
        a.get("name") or a.get("agent_id"): key_status(
            a.get("agent_id") or "", a.get("name") or ""
        )
        for a in agents[:8]
    }
    onchain = False
    try:
        from gaming.src.stack.agentic.onchain import onchain_enabled

        onchain = onchain_enabled()
    except Exception:
        pass
    return {
        "status": "ok",
        "layer": "boardman-agentic",
        "data_dir": str(data_dir()),
        "agents": len(agents),
        "games": len(reg.list_games()),
        "auth": "X-Rematch-Key required for data routes",
        "rule_book": rule_book_meta(),
        "onchain_enabled": onchain,
        "llm_keys": llm_status,
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


@router.get("/house")
async def house_snapshot(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Boardman House cashier — does not play. Telegram remains human-vs-human."""
    from gaming.src.stack.agentic.house import get_house

    snap = get_house().snapshot()
    return {"success": True, "house": snap}


@router.get("/house/floor")
async def house_floor(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Live tables (cap 5 playing) + queued + waiting."""
    from gaming.src.stack.agentic.house import get_house

    return {"success": True, "floor": get_house().floor()}


class HouseOpenBody(BaseModel):
    agent_a_id: str
    agent_b_id: str
    stake_usdc: Optional[float] = Field(None, gt=0, le=1000)
    white_agent_id: Optional[str] = None
    chain_id: str = "arc"
    game_id: str = "agentic.chess_standard"


@router.post("/house/matches")
async def house_open_match(body: HouseOpenBody, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.house import get_house

    try:
        m = get_house().open_match(
            agent_a_id=body.agent_a_id,
            agent_b_id=body.agent_b_id,
            stake_usdc=body.stake_usdc,
            white_agent_id=body.white_agent_id,
            chain_id=body.chain_id,
            game_id=body.game_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, "match": m, "clerk": "agent_boardman_house"}


@router.post("/house/matches/{match_id}/lock")
async def house_lock(match_id: str, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.house import get_house

    try:
        m = get_house().lock(match_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, "match": m, "clerk": "agent_boardman_house"}


class HouseBetBody(BaseModel):
    bettor_id: str
    side: str = Field(..., description="a|b or agent name/id or white|black")
    amount_usdc: float = Field(..., gt=0, le=10_000)


@router.post("/house/matches/{match_id}/bets")
async def house_take_bet(match_id: str, body: HouseBetBody, _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from decimal import Decimal
    from gaming.src.stack.agentic.house import get_house

    try:
        out = get_house().take_bet(
            match_id,
            bettor_id=body.bettor_id,
            side=body.side,
            amount_usdc=Decimal(str(body.amount_usdc)),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, **out}


class HousePlayBody(RunBody):
    wait: bool = Field(
        False,
        description="True = block until settle. False = seat on the 5-table floor (or queue).",
    )


class HouseRematchBody(BaseModel):
    stake_usdc: Optional[float] = Field(None, gt=0, le=1000)
    white: str = Field("raja", description="raja | nero")
    wait: bool = Field(False, description="False = return immediately; lock+play in worker")
    move_delay_sec: float = Field(0.05, ge=0, le=5)
    seed: Optional[int] = None
    game_id: str = "agentic.chess_standard"


@router.post("/house/rematch")
async def house_rematch(body: HouseRematchBody = HouseRematchBody(), _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Raja vs Nero via House — same path as scripts/run_house_session.py."""
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.disbursement import DisbursementDenied

    house = get_house()
    raja = "agent_raja_kia_alekhine"
    nero = "agent_nero_sicilian_french"
    white_id = nero if str(body.white).lower().startswith("n") else raja
    try:
        out = house.rematch(
            agent_a_id=raja,
            agent_b_id=nero,
            stake_usdc=body.stake_usdc,
            game_id=body.game_id,
            white_agent_id=white_id,
            move_delay_sec=body.move_delay_sec,
            seed=body.seed,
            wait=body.wait,
        )
    except DisbursementDenied as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"success": True, "clerk": "agent_boardman_house", **out}


class HouseScheduleBody(BaseModel):
    cadence_sec: Optional[int] = Field(None, ge=0, le=86400, description="seconds between session games (0 = continuous)")
    burst_games: Optional[int] = Field(None, ge=0, le=1000, description="play N games back-to-back, then resume cadence")
    enabled: Optional[bool] = None


@router.get("/house/schedule")
async def house_schedule_get(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.house_schedule import PRESETS, read_schedule

    sched = read_schedule()
    return {"success": True, "schedule": sched, "presets": PRESETS, "clerk": "agent_boardman_house"}


@router.post("/house/schedule")
async def house_schedule_set(
    body: HouseScheduleBody = HouseScheduleBody(),
    _: ApiKeyPrincipal = Depends(require_stack_api_key),
):
    from gaming.src.stack.agentic.house_schedule import (
        clamp_burst,
        clamp_cadence,
        write_schedule,
    )

    changes: dict[str, Any] = {}
    if body.cadence_sec is not None:
        changes["cadence_sec"] = clamp_cadence(body.cadence_sec)
    if body.burst_games is not None:
        changes["burst_games"] = clamp_burst(body.burst_games)
    if body.enabled is not None:
        changes["enabled"] = bool(body.enabled)
    sched = write_schedule(set_by="admin_desk", **changes)
    return {"success": True, "schedule": sched, "clerk": "agent_boardman_house"}


@router.get("/house/status")
async def house_status(_: ApiKeyPrincipal = Depends(require_stack_api_key)):
    """Operator status: schedule, agent health, bot process, last settlement."""
    import os
    import socket
    from datetime import datetime, timedelta, timezone

    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.house_schedule import PRESETS, read_schedule
    from gaming.src.stack.agentic.metrics import build_public_metrics
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json

    sched = read_schedule()

    def _probe(port: int) -> bool:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1.5)
            s.close()
            return True
        except OSError:
            return False

    bot = {"running": False, "pid": None}
    # python:3.12-slim has no pgrep — scan /proc directly.
    try:
        for pid in os.listdir("/proc"):
            if not str(pid).isdigit():
                continue
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "ignore").replace("\x00", " ")
            except Exception:
                continue
            if "gaming.src.bot.main" in cmd:
                bot = {"running": True, "pid": str(pid)}
                break
    except Exception:
        pass

    ledger = load_json("ledger.json", {"balances": {}, "escrows": {}, "txs": []})
    balances = ledger.get("balances") or {}

    reg = get_registry()
    agents_out: list[dict[str, Any]] = []
    try:
        demo = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    except Exception:
        demo = {}
    for aid, name, port in (
        ("agent_raja_kia_alekhine", "Raja", 18761),
        ("agent_nero_sicilian_french", "Nero", 18762),
    ):
        a = demo.get(aid) or {}
        wallet = a.get("wallet_address") or ""
        agents_out.append(
            {
                "agent_id": aid,
                "name": name,
                "wallet": wallet,
                "bankroll_usdc": float(balances.get(wallet.lower()) or 0),
                "webhook_up": _probe(port),
                "webhook_port": port,
            }
        )
    try:
        house = get_house()
        snap = house.snapshot()
        house_wallet = snap.get("wallet_address") or ""
    except Exception:
        house_wallet = ""
    agents_out.insert(
        0,
        {
            "agent_id": "agent_boardman_house",
            "name": "Boardman House",
            "wallet": house_wallet,
            "bankroll_usdc": float(balances.get(house_wallet.lower()) or 0),
            "webhook_up": True,
            "webhook_port": None,
        },
    )

    now = datetime.now(timezone.utc)
    metrics = build_public_metrics(limit=10)
    last_settled: dict[str, Any] = {}
    games_24h = 0
    for m in metrics.get("matches") or []:
        if m.get("status") != "settled":
            continue
        if not last_settled:
            last_settled = m
        try:
            sa = m.get("settled_at") or ""
            if sa:
                settled_dt = datetime.fromisoformat(sa.replace("Z", "+00:00"))
                if settled_dt >= now - timedelta(hours=24):
                    games_24h += 1
        except Exception:
            pass

    next_game_at: Optional[str] = None
    next_in_sec: Optional[int] = None
    if sched.get("enabled") and sched.get("cadence_sec", 0) > 0 and sched.get("last_settled_at"):
        try:
            last_dt = datetime.fromisoformat(str(sched["last_settled_at"]).replace("Z", "+00:00"))
            nxt = last_dt + timedelta(seconds=int(sched["cadence_sec"]))
            next_game_at = nxt.isoformat()
            next_in_sec = max(0, int((nxt - now).total_seconds()))
        except Exception:
            pass

    api_ok = True
    try:
        import gaming.src.backend.supabase_client as _sc  # noqa: F401
    except Exception:
        api_ok = True

    return {
        "success": True,
        "generated_at": now.isoformat(),
        "api": {"ok": api_ok, "host": os.getenv("BOARDMAN_AGENTIC_DATA") or "data/agentic"},
        "bot": bot,
        "schedule": sched,
        "presets": PRESETS,
        "agents": agents_out,
        "games_24h": games_24h,
        "games_live": metrics.get("volume", {}).get("games_live"),
        "last_settled": {
            "match_id": last_settled.get("match_id"),
            "result": last_settled.get("result"),
            "winner": (last_settled.get("winner") or {}).get("name"),
            "stake_usdc": last_settled.get("stake_usdc"),
            "settled_at": last_settled.get("settled_at"),
        },
        "next_game_at": next_game_at,
        "next_in_sec": next_in_sec,
        "clerk": "agent_boardman_house",
    }


@router.post("/house/matches/{match_id}/play")
async def house_play(match_id: str, body: HousePlayBody = HousePlayBody(), _: ApiKeyPrincipal = Depends(require_stack_api_key)):
    from gaming.src.stack.agentic.house import get_house

    try:
        out = get_house().play(
            match_id,
            move_delay_sec=body.move_delay_sec,
            seed=body.seed,
            wait=body.wait,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if body.wait:
        return {"success": True, "match": out, "clerk": "agent_boardman_house"}
    return {"success": True, "clerk": "agent_boardman_house", **out}


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


@router.get("/agents/onchain_volume")
async def agents_onchain_volume(
    chain: int = 0,
    days: Optional[int] = None,
    _: ApiKeyPrincipal = Depends(require_stack_api_key),
):
    """
    Aggregate volumes per agent.

    - `totals` — locked/settled volumes derived from matches records (fast, local).
    - `onchain` — real USDC transfer volume per agent wallet (eth_getLogs scan,
      cached in data/agentic/). Only computed when `chain=1` is passed so the
      default call stays fast. Pass `days=N` for a rolling N-day window.
    """
    from gaming.src.stack.agentic.store import load_json

    try:
        data = load_json("matches.json", {"matches": {}})
    except Exception:
        raise HTTPException(500, "matches data not available")
    matches = list(data.get("matches", {}).values())
    totals: dict[str, dict[str, float]] = {}
    for m in matches:
        stake = float(m.get("stake_usdc") or 0)
        # if settlement_mode indicates onchain, count as locked
        mode = m.get("settlement_mode") or "demo_ledger"
        for aid in (m.get("agent_a_id"), m.get("agent_b_id")):
            if not aid:
                continue
            t = totals.setdefault(
                aid,
                {"locked_count": 0, "locked_usdc": 0.0, "settled_count": 0, "settled_usdc": 0.0},
            )
            if mode == "onchain":
                t["locked_count"] += 1
                t["locked_usdc"] += stake
            # settled onchain if onchain_settle present
            if m.get("onchain_settle"):
                t["settled_count"] += 1
                # winner gets owner_payout in fee_split, but stake is a reasonable proxy
                t["settled_usdc"] += stake

    out: dict[str, Any] = {"success": True, "totals": totals}
    if chain:
        out["onchain"] = _agents_onchain_transfer_volume(days=days)
        out["window_days"] = days
    return out


def _agents_onchain_transfer_volume(days: Optional[int] = None) -> dict[str, Any]:
    """Best-effort real on-chain transfer volume per registered agent wallet."""
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.onchain import usdc_transfer_volume

    res: dict[str, Any] = {}
    try:
        for a in get_registry().list_agents():
            wid = a.get("wallet_address") or ""
            if not wid:
                continue
            try:
                vol = usdc_transfer_volume(
                    wid, chain_id=a.get("chain_id") or "arc", days=days
                )
                res[a["agent_id"]] = {
                    "wallet": wid,
                    "in_usdc": vol["in_usdc"],
                    "out_usdc": vol["out_usdc"],
                    "count_in": vol["count_in"],
                    "count_out": vol["count_out"],
                    "scanned_from": vol["scanned_from"],
                    "scanned_to": vol["scanned_to"],
                    "window_days": vol.get("window_days"),
                    "cached": vol.get("cached", False),
                }
            except Exception as exc:
                res[a["agent_id"]] = {"wallet": wid, "error": str(exc)}
    except Exception as exc:
        res["_error"] = str(exc)
    return res


@router.get("/agents/{agent_id}/onchain_volume")
async def agent_onchain_volume(
    agent_id: str,
    days: Optional[int] = None,
    _: ApiKeyPrincipal = Depends(require_stack_api_key),
):
    """Real on-chain USDC transfer volume (in/out) for a single agent's wallet."""
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.onchain import usdc_transfer_volume

    a = get_registry().get_agent(agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    wid = a.get("wallet_address") or ""
    if not wid:
        raise HTTPException(400, "agent has no wallet_address")
    try:
        vol = usdc_transfer_volume(
            wid, chain_id=a.get("chain_id") or "arc", days=days
        )
    except Exception as exc:
        raise HTTPException(502, f"on-chain volume read failed: {exc}") from exc
    return {
        "success": True,
        "agent_id": agent_id,
        "wallet": wid,
        "chain_id": a.get("chain_id") or "arc",
        "window_days": days,
        "volume": vol,
    }


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    _: ApiKeyPrincipal = Depends(require_stack_api_key),
):
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.chess.personas import get_persona
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.runtime.agent_keys import key_status

    a = get_registry().get_agent(agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    p = get_persona(agent_id)
    if p:
        a = {**a, "mind": p["mind"], "openings": p["openings"]}
    wallet = a.get("wallet_address") or ""
    ledger_bal = ledger.balance(wallet)
    a["usdc_balance"] = str(ledger_bal)  # legacy field = ledger book entry
    a["ledger_balance_usdc"] = str(ledger_bal)
    a["wallet"] = {
        "address": wallet,
        "chain_id": a.get("chain_id") or "arc",
        "identity_contract": a.get("identity_contract"),
        "ledger_balance_usdc": str(ledger_bal),
        "onchain_balance_usdc": None,
        "spendable_usdc": str(ledger_bal),
        "source": "demo_ledger",
    }
    try:
        from gaming.src.stack.agentic.onchain import onchain_enabled, usdc_balance

        if onchain_enabled() and wallet:
            onchain_bal = usdc_balance(wallet, chain_id=a.get("chain_id") or "arc")
            a["wallet"]["onchain_balance_usdc"] = str(onchain_bal)
            a["wallet"]["spendable_usdc"] = str(onchain_bal)
            a["wallet"]["source"] = "arc_onchain"
            a["onchain_balance_usdc"] = str(onchain_bal)
            # Prefer on-chain as the play balance when live
            a["usdc_balance"] = str(onchain_bal)
    except Exception as exc:
        a["wallet"]["onchain_error"] = str(exc)
    a["llm"] = key_status(a.get("agent_id") or agent_id, a.get("name") or "")
    return {"success": True, "agent": a}


@router.get("/agents/{agent_id}/wallet")
async def get_agent_wallet(
    agent_id: str,
    _: ApiKeyPrincipal = Depends(require_stack_api_key),
):
    """Wallet identity + ledger vs real Arc USDC balance for an agent."""
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic import ledger

    a = get_registry().get_agent(agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    wallet = a.get("wallet_address") or ""
    if not wallet:
        raise HTTPException(400, "agent has no wallet_address")
    ledger_bal = ledger.balance(wallet)
    out: dict[str, Any] = {
        "success": True,
        "agent_id": agent_id,
        "name": a.get("name"),
        "wallet_address": wallet,
        "identity_contract": a.get("identity_contract"),
        "chain_id": a.get("chain_id") or "arc",
        "ledger_balance_usdc": str(ledger_bal),
        "onchain_balance_usdc": None,
        "spendable_usdc": str(ledger_bal),
        "settlement_mode": "demo_ledger",
        "plays_as": wallet,
        "note": "Agent stakes and settles using wallet_address — not a separate ledger id.",
    }
    try:
        from gaming.src.stack.agentic.onchain import onchain_enabled, usdc_balance

        if onchain_enabled():
            onchain_bal = usdc_balance(wallet, chain_id=out["chain_id"])
            out["onchain_balance_usdc"] = str(onchain_bal)
            out["spendable_usdc"] = str(onchain_bal)
            out["settlement_mode"] = "onchain"
    except Exception as exc:
        out["onchain_error"] = str(exc)
    return out


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
    side: str = Field(..., description="a or b or draw")
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


@router.get("/public/metrics")
async def public_metrics(limit: int = 100):
    """Unauthenticated Raja vs Nero PNL + match proofs.

    Sanitized: no private keys, no full move lists, no spectator bettor ids.
    """
    from gaming.src.stack.agentic.metrics import public_metrics as _metrics

    cap = max(1, min(int(limit or 100), 200))
    return _metrics(limit=cap)


@router.get("/admin/metrics-detail")
async def admin_metrics_detail():
    """Detailed admin metrics: human vs agent volume, wallet balances, user count, running totals."""
    from gaming.src.stack.agentic.metrics import build_public_metrics
    from gaming.src.stack.agentic.store import load_json
    from decimal import Decimal
    from datetime import datetime, timezone

    metrics = build_public_metrics(limit=500)
    vol = metrics.get("volume", {})
    agents = metrics.get("agents", [])
    matches = metrics.get("matches", [])

    # Wallet balances
    agent_store = load_json("agents.json", {"agents": {}})
    agent_map = agent_store.get("agents") or {}
    wallet_balances = {}
    for aid, rec in agent_map.items():
        wallet = rec.get("wallet_address") or ""
        if wallet:
            try:
                from gaming.src.stack.agentic.onchain import usdc_balance
                bal = usdc_balance(wallet)
                wallet_balances[aid] = {
                    "wallet": wallet,
                    "balance_usdc": str(bal),
                    "name": rec.get("name") or aid,
                }
            except Exception:
                wallet_balances[aid] = {
                    "wallet": wallet,
                    "balance_usdc": "unknown",
                    "name": rec.get("name") or aid,
                }

    # Human vs Agent volume split
    human_volume = Decimal("0")
    agent_volume = Decimal("0")
    human_matches = 0
    agent_matches = 0
    human_bet_volume = Decimal("0")
    agent_bet_volume = Decimal("0")

    RAJA = "agent_raja_kia_alekhine"
    NERO = "agent_nero_sicilian_french"
    agent_ids = {RAJA, NERO}

    for m in matches:
        a = m.get("agent_a_id") or ""
        b = m.get("agent_b_id") or ""
        is_agent_match = a in agent_ids and b in agent_ids
        stake = Decimal(str(m.get("stake_usdc") or "0"))

        if is_agent_match:
            agent_volume += stake * 2
            agent_matches += 1
            # spectator bets on agent matches
            book = m.get("spectator_book") or {}
            bets = book.get("bets") or []
            for bet in bets:
                agent_bet_volume += Decimal(str(bet.get("amount") or "0"))
        else:
            human_volume += stake * 2
            human_matches += 1
            book = m.get("spectator_book") or {}
            bets = book.get("bets") or []
            for bet in bets:
                human_bet_volume += Decimal(str(bet.get("amount") or "0"))

    # LP pools
    lp_store = load_json("agent_lp_pools.json", {"pools": {}})
    lp_pools = lp_store.get("pools") or {}
    lp_summary = {}
    total_lp = Decimal("0")
    for aid, pool in lp_pools.items():
        positions = pool.get("positions") or {}
        pool_total = sum(Decimal(str(p.get("amount") or "0")) for p in positions.values())
        realized = sum(Decimal(str(p.get("realized_pnl") or "0")) for p in positions.values())
        lp_summary[aid] = {
            "total_deposited": str(pool_total),
            "realized_pnl": str(realized),
            "positions": len(positions),
        }
        total_lp += pool_total

    # Spectator books summary
    spec_store = load_json("spectator_books.json", {"books": {}})
    spec_books = spec_store.get("books") or {}
    total_spectator_pool = Decimal("0")
    for mid, book in spec_books.items():
        totals = book.get("totals") or {}
        book_total = sum(Decimal(str(v or "0")) for v in totals.values())
        total_spectator_pool += book_total

    # First and latest match
    sorted_matches = sorted(matches, key=lambda x: x.get("created_at") or "")
    first_match = sorted_matches[0] if sorted_matches else None
    last_match = sorted_matches[-1] if sorted_matches else None

    # Unique users (approximate: unique bettor IDs from spectator books)
    uniquebettors = set()
    for mid, book in spec_books.items():
        bets = book.get("bets") or []
        for bet in bets:
            uid = bet.get("user_id") or bet.get("profile_id") or ""
            if uid:
                uniquebettors.add(uid)

    return {
        "success": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_matches": vol.get("matches_total", 0),
            "total_settled": vol.get("matches_settled", 0),
            "total_live": vol.get("games_live", 0),
            "total_transactions": vol.get("transactions", 0),
            "total_skill_volume_usdc": vol.get("skill_volume_usdc", "0"),
            "total_spectator_volume_usdc": vol.get("spectator_volume_usdc", "0"),
            "total_volume_usdc": str(
                Decimal(str(vol.get("skill_volume_usdc", "0"))) +
                Decimal(str(vol.get("spectator_volume_usdc", "0")))
            ),
            "total_onchain_volume_usdc": vol.get("total_onchain_volume_usdc", "0"),
            "first_match_at": first_match.get("created_at") if first_match else None,
            "last_match_at": last_match.get("created_at") if last_match else None,
            "unique_bettors": len(uniquebettors),
        },
        "human_vs_agent": {
            "human": {
                "matches": human_matches,
                "skill_volume_usdc": str(human_volume),
                "bet_volume_usdc": str(human_bet_volume),
            },
            "agent": {
                "matches": agent_matches,
                "skill_volume_usdc": str(agent_volume),
                "bet_volume_usdc": str(agent_bet_volume),
            },
        },
        "wallet_balances": wallet_balances,
        "lp_pools": lp_summary,
        "total_lp_deposited_usdc": str(total_lp),
        "spectator_pool_total_usdc": str(total_spectator_pool),
        "agents": agents,
    }


@router.get("/football/catalog")
async def football_catalog(
    q: Optional[str] = None,
    slot: Optional[str] = None,
    pos: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Public AFM catalog — real seed names, slots, ratings, in-game price."""
    from gaming.src.stack.agentic.games.football_managers.catalog import (
        SLOTS,
        catalog_meta,
        list_players,
    )

    players = list_players(pos=pos, slot=slot)
    if q:
        ql = q.lower()
        players = [p for p in players if ql in (p.get("name") or "").lower()]
    total = len(players)
    cap = max(1, min(int(limit or 200), 500))
    off = max(0, int(offset or 0))
    return {
        "success": True,
        "total": total,
        "slots": list(SLOTS),
        "meta": catalog_meta(),
        "players": players[off : off + cap],
    }


class FootballSimBody(BaseModel):
    """A one-off AFM friendly: two XIs from the catalog (public demo route)."""

    home_name: Optional[str] = None
    away_name: Optional[str] = None
    home_xi: list[str]
    away_xi: list[str]
    match_id: Optional[str] = None  # pass to reproduce the exact seeded match
    home_tactics: Optional[dict] = None  # {formation?, tags?} — what the club set
    away_tactics: Optional[dict] = None


class FootballLineupBody(BaseModel):
    """afm_set_lineup: a club's formation + legal XI + bench (+ tactical tags)."""

    formation: Optional[str] = None
    starters: Optional[list[str]] = None
    bench: Optional[list[str]] = None
    tactical_tags: Optional[list[str]] = None


class FootballSeasonJoinBody(BaseModel):
    agent_id: str


class FootballSeasonOpenBody(BaseModel):
    agent_ids: Optional[list[str]] = None
    start_at: Optional[str] = None  # ISO timestamp
    force: bool = False


@router.post("/football/simulate")
async def football_simulate(body: FootballSimBody):
    """Run the AFM match engine on two submitted XIs (watchable friendly sim).

    The engine stays authoritative server-side: same seeded `simulate_match`
    used by future league fixtures. Response is MatchResult.to_dict() — score,
    outcome and the minute-by-minute feed the 3D broadcast animates.
    """
    import random as _random
    import time as _time

    from gaming.src.stack.agentic.games.football_managers.catalog import get_player
    from gaming.src.stack.agentic.games.football_managers.match_engine import (
        simulate_match,
    )

    def _xi(label: str, ids: list[str]) -> list[str]:
        out: list[str] = []
        for pid in ids:
            p = get_player(pid)
            if not p:
                raise HTTPException(status_code=400, detail=f"unknown player {pid}")
            out.append(pid)
        if not out:
            raise HTTPException(status_code=400, detail=f"{label} XI is empty")
        return out

    home = _xi("home", body.home_xi)
    away = _xi("away", body.away_xi)
    overlap = set(home) & set(away)
    if overlap:
        raise HTTPException(
            status_code=400,
            detail=f"one copy of each player — XI overlap: {sorted(overlap)}",
        )

    mid = (body.match_id or "").strip() or f"afm_friendly_{int(_time.time() * 1000)}_{_random.randrange(10_000)}"
    result = simulate_match(
        mid,
        home_agent_id=body.home_name or "Home FC",
        away_agent_id=body.away_name or "Away FC",
        home_xi=home,
        away_xi=away,
        home_tactics=body.home_tactics,
        away_tactics=body.away_tactics,
    )
    return {
        "success": True,
        "match_id": mid,
        "tactics": {
            "home": body.home_tactics or {"formation": "4-3-3", "tags": ["balanced"]},
            "away": body.away_tactics or {"formation": "4-3-3", "tags": ["balanced"]},
        },
        "result": result.to_dict(),
    }


@router.get("/football/clubs")
async def football_clubs():
    """Agent-owned AFM clubs: formation, tactics, roster + locked lineup."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        list_clubs,
        seed_demo_clubs,
    )

    seed_demo_clubs()
    return {"success": True, "clubs": list_clubs()}


@router.get("/football/clubs/{agent_id}")
async def football_club(agent_id: str):
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        get_club,
        seed_demo_clubs,
        squad_view,
    )

    seed_demo_clubs()
    club = get_club(agent_id)
    if not club:
        raise HTTPException(status_code=404, detail=f"no AFM club for agent {agent_id}")
    return {"success": True, "club": club, "squad": squad_view(agent_id)}


@router.put("/football/clubs/{agent_id}/lineup")
async def football_club_lineup(agent_id: str, body: FootballLineupBody):
    """Set a club's lineup + tactics (agent afm_set_lineup / board Save)."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
        set_lineup,
    )

    seed_demo_clubs()
    try:
        club = set_lineup(
            agent_id,
            formation=body.formation,
            starters=body.starters,
            bench=body.bench,
            tactical_tags=body.tactical_tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"success": True, "club": club}


# ---------------------------------------------------------------- AFM season


@router.get("/football/owner/{agent_id}")
async def football_owner_dashboard(agent_id: str):
    """Owner seat, step 5 — follow one club: results, the agent's decisions,
    table position, the spending log and suspension/injury news."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )
    from gaming.src.stack.agentic.games.football_managers.dashboard import (
        owner_dashboard,
    )

    seed_demo_clubs()
    try:
        dash = owner_dashboard(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "dashboard": dash}


@router.get("/football/report/{agent_id}")
async def football_agent_report(agent_id: str, matchday: Optional[int] = None):
    """Agent FM post-match report — ratings, xG, errors for the club's latest
    (or a given) played fixture. The "why we lost" file the agent reads."""
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.games.football_managers import report as R

    seed_demo_clubs()
    try:
        if matchday is not None:
            from gaming.src.stack.agentic.games.football_managers.season import _state

            s = _state().get("season")
            if not s:
                raise HTTPException(status_code=404, detail="no season running")
            info = (s.get("matchdays") or {}).get(str(matchday)) or {}
            for r in info.get("results") or []:
                if agent_id in (r.get("home_agent_id"), r.get("away_agent_id")):
                    rep = R.match_report(int(s["season_no"]), matchday, r["home_agent_id"], r["away_agent_id"])
                    rep["my_side"] = "home" if r["home_agent_id"] == agent_id else "away"
                    rep["my"] = rep[rep["my_side"]]
                    return {"success": True, "report": rep}
            raise HTTPException(status_code=404, detail=f"no result for {agent_id} on matchday {matchday}")
        rep = R.latest_report_for_agent(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "report": rep}


@router.get("/football/season/report")
async def football_match_report(season_no: int, matchday: int, home: str, away: str):
    """Full FM post-match report for one recorded fixture (both sides):
    per-player ratings, xG, error attribution and the "why" headline lines."""
    from gaming.src.stack.agentic.games.football_managers import report as R

    try:
        rep = R.match_report(int(season_no), int(matchday), home, away)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "report": rep}


@router.get("/football/season")
async def football_season():
    """Season state for humans + agents (afm_view_season): standings, fixtures,
    recent results, pot, next matchday deadline."""
    from gaming.src.stack.agentic.games.football_managers.season import get_season

    return {"success": True, "season": get_season()}


@router.post("/football/season/join")
async def football_season_join(body: FootballSeasonJoinBody):
    """afm_join_season — queue the club for the next season."""
    from gaming.src.stack.agentic.games.football_managers.season import join_season

    try:
        return {"success": True, **join_season(body.agent_id)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/football/season/open")
async def football_season_open(body: FootballSeasonOpenBody):
    """Open a season: collect USDC entries, build schedule, zero standings."""
    from datetime import datetime

    from gaming.src.stack.agentic.games.football_managers.season import open_season

    start = datetime.fromisoformat(body.start_at) if body.start_at else None
    try:
        snap = open_season(body.agent_ids, start_at=start, force=body.force)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"success": True, "season": snap}


@router.post("/football/season/tick")
async def football_season_tick():
    """Advance the season clock: open due matchdays, resolve past deadlines.
    Called by the daily scheduler (and by the standings page's watch button)."""
    from gaming.src.stack.agentic.games.football_managers.season import tick

    return {"success": True, **tick()}


@router.post("/football/season/reset")
async def football_season_reset():
    """Dev/ops: drop the current season state (no money moves)."""
    from gaming.src.stack.agentic.games.football_managers.season import reset_season

    return {"success": True, **reset_season()}


@router.get("/football/season/replay")
async def football_season_replay(matchday: int, home: str, away: str):
    """A recorded season fixture, replayable on the tactics board (feed + lineups)."""
    from gaming.src.stack.agentic.games.football_managers.season import get_replay

    try:
        replay = get_replay(int(matchday), home, away)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "replay": replay}


@router.get("/football/season/prematch")
async def football_season_prematch(matchday: int, home: str, away: str):
    """The pre-match board for one fixture: locked lineups + tactics, HT plans,
    press quotes and ban/injury news — everything a human reads before kickoff."""
    from gaming.src.stack.agentic.games.football_managers.season import prematch_view

    try:
        view = prematch_view(int(matchday), home, away)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "prematch": view}


@router.get("/football/market")
async def football_market():
    """afm_market (v1): free agents — catalog players with no club owner."""
    from gaming.src.stack.agentic.games.football_managers.catalog import list_players
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )

    seed_demo_clubs()  # re-assert ownership in-process (catalog owner is memory)
    free = [
        {
            "player_id": p["player_id"],
            "name": p.get("name"),
            "primary_pos": p.get("primary_pos"),
            "base_rating": p.get("base_rating"),
            "game_price_usdc": p.get("game_price_usdc"),
            "wage_per_matchday_usdc": p.get("wage_per_matchday_usdc"),
            "nation": p.get("nation"),
        }
        for p in list_players()
        if not p.get("owner_agent_id")
    ]
    return {"success": True, "count": len(free), "free_agents": free}


class FootballAgentCreateBody(BaseModel):
    """Owner seat: build a manager against the playbook."""

    manager_name: str
    club_name: Optional[str] = None
    archetype: str = "tactician"  # one of agent_market.ARCHETYPES
    formation: str = "4-3-3"
    owner_id: Optional[str] = None
    # optional: list the manager for sale the moment it is created
    list_price_usdc: Optional[float] = Field(None, gt=0, le=1_000_000)
    creator_cut_bps: Optional[int] = Field(None, ge=0, le=2000)


class FootballAgentAcquireBody(BaseModel):
    """Owner seat: adopt an unlisted developer-built manager for free."""

    agent_id: str
    owner_id: Optional[str] = None


class FootballAgentWebhookBody(BaseModel):
    """Owner seat: point your manager at the webhook hosting its brain.

    From the next matchday ask on, the House POSTs the matchday context here
    and uses the manager's JSON reply (deterministic playbook fallback when
    unreachable). Empty ``webhook_url`` clears the binding.
    """

    agent_id: str
    webhook_url: Optional[str] = Field(
        None, description="full http(s) URL — empty clears the binding"
    )
    owner_id: Optional[str] = None  # caller — must be the current owner


class FootballAgentListBody(BaseModel):
    """Owner seat: list your manager for sale with a price + creator cut."""

    agent_id: str
    price_usdc: float = Field(..., gt=0, le=1_000_000)
    creator_cut_bps: int = Field(0, ge=0, le=2000)  # developer's % of each sale
    reserve_price_usdc: Optional[float] = Field(
        None, gt=0, le=1_000_000, description="floor — offers below it auto-decline"
    )
    listed_by: Optional[str] = None  # caller — must be the current owner


class FootballAgentDelistBody(BaseModel):
    """Owner seat: pull your manager off the marketplace."""

    agent_id: str
    listed_by: Optional[str] = None


class FootballAgentPurchaseBody(BaseModel):
    """Owner seat: buy a listed manager — price settles, ownership moves.

    ``settlement``: ``auto`` (real USDC when Circle is configured and every
    party has a bound wallet, else the demo ledger) | ``onchain`` (required) |
    ``ledger`` (force the demo book-entry rail).
    """

    agent_id: str
    buyer_id: Optional[str] = None
    settlement: str = Field(
        "auto", description="auto | ledger | onchain — how the price settles"
    )


class FootballAgentOfferBody(BaseModel):
    """Owner seat: a buyer names their price on a listed manager."""

    agent_id: str
    offer_usdc: float = Field(..., gt=0, le=1_000_000)
    buyer_id: Optional[str] = None


class FootballAgentOfferDecisionBody(BaseModel):
    """Owner seat: accept or reject a buyer's offer on your listing."""

    agent_id: str
    offer_id: str
    decided_by: Optional[str] = None  # caller — must be the current owner
    settlement: str = Field(
        "auto", description="accept only — auto | ledger | onchain"
    )


class FootballWalletBindBody(BaseModel):
    """Owner seat: bind a real (Circle) wallet to a marketplace party.

    ``address`` is the Arc USDC address the party is paid to. Pass ``wallet_id``
    too when the party pays from that wallet (a Circle developer-controlled
    wallet) so purchases can move real USDC out of it.
    """

    party_id: str
    address: str = Field(
        ..., description="Arc USDC payout address (0x…)", min_length=42, max_length=42
    )
    wallet_id: Optional[str] = None


class FootballWalletUnbindBody(BaseModel):
    """Owner seat: remove a party's wallet binding."""

    party_id: str
    address: Optional[str] = None


@router.get("/football/agents")
async def football_agents():
    """The manager marketplace — every AFM agent an owner can adopt."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_market_agents,
    )

    return {"success": True, "agents": list_market_agents()}


@router.post("/football/agents/create")
async def football_agents_create(body: FootballAgentCreateBody):
    """Create a manager agent + seed its club (owner seat, step 1)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
    )

    try:
        out = create_manager_agent(
            manager_name=body.manager_name,
            club_name=body.club_name,
            archetype=body.archetype,
            formation=body.formation,
            owner_id=body.owner_id,
            list_price_usdc=str(body.list_price_usdc) if body.list_price_usdc is not None else None,
            creator_cut_bps=body.creator_cut_bps,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/acquire")
async def football_agents_acquire(body: FootballAgentAcquireBody):
    """Adopt an unlisted developer-built manager: ownership moves to the caller."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        acquire_manager_agent,
    )

    try:
        out = acquire_manager_agent(agent_id=body.agent_id, owner_id=body.owner_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/webhook")
async def football_agents_webhook(body: FootballAgentWebhookBody):
    """Owner seat: point your manager at the webhook hosting its brain.

    From the next matchday ask on, the House POSTs the matchday context here
    and locks the manager's JSON reply (deterministic playbook fallback when
    the webhook is unreachable). Empty URL clears the binding.
    """
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        set_manager_webhook,
    )

    try:
        out = set_manager_webhook(
            agent_id=body.agent_id,
            webhook_url=body.webhook_url,
            owner_id=body.owner_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/list")
async def football_agents_list(body: FootballAgentListBody):
    """Owner seat: list your manager for sale (price + creator cut)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_manager_for_sale,
    )

    try:
        out = list_manager_for_sale(
            agent_id=body.agent_id,
            price_usdc=str(body.price_usdc),
            creator_cut_bps=body.creator_cut_bps,
            reserve_price_usdc=str(body.reserve_price_usdc) if body.reserve_price_usdc is not None else None,
            listed_by=body.listed_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/delist")
async def football_agents_delist(body: FootballAgentDelistBody):
    """Owner seat: pull your manager off the marketplace."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        delist_manager_agent,
    )

    try:
        out = delist_manager_agent(agent_id=body.agent_id, listed_by=body.listed_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/offer")
async def football_agents_offer(body: FootballAgentOfferBody):
    """A buyer names their price on a listed manager. Offers below the owner's
    reserve are auto-declined; the rest land pending for the owner."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        make_manager_offer,
    )

    try:
        out = make_manager_offer(
            agent_id=body.agent_id,
            offer_usdc=str(body.offer_usdc),
            buyer_id=body.buyer_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/offer/accept")
async def football_agents_offer_accept(body: FootballAgentOfferDecisionBody):
    """The owner accepts a buyer's offer — sale settles at the offered price.
    Same settlement rail as buy-now (auto | onchain | ledger)."""
    import asyncio

    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        accept_manager_offer,
    )

    try:
        # a real-USDC settlement blocks on Circle transfers — run off the loop
        out = await asyncio.to_thread(
            accept_manager_offer,
            agent_id=body.agent_id,
            offer_id=body.offer_id,
            accept_by=body.decided_by,
            settlement=body.settlement,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/offer/reject")
async def football_agents_offer_reject(body: FootballAgentOfferDecisionBody):
    """The owner turns a buyer's offer down — the listing stays up."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        reject_manager_offer,
    )

    try:
        out = reject_manager_offer(
            agent_id=body.agent_id,
            offer_id=body.offer_id,
            reject_by=body.decided_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.post("/football/agents/purchase")
async def football_agents_purchase(body: FootballAgentPurchaseBody):
    """Buy a listed manager: the price settles and ownership transfers to the
    buyer (creator cut paid to the developer). Default ``auto`` settles in
    real USDC from the buyer's bound Circle wallet when every party has one,
    and falls back to the demo ledger otherwise."""
    import asyncio

    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        purchase_manager_agent,
    )

    try:
        # a real-USDC sale blocks on Circle transfer + confirmation — run off
        # the event loop (ledger sales are cheap and fine in a thread too)
        out = await asyncio.to_thread(
            purchase_manager_agent,
            agent_id=body.agent_id,
            buyer_id=body.buyer_id,
            settlement=body.settlement,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, **out}


@router.get("/football/agents/wallet")
async def football_agents_wallet(party_id: str):
    """Wallet status for a marketplace party: what they pay with and get paid
    to — demo ledger wallet vs a bound real (Circle) wallet on Arc."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        wallet_status,
    )

    return {"success": True, "wallet": wallet_status(party_id)}


@router.get("/football/agents/sales")
async def football_agents_sales(party_id: str = ""):
    """Owner dashboard desk: money a party has earned from manager sales and
    the listing history — earnings (seller proceeds + developer creator cuts),
    the managers they own with their live listing state, and the timeline of
    every list / relist / delist / sale they were part of."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        party_sales_view,
    )

    return {"success": True, "sales": party_sales_view(party_id)}


@router.post("/football/agents/wallet/bind")
async def football_agents_wallet_bind(body: FootballWalletBindBody):
    """Bind a real (Circle) wallet to a marketplace party so purchases can
    settle in real USDC (the demo ledger stays the fallback until then)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        bind_party_wallet,
    )

    try:
        rec = bind_party_wallet(
            party_id=body.party_id,
            address=body.address,
            wallet_id=body.wallet_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "wallet": rec}


@router.post("/football/agents/wallet/unbind")
async def football_agents_wallet_unbind(body: FootballWalletUnbindBody):
    """Remove a marketplace party's wallet binding (back to demo ledger)."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        unbind_party_wallet,
    )

    try:
        removed = unbind_party_wallet(party_id=body.party_id, address=body.address)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "removed": removed}


class FootballCupOpenBody(BaseModel):
    """Open a knockout cup over AFM clubs (no entry fee in v0)."""

    agent_ids: Optional[list[str]] = None  # default: every club with a roster
    start_at: Optional[str] = None  # ISO timestamp
    title: Optional[str] = None
    salt: Optional[str] = None  # controls the seeded tie match_ids (replays)
    force: bool = False


# ---------------------------------------------------------------- AFM cup


@router.get("/football/cup")
async def football_cup():
    """Knockout cup state: bracket rounds, played ties, champion."""
    from gaming.src.stack.agentic.games.football_managers.cup import get_cup

    return {"success": True, "cup": get_cup()}


@router.post("/football/cup/open")
async def football_cup_open(body: FootballCupOpenBody):
    """Open a single-elimination cup. Knockout rules: a level 90' tie goes to
    extra time and, if still level, a penalty shootout (require_result)."""
    from datetime import datetime

    from gaming.src.stack.agentic.games.football_managers.cup import open_cup

    start = datetime.fromisoformat(body.start_at) if body.start_at else None
    try:
        snap = open_cup(
            body.agent_ids,
            start_at=start,
            title=body.title,
            salt=body.salt,
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"success": True, "cup": snap}


@router.post("/football/cup/tick")
async def football_cup_tick():
    """Advance the cup clock: open due rounds, resolve past deadlines (winner
    required — draws are settled in extra time / on penalties)."""
    from gaming.src.stack.agentic.games.football_managers.cup import tick

    return {"success": True, **tick()}


@router.post("/football/cup/reset")
async def football_cup_reset():
    """Dev/ops: drop the current cup state (no money moves)."""
    from gaming.src.stack.agentic.games.football_managers.cup import reset_cup

    return {"success": True, **reset_cup()}


@router.get("/football/cup/replay")
async def football_cup_replay(round_no: int, home: str, away: str):
    """A recorded cup tie, replayable on the tactics board (feed + lineups)."""
    from gaming.src.stack.agentic.games.football_managers.cup import get_cup_replay

    try:
        replay = get_cup_replay(int(round_no), home, away)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": True, "replay": replay}
