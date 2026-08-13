"""Boardman House runtime — one agent cashiers every agent-vs-agent match.

Playing agents keep their own wallets. House opens the match, locks both
stakes (via existing escrow / ledger), takes spectator bets, and settles.
It never appears as white/black or side a/b.

Floor capacity is 5 live *playing* tables (env BOARDMAN_HOUSE_TABLES).
More matches may sit locked/queued. Raise the env later for 25.
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.agents.boardman.manifest import HOUSE_ID, MANIFEST
from gaming.src.stack.agentic.registry import get_registry

logger = logging.getLogger(__name__)

LIVE_STATUSES = frozenset(
    {"open", "locked", "partial_lock", "playing", "queued", "settle_failed", "locking"}
)
BET_STATUSES = frozenset({"open", "locked", "partial_lock", "playing", "queued"})


def max_tables() -> int:
    try:
        n = int(os.getenv("BOARDMAN_HOUSE_TABLES") or "5")
    except ValueError:
        n = 5
    return max(1, min(n, 25))


_floor_lock = threading.RLock()
_workers: dict[str, Future] = {}
_pool: Optional[ThreadPoolExecutor] = None


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _floor_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=max_tables(), thread_name_prefix="house-table")
            # Don't pin the process on leftover tables (pytest / laptop hub).
            for t in getattr(_pool, "_threads", []):
                t.daemon = True
        return _pool

HOUSE_NAMES = {n.lower() for n in (MANIFEST.get("display_names") or [])} | {
    "boardman",
    "my boardman",
    "house",
}


def _seal_house(rec: dict[str, Any]) -> dict[str, Any]:
    """Bind the venue wallet to feeRecipient and wipe any spend key."""
    from gaming.src.stack.agentic.disbursement import (
        configured_escrow_address,
        house_public_wallet,
        public_policy,
        seal_house_secrets,
    )
    from gaming.src.stack.agentic.store import load_json, save_json

    wallet = house_public_wallet()
    if wallet:
        rec["wallet_address"] = wallet
    rec["role"] = "house"
    rec["escrow_contract"] = configured_escrow_address()
    rec["disbursement_policy"] = public_policy()["policy"]
    rec["wallet_role"] = "fee_recipient"
    rec["plays_games"] = False
    store = load_json("agents.json", {"agents": {}})
    store.setdefault("agents", {})[HOUSE_ID] = rec
    save_json("agents.json", store)
    seal_house_secrets()
    return rec


def ensure_house() -> dict[str, Any]:
    """Register the House agent if missing / version-stale, then seal spend keys."""
    from gaming.src.stack.agentic.agents.boardman.manifest import MANIFEST as H

    reg = get_registry()
    existing = reg.get_agent(HOUSE_ID)
    if not (
        existing
        and existing.get("version") == H.get("version")
        and existing.get("role") == "house"
    ):
        existing = reg.register_from_manifest(H)
    return _seal_house(existing)


def is_house(agent_id: Optional[str]) -> bool:
    if not agent_id:
        return False
    if agent_id == HOUSE_ID:
        return True
    rec = get_registry().get_agent(agent_id)
    return bool(rec and rec.get("role") == "house")


def resolve_side(match: dict[str, Any], side: str) -> str:
    """Map a human/agent label to book slot a|b using the match record."""
    s = (side or "").strip().lower()
    if s in {"a", "0"}:
        return "a"
    if s in {"b", "1"}:
        return "b"
    a_id = (match.get("agent_a_id") or "").lower()
    b_id = (match.get("agent_b_id") or "").lower()
    if s == a_id or s in {"agent_a", "p1"}:
        return "a"
    if s == b_id or s in {"agent_b", "p2"}:
        return "b"
    white = (match.get("white_agent_id") or "").lower()
    black = (match.get("black_agent_id") or "").lower()
    if s in {"white", "p1"}:
        return "a" if white == a_id else "b"
    if s in {"black", "p2"}:
        return "b" if black == b_id else "a"
    reg = get_registry()
    for slot, aid in (("a", match.get("agent_a_id")), ("b", match.get("agent_b_id"))):
        rec = reg.get_agent(aid or "") or {}
        name = (rec.get("name") or "").lower()
        if s == name or s == (aid or "").lower():
            return slot
    raise ValueError("side must resolve to a or b for this match")


def live_match_for_agent(agent_id: str) -> Optional[dict[str, Any]]:
    """Return the live match this contestant is already in, if any."""
    from gaming.src.stack.agentic.matches import get_match_service

    for m in get_match_service().list_matches(200):
        if m.get("status") not in LIVE_STATUSES:
            continue
        if agent_id in {m.get("agent_a_id"), m.get("agent_b_id")}:
            return m
    return None


def _playing_ids() -> list[str]:
    from gaming.src.stack.agentic.matches import get_match_service

    return [
        m["match_id"]
        for m in get_match_service().list_matches(200)
        if m.get("status") == "playing"
    ]


def _queued() -> list[dict[str, Any]]:
    from gaming.src.stack.agentic.matches import get_match_service

    q = [m for m in get_match_service().list_matches(200) if m.get("status") == "queued"]
    q.sort(key=lambda m: m.get("queued_at") or m.get("created_at") or "")
    return q


def _set_status(match_id: str, status: str, **extra: Any) -> dict[str, Any]:
    from gaming.src.stack.agentic.store import load_json, save_json
    from datetime import datetime, timezone

    store = load_json("matches.json", {"matches": {}})
    rec = store["matches"].get(match_id)
    if not rec:
        raise ValueError("match not found")
    rec["status"] = status
    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
    rec.update(extra)
    store["matches"][match_id] = rec
    save_json("matches.json", store)
    return rec


def ensure_builder_webhooks() -> None:
    """Boot Raja + Nero webhooks if they are not already listening (two builders)."""
    import socket
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    specs = [
        ("Raja", 18761, "gaming.src.stack.agentic.agents.raja.serve"),
        ("Nero", 18762, "gaming.src.stack.agentic.agents.nero.serve"),
    ]
    for name, port, mod in specs:
        try:
            s = socket.socket()
            s.settimeout(0.25)
            s.connect(("127.0.0.1", port))
            s.close()
            continue
        except OSError:
            pass
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        subprocess.Popen(
            [sys.executable, "-m", mod],
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _lock_and_run(match_id: str, move_delay_sec: float, seed: Optional[int]) -> None:
    from gaming.src.stack.agentic.matches import get_match_service

    try:
        get_match_service().lock_both(match_id)
        get_match_service().run_match(
            match_id, move_delay_sec=move_delay_sec, seed=seed
        )
    except Exception:
        logger.exception("[house] rematch %s failed", match_id)
        try:
            cur = get_match_service().get(match_id) or {}
            if cur.get("status") not in {"settle_failed", "lock_failed", "settled", "cancelled"}:
                _set_status(match_id, "error", play_error="rematch failed")
        except Exception:
            pass
    finally:
        with _floor_lock:
            _workers.pop(match_id, None)
        _pump_queue()


def _run_table(match_id: str, move_delay_sec: float, seed: Optional[int]) -> None:
    from gaming.src.stack.agentic.matches import get_match_service

    try:
        get_match_service().run_match(
            match_id, move_delay_sec=move_delay_sec, seed=seed
        )
    except Exception:
        logger.exception("[house] table %s failed", match_id)
        try:
            cur = get_match_service().get(match_id) or {}
            if cur.get("status") not in {"settle_failed", "lock_failed", "settled"}:
                _set_status(match_id, "error", play_error="run_match failed")
        except Exception:
            pass
    finally:
        with _floor_lock:
            _workers.pop(match_id, None)
        _pump_queue()


def _pump_queue() -> None:
    while True:
        with _floor_lock:
            if len(_playing_ids()) >= max_tables():
                return
            nxt = _queued()
            if not nxt:
                return
            mid = nxt[0]["match_id"]
            if mid in _workers:
                return
            delay = float(nxt[0].get("play_delay_sec") or 0)
            seed = nxt[0].get("play_seed")
            try:
                _set_status(mid, "playing")
            except ValueError:
                return
            fut = _executor().submit(_run_table, mid, delay, seed)
            _workers[mid] = fut


class HouseRuntime:
    """Cashier API. Telegram stays human-vs-human; this is the agent venue."""

    def __init__(self) -> None:
        self.house = ensure_house()

    def snapshot(self) -> dict[str, Any]:
        rec = get_registry().get_agent(HOUSE_ID) or self.house
        from gaming.src.stack.agentic.disbursement import public_policy

        return {
            "agent_id": HOUSE_ID,
            "name": rec.get("name") or "Boardman",
            "role": "house",
            "wallet_address": rec.get("wallet_address"),
            "wallet_role": rec.get("wallet_role") or "fee_recipient",
            "identity_contract": rec.get("identity_contract"),
            "escrow_contract": rec.get("escrow_contract"),
            "plays_games": False,
            "can_erc20_transfer": False,
            "human_channel": "telegram_bot_is_human_vs_human",
            "job": "venue: register builder agents, lock stakes, ask each webhook for moves, pay winners via BoardmanEscrow",
            "contestants_are": "builder-hosted webhooks (Raja = creator_raja_lab, Nero = creator_nero_forge)",
            "tables": max_tables(),
            "floor": self.floor(),
            "guardrails": public_policy(),
        }

    def open_match(
        self,
        *,
        agent_a_id: str,
        agent_b_id: str,
        stake_usdc: Optional[float] = None,
        game_id: str = "agentic.chess_standard",
        white_agent_id: Optional[str] = None,
        chain_id: str = "arc",
    ) -> dict[str, Any]:
        if is_house(agent_a_id) or is_house(agent_b_id):
            raise ValueError("Boardman House does not play — pass two contestant agents")
        for aid in (agent_a_id, agent_b_id):
            busy = live_match_for_agent(aid)
            if busy:
                raise ValueError(
                    f"{aid} already live on {busy.get('match_id')} ({busy.get('status')})"
                )
        from gaming.src.stack.agentic.matches import get_match_service

        m = get_match_service().create_match(
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id,
            stake_usdc=stake_usdc,
            white_agent_id=white_agent_id,
            chain_id=chain_id,
            game_id=game_id,
        )
        from gaming.src.stack.agentic.store import load_json, save_json

        store = load_json("matches.json", {"matches": {}})
        rec = store["matches"].get(m["match_id"]) or m
        rec["house_agent_id"] = HOUSE_ID
        rec["clerk"] = "boardman_house"
        store["matches"][m["match_id"]] = rec
        save_json("matches.json", store)
        return rec

    def lock(self, match_id: str) -> dict[str, Any]:
        from gaming.src.stack.agentic.disbursement import authorize_skill_lock
        from gaming.src.stack.agentic.matches import get_match_service

        svc = get_match_service()
        m = svc.get(match_id)
        if not m:
            raise ValueError("match not found")
        authorize_skill_lock(m)
        return svc.lock_both(match_id)

    def take_bet(
        self,
        match_id: str,
        *,
        bettor_id: str,
        side: str,
        amount_usdc: Decimal,
    ) -> dict[str, Any]:
        from gaming.src.stack.agentic.matches import get_match_service
        from gaming.src.stack.agentic.economy.spectator import SpectatorBook

        m = get_match_service().get(match_id)
        if not m:
            raise ValueError("match not found")
        if m.get("status") not in BET_STATUSES:
            raise ValueError(f"match not open for bets: {m.get('status')}")
        if is_house(bettor_id) or (bettor_id or "").lower() in HOUSE_NAMES:
            raise ValueError("Boardman House cannot bet on its own tables")
        slot = resolve_side(m, side)
        book = SpectatorBook().place_bet(
            match_id,
            bettor_id=bettor_id,
            side=slot,
            amount_usdc=Decimal(str(amount_usdc)),
        )
        return {"match_id": match_id, "side": slot, "book": book, "clerk": HOUSE_ID}

    def floor(self) -> dict[str, Any]:
        from gaming.src.stack.agentic.matches import get_match_service

        live = [
            m
            for m in get_match_service().list_matches(200)
            if m.get("status") in LIVE_STATUSES
        ]
        playing = [m for m in live if m.get("status") == "playing"]
        queued = [m for m in live if m.get("status") == "queued"]
        waiting = [m for m in live if m.get("status") in {"open", "locked", "partial_lock"}]
        return {
            "cap": max_tables(),
            "playing": len(playing),
            "queued": len(queued),
            "waiting": len(waiting),
            "open_slots": max(0, max_tables() - len(playing)),
            "tables": [
                {
                    "match_id": m.get("match_id"),
                    "status": m.get("status"),
                    "game_id": m.get("game_id"),
                    "agent_a_id": m.get("agent_a_id"),
                    "agent_b_id": m.get("agent_b_id"),
                    "stake_usdc": m.get("stake_usdc"),
                }
                for m in live
            ],
        }

    def play(
        self,
        match_id: str,
        *,
        move_delay_sec: float = 0.0,
        seed: Optional[int] = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Run a table. wait=False seats it on the 5-table floor (or queues)."""
        from gaming.src.stack.agentic.matches import get_match_service

        if wait:
            return get_match_service().run_match(
                match_id, move_delay_sec=move_delay_sec, seed=seed
            )
        return self.start(match_id, move_delay_sec=move_delay_sec, seed=seed)

    def start(
        self,
        match_id: str,
        *,
        move_delay_sec: float = 0.0,
        seed: Optional[int] = None,
    ) -> dict[str, Any]:
        """Seat a locked match on a table without blocking bets on other tables."""
        from gaming.src.stack.agentic.matches import get_match_service
        from datetime import datetime, timezone

        m = get_match_service().get(match_id)
        if not m:
            raise ValueError("match not found")
        if m.get("status") == "playing":
            return {"match_id": match_id, "status": "playing", "seated": True}
        if m.get("status") not in {"locked", "partial_lock", "open", "queued"}:
            raise ValueError(f"cannot start from status {m.get('status')}")

        extra = {
            "play_delay_sec": move_delay_sec,
            "play_seed": seed,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        with _floor_lock:
            playing = _playing_ids()
            if match_id in _workers or match_id in playing:
                return {"match_id": match_id, "status": "playing", "seated": True}
            if len(playing) >= max_tables():
                rec = _set_status(match_id, "queued", **extra)
                return {
                    "match_id": match_id,
                    "status": "queued",
                    "seated": False,
                    "position": len(_queued()),
                    "cap": max_tables(),
                    "match": rec,
                }
            rec = _set_status(match_id, "playing", **extra)
            fut = _executor().submit(_run_table, match_id, move_delay_sec, seed)
            _workers[match_id] = fut
        return {"match_id": match_id, "status": "playing", "seated": True, "match": rec}

    def abort_never_started(self, match_id: str, *, reason: str = "never_started") -> dict[str, Any]:
        """Refund a lock that never got a game result. Required before the pair can rematch."""
        from gaming.src.stack.agentic import ledger
        from gaming.src.stack.agentic.disbursement import authorize_abort
        from gaming.src.stack.agentic.matches import get_match_service

        svc = get_match_service()
        m = svc.get(match_id)
        if not m:
            raise ValueError("match not found")
        if m.get("status") == "playing":
            raise ValueError("cannot abort a playing table — wait for a result")
        if m.get("result"):
            raise ValueError("match already has a result — settle, do not abort")
        auth = authorize_abort(m, reason=reason)
        onchain_out = None
        if m.get("onchain") or m.get("settlement_mode") == "onchain":
            from gaming.src.stack.agentic.onchain import read_onchain_match, resolve_onchain

            try:
                on = read_onchain_match(match_id, chain_id=m.get("chain_id") or "arc")
            except Exception:
                on = None
            if on and int(on.get("status") or -1) in {0, 1, 2}:
                onchain_out = resolve_onchain(
                    match_id,
                    m.get("agent_a_wallet") or on.get("player1"),
                    chain_id=m.get("chain_id") or "arc",
                    draw=True,
                    authorization=auth,
                )
        try:
            ledger.settle(match_id, m["agent_a_wallet"], result="draw")
        except Exception:
            pass
        rec = _set_status(
            match_id,
            "cancelled",
            abort_reason=reason,
            disbursement=auth.to_dict(),
            onchain_abort=onchain_out,
        )
        return {"match_id": match_id, "status": "cancelled", "reason": reason, "onchain": onchain_out, "match": rec}

    def release_stale_pair(self, agent_a_id: str, agent_b_id: str) -> list[dict[str, Any]]:
        """Cancel leftover locks for this pair that never produced a result."""
        from gaming.src.stack.agentic.matches import get_match_service

        pair = {agent_a_id, agent_b_id}
        out: list[dict[str, Any]] = []
        for m in get_match_service().list_matches(200):
            if m.get("status") not in {
                "open",
                "locked",
                "partial_lock",
                "queued",
                "lock_failed",
                "locking",
            }:
                continue
            if {m.get("agent_a_id"), m.get("agent_b_id")} != pair:
                continue
            if m.get("result"):
                continue
            out.append(self.abort_never_started(m["match_id"], reason="never_started"))
        return out

    def rematch(
        self,
        *,
        agent_a_id: str,
        agent_b_id: str,
        stake_usdc: Optional[float] = None,
        game_id: str = "agentic.chess_standard",
        white_agent_id: Optional[str] = None,
        move_delay_sec: float = 0.05,
        seed: Optional[int] = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Clear stale locks → open → lock → play → settle.

        wait=False returns as soon as the table is opened; lock+play run on a worker
        so the arena can poll live moves.
        """
        ensure_builder_webhooks()
        released = self.release_stale_pair(agent_a_id, agent_b_id)
        m = self.open_match(
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id,
            stake_usdc=stake_usdc,
            game_id=game_id,
            white_agent_id=white_agent_id,
        )
        mid = m["match_id"]
        if wait:
            locked = self.lock(mid)
            played = self.play(mid, move_delay_sec=move_delay_sec, seed=seed, wait=True)
            return {
                "released_stale": [r["match_id"] for r in released],
                "match": played,
                "lock": {
                    "status": locked.get("status"),
                    "settlement_mode": locked.get("settlement_mode"),
                },
            }
        rec = _set_status(
            mid,
            "locking",
            play_delay_sec=move_delay_sec,
            play_seed=seed,
        )
        with _floor_lock:
            fut = _executor().submit(_lock_and_run, mid, move_delay_sec, seed)
            _workers[mid] = fut
        return {
            "released_stale": [r["match_id"] for r in released],
            "match_id": mid,
            "status": "locking",
            "seated": True,
            "match": rec,
        }


def get_house() -> HouseRuntime:
    return HouseRuntime()
