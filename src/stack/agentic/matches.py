"""Agent match lifecycle: open → dual-lock (on-chain or demo) → play → settle."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.registry import get_registry
from gaming.src.stack.agentic.store import load_json, save_json

logger = logging.getLogger(__name__)

MATCHES_FILE = "matches.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentMatchService:
    def _load(self) -> dict[str, Any]:
        return load_json(MATCHES_FILE, {"matches": {}})

    def _save(self, data: dict[str, Any]) -> None:
        save_json(MATCHES_FILE, data)
        # Do not write sqlite on every live ply — that wedged metrics.
        try:
            from gaming.src.stack.agentic.tx_log import upsert_match

            for rec in (data.get("matches") or {}).values():
                if rec.get("status") != "settled":
                    continue
                upsert_match(rec)
        except Exception:
            pass

    def list_matches(self, limit: int = 50) -> list[dict[str, Any]]:
        ms = list(self._load()["matches"].values())
        ms.sort(key=lambda m: m.get("created_at") or "", reverse=True)
        return ms[:limit]

    def get(self, match_id: str) -> Optional[dict[str, Any]]:
        return self._load()["matches"].get(match_id)

    def create_match(
        self,
        *,
        agent_a_id: str,
        agent_b_id: str,
        stake_usdc: Optional[float] = None,
        chain_id: str = "arc",
        white_agent_id: Optional[str] = None,
        game_id: str = "agentic.chess_standard",
        auto_negotiate: bool = True,
    ) -> dict[str, Any]:
        from gaming.src.stack.agentic.onchain import match_id_hex, onchain_enabled

        reg = get_registry()
        a = reg.get_agent(agent_a_id)
        b = reg.get_agent(agent_b_id)
        if not a or not b:
            raise ValueError("both agents must be registered")
        if agent_a_id == agent_b_id:
            raise ValueError("agents must be different")
        if a.get("role") == "house" or b.get("role") == "house":
            raise ValueError("Boardman House clerks matches — it cannot play")
        from gaming.src.stack.agentic.house import live_match_for_agent

        for aid, label in ((agent_a_id, "A"), (agent_b_id, "B")):
            busy = live_match_for_agent(aid)
            if busy:
                raise ValueError(
                    f"agent {label} ({aid}) already live on {busy.get('match_id')}"
                )
        if not a.get("wallet_address") or not b.get("wallet_address"):
            raise ValueError("both agents must have wallet_address bound to play")

        from gaming.src.stack.agentic.games.catalog import get_game_meta

        if game_id != "agentic.chess_standard" and not get_game_meta(game_id):
            raise ValueError(f"unknown game_id: {game_id}")
        for ag, label in ((a, "A"), (b, "B")):
            gids = list(ag.get("game_ids") or [])
            if "*" not in gids and game_id not in gids:
                raise ValueError(
                    f"agent {label} ({ag.get('agent_id')}) does not play {game_id} "
                    "— the builder has not shipped that game yet"
                )

        match_id = f"agm_{uuid.uuid4().hex[:12]}"
        # white_agent_id == p1 (first mover) for all games
        white_id = white_agent_id or agent_a_id
        black_id = agent_b_id if white_id == agent_a_id else agent_a_id
        if white_id not in {agent_a_id, agent_b_id}:
            raise ValueError("white_agent_id must be one of the two agents")

        from gaming.src.stack.agentic.clock import negotiate_time_control
        from gaming.src.stack.agentic.economy.budget import (
            budget_from_manifest,
            negotiate_match_stake,
        )
        from gaming.src.stack.agentic.economy.spectator import SpectatorBook
        from gaming.src.stack.agentic.chess.personas import get_persona

        # Enrich from silo personas
        for ag in (a, b):
            p = get_persona(ag["agent_id"])
            if p:
                ag.setdefault("economy", p.get("economy"))
                ag.setdefault("creator_id", p.get("creator_id"))
                ag.setdefault("creator_fee_bps", p.get("creator_fee_bps"))
                ag.setdefault("preferred_time_controls", p.get("preferred_time_controls"))

        bud_a = budget_from_manifest(a)
        bud_b = budget_from_manifest(b)

        # Live bankroll: prefer real Arc USDC on the agent's wallet_address;
        # fall back to demo ledger; then manifest bankroll.
        def _play_balance(agent: dict[str, Any], bud) -> Decimal:
            w = agent.get("wallet_address") or ""
            if onchain_enabled() and w:
                try:
                    from gaming.src.stack.agentic.onchain import usdc_balance

                    on_bal = usdc_balance(w, chain_id=chain_id)
                    if on_bal > 0:
                        return on_bal
                except Exception as exc:
                    logger.warning(
                        "[agentic] on-chain balance read failed for %s: %s", w[:12], exc
                    )
            lb = ledger.balance(w) if w else Decimal("0")
            if lb > 0:
                return lb
            return Decimal(str(bud.bankroll_usdc))

        br_a = _play_balance(a, bud_a)
        br_b = _play_balance(b, bud_b)

        requested = Decimal(str(stake_usdc)) if stake_usdc is not None else None
        if auto_negotiate or requested is None:
            neg = negotiate_match_stake(
                bud_a, bud_b, br_a, br_b, requested=requested
            )
            if not neg.ok:
                raise ValueError(f"stake negotiation failed: {neg.reason}")
            stake = Decimal(neg.stake_usdc)
            seed_a = Decimal(neg.seed_a)
            seed_b = Decimal(neg.seed_b)
            seed_draw = Decimal(getattr(neg, "draw_seed", "0") or "0")
            negotiation = neg.to_dict()
        else:
            stake = Decimal(str(stake_usdc))
            ok_a, why_a = bud_a.can_stake(stake, br_a)
            ok_b, why_b = bud_b.can_stake(stake, br_b)
            if not ok_a:
                raise ValueError(f"agent A cannot stake: {why_a}")
            if not ok_b:
                raise ValueError(f"agent B cannot stake: {why_b}")
            seed_a = bud_a.spectator_seed_for_stake(stake)
            seed_b = bud_b.spectator_seed_for_stake(stake)
            seed_draw = min(bud_a.draw_seed_for_stake(stake), bud_b.draw_seed_for_stake(stake))
            negotiation = {
                "stake_usdc": str(stake),
                "seed_a": str(seed_a),
                "seed_b": str(seed_b),
                "draw_seed": str(seed_draw),
                "binding": "request",
                "ok": True,
                "reason": "manual stake (auto_negotiate=false)",
            }

        tc = negotiate_time_control(
            list(a.get("preferred_time_controls") or bud_a.preferred_time_controls),
            list(b.get("preferred_time_controls") or bud_b.preferred_time_controls),
        )

        # Demo ledger: fund to at least policy bankroll so unequal agents work
        ledger.ensure_funded(a["wallet_address"], Decimal(str(bud_a.bankroll_usdc)))
        ledger.ensure_funded(b["wallet_address"], Decimal(str(bud_b.bankroll_usdc)))
        esc = ledger.open_escrow(
            match_id,
            agent_a_wallet=a["wallet_address"],
            agent_b_wallet=b["wallet_address"],
            stake_usdc=stake,
            chain_id=chain_id,
        )

        # Pot cap scales with matched stake (richer mutual stake → juicier market)
        pot_cap = max(Decimal("5"), stake * 4)
        book = SpectatorBook().open_book(
            match_id,
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id,
            seed_a=seed_a,
            seed_b=seed_b,
            seed_draw=seed_draw,
            creator_a_id=str(a.get("creator_id") or a.get("owner_id") or ""),
            creator_b_id=str(b.get("creator_id") or b.get("owner_id") or ""),
            pot_cap_usdc=pot_cap,
            agent_a_wallet=a["wallet_address"],
            agent_b_wallet=b["wallet_address"],
        )

        rec = {
            "match_id": match_id,
            "match_id_bytes32": match_id_hex(match_id),
            "game_id": game_id,
            "status": "open",
            "settlement_mode": "onchain" if onchain_enabled() else "demo_ledger",
            "chain_id": chain_id,
            "stake_usdc": str(stake),
            "time_control_id": tc,
            "agent_a_id": agent_a_id,
            "agent_b_id": agent_b_id,
            "white_agent_id": white_id,
            "black_agent_id": black_id,
            "agent_a_wallet": a["wallet_address"],
            "agent_b_wallet": b["wallet_address"],
            "agent_a_contract": a["identity_contract"],
            "agent_b_contract": b["identity_contract"],
            "creator_a_id": a.get("creator_id") or a.get("owner_id"),
            "creator_b_id": b.get("creator_id") or b.get("owner_id"),
            "economy": {
                "creator_fee_bps_a": a.get("creator_fee_bps") or bud_a.creator_fee_bps,
                "creator_fee_bps_b": b.get("creator_fee_bps") or bud_b.creator_fee_bps,
                "spectator_seed_a": str(seed_a),
                "spectator_seed_b": str(seed_b),
                "spectator_seed_draw": str(seed_draw),
                "negotiation": negotiation,
                "pot_cap_usdc": str(pot_cap),
                "lp_profit_share_bps_a": bud_a.lp_profit_share_bps,
                "lp_profit_share_bps_b": bud_b.lp_profit_share_bps,
            },
            "spectator_book": {
                "match_id": match_id,
                "totals": book.get("totals"),
                "status": book.get("status"),
                "pot_cap_usdc": book.get("pot_cap_usdc"),
            },
            "escrow": esc,
            "onchain": None,
            "onchain_player1": None,
            "onchain_player2": None,
            "house_agent_id": "agent_boardman_house",
            "clerk": "boardman_house",
            "fee_split": None,
            "result": None,
            "winner_agent_id": None,
            "pgn": None,
            "moves": [],
            "created_at": _now(),
            "updated_at": _now(),
            "locked_at": None,
            "settled_at": None,
        }
        data = self._load()
        data["matches"][match_id] = rec
        self._save(data)
        return rec

    def lock_both(self, match_id: str) -> dict[str, Any]:
        from gaming.src.stack.agentic.onchain import dual_lock_onchain, onchain_enabled
        from gaming.src.stack.agentic.disbursement import (
            DisbursementDenied,
            allow_ledger_fallback,
            authorize_skill_lock,
        )

        data = self._load()
        m = data["matches"].get(match_id)
        if not m:
            raise ValueError("match not found")
        existing = ledger.get_escrow(match_id)
        if existing and existing.get("status") == "locked":
            m["escrow"] = existing
            if m.get("status") in {"open", "partial_lock", "queued"}:
                m["status"] = "locked"
                m["updated_at"] = _now()
                data["matches"][match_id] = m
                self._save(data)
            return m
        authorize_skill_lock(m)

        onchain_result = None
        if onchain_enabled():
            try:
                # White locks first as player1 (createMatch), black joins
                white_is_a = m["white_agent_id"] == m["agent_a_id"]
                onchain_result = dual_lock_onchain(
                    match_id,
                    agent_a_id=m["agent_a_id"],
                    agent_b_id=m["agent_b_id"],
                    agent_a_wallet=m["agent_a_wallet"],
                    agent_b_wallet=m["agent_b_wallet"],
                    stake_usdc=Decimal(str(m["stake_usdc"])),
                    chain_id=m.get("chain_id") or "arc",
                    player1_is_a=white_is_a,
                )
                m["onchain"] = onchain_result
                m["settlement_mode"] = "onchain"
                p1 = onchain_result.get("player1")
                p2 = onchain_result.get("player2")
                if p1 and p2:
                    m["onchain_player1"] = p1
                    m["onchain_player2"] = p2
                    if white_is_a:
                        m["agent_a_wallet"] = p1
                        m["agent_b_wallet"] = p2
                    else:
                        m["agent_a_wallet"] = p2
                        m["agent_b_wallet"] = p1
                logger.info(
                    "[agentic] on-chain dual-lock ok match=%s create=%s join=%s",
                    match_id,
                    onchain_result.get("create_tx_hash"),
                    onchain_result.get("join_tx_hash"),
                )
            except Exception as exc:
                logger.exception("[agentic] on-chain lock failed: %s", exc)
                m["onchain_error"] = str(exc)
                if not allow_ledger_fallback():
                    m["status"] = "lock_failed"
                    m["updated_at"] = _now()
                    data["matches"][match_id] = m
                    self._save(data)
                    raise DisbursementDenied(
                        f"on-chain lock failed and ledger fallback is off: {exc}"
                    ) from exc
                m["settlement_mode"] = "demo_ledger_fallback"
                onchain_result = None

        # Mirror lock in demo ledger (always) for balances UI
        esc = ledger.lock(match_id, m["agent_a_wallet"])
        esc = ledger.lock(match_id, m["agent_b_wallet"])
        # Debit spectator seeds from agent bankrolls into pot holding (not skill escrow)
        eco = m.get("economy") or {}
        seed_a = Decimal(str(eco.get("spectator_seed_a") or "0"))
        seed_b = Decimal(str(eco.get("spectator_seed_b") or "0"))
        seed_draw = Decimal(str(eco.get("spectator_seed_draw") or "0"))
        if seed_a > 0:
            ledger.debit(
                m["agent_a_wallet"],
                seed_a,
                reason="spectator_seed",
                ref=match_id,
            )
        if seed_b > 0:
            ledger.debit(
                m["agent_b_wallet"],
                seed_b,
                reason="spectator_seed",
                ref=match_id,
            )
        if seed_draw > 0:
            ledger.debit(
                m["agent_a_wallet"],
                seed_draw,
                reason="draw_seed",
                ref=match_id,
            )
            ledger.debit(
                m["agent_b_wallet"],
                seed_draw,
                reason="draw_seed",
                ref=match_id,
            )
        if onchain_result:
            esc = dict(esc)
            esc["mode"] = "onchain"
            esc["onchain"] = {
                "match_id_bytes32": onchain_result.get("match_id_bytes32"),
                "escrow": onchain_result.get("escrow"),
                "create_tx_hash": onchain_result.get("create_tx_hash"),
                "join_tx_hash": onchain_result.get("join_tx_hash"),
                "explorer_create": onchain_result.get("explorer_create"),
                "explorer_join": onchain_result.get("explorer_join"),
                "txs": onchain_result.get("txs"),
            }

        try:
            from gaming.src.stack.agentic.spectator_onchain import (
                open_book_onchain,
                spectator_onchain_enabled,
            )
            from gaming.src.stack.agentic.economy.spectator import SpectatorBook

            if spectator_onchain_enabled():
                opened = open_book_onchain(m, chain_id=m.get("chain_id") or "arc")
                SpectatorBook().mark_onchain(
                    match_id,
                    pool=str(opened.get("pool") or ""),
                    open_tx_hash=str(opened.get("tx_hash") or ""),
                )
                m["spectator_pool"] = {
                    "pool": opened.get("pool"),
                    "open_tx_hash": opened.get("tx_hash"),
                    "explorer": opened.get("explorer"),
                    "already_open": opened.get("already_open"),
                }
                snap = dict(m.get("spectator_book") or {})
                snap["onchain"] = True
                snap["pool"] = opened.get("pool")
                snap["open_tx_hash"] = opened.get("tx_hash")
                m["spectator_book"] = snap
        except Exception as exc:
            logger.warning("[agentic] SpectatorPool openBook: %s", exc)
            m["spectator_pool_error"] = str(exc)

        m["escrow"] = esc
        m["status"] = "locked" if esc.get("status") == "locked" else "partial_lock"
        if m["status"] == "locked":
            m["locked_at"] = _now()
        m["updated_at"] = _now()
        data["matches"][match_id] = m
        self._save(data)
        return m

    def _settle(self, match_id: str, m: dict[str, Any], result: dict[str, Any], white: dict, black: dict) -> dict[str, Any]:
        from gaming.src.stack.agentic.onchain import onchain_enabled, resolve_onchain
        from gaming.src.stack.agentic.economy.fees import FeeRouter
        from gaming.src.stack.agentic.economy.spectator import SpectatorBook
        from gaming.src.stack.agentic.chess.personas import get_persona
        from gaming.src.stack.agentic.disbursement import (
            DisbursementDenied,
            allow_ledger_fallback,
            authorize_skill_settlement,
            require_onchain_settlement,
        )

        reg = get_registry()
        # Attach economy from silo if missing
        for ag in (white, black):
            p = get_persona(ag["agent_id"])
            if p:
                ag.setdefault("creator_id", p.get("creator_id"))
                ag.setdefault("creator_fee_bps", p.get("creator_fee_bps"))
                ag.setdefault("economy", p.get("economy"))

        try:
            auth = authorize_skill_settlement(m, result, white=white, black=black)
        except DisbursementDenied:
            m["status"] = "settle_failed"
            m["settle_error"] = "disbursement denied — result is not a contract trigger"
            m["updated_at"] = _now()
            data = self._load()
            data["matches"][match_id] = m
            self._save(data)
            raise

        draw = auth.action == "cancel"
        winner = loser = None
        if not draw:
            winner_id = result.get("winner_agent_id") or (
                white["agent_id"]
                if auth.winner_wallet
                and auth.winner_wallet.lower()
                == (white.get("wallet_address") or "").lower()
                else None
            )
            if not winner_id:
                rcode = str(result.get("result") or "")
                if rcode in {"white_win", "p1_win"}:
                    winner_id = white["agent_id"]
                elif rcode in {"black_win", "p2_win"}:
                    winner_id = black["agent_id"]
            if winner_id == white["agent_id"]:
                winner, loser = white, black
            elif winner_id == black["agent_id"]:
                winner, loser = black, white
            else:
                raise DisbursementDenied("authorized win but winner agent is missing")
            # Pay the authorized (on-chain) wallet, not a stale registry copy.
            winner = {**winner, "wallet_address": auth.winner_wallet}

        m["disbursement"] = auth.to_dict()

        fee_split = FeeRouter().split_skill_pot(
            stake_usdc=Decimal(str(m["stake_usdc"])),
            winner_agent=winner,
            loser_agent=loser,
            draw=draw,
        )
        m["fee_split"] = fee_split.to_dict()

        onchain_settle = None
        onchain_needed = require_onchain_settlement(m) or (
            onchain_enabled() and m.get("onchain") and not m.get("onchain_error")
        )
        if onchain_needed:
            try:
                if draw:
                    onchain_settle = resolve_onchain(
                        match_id,
                        white["wallet_address"],
                        chain_id=m.get("chain_id") or "arc",
                        draw=True,
                        authorization=auth,
                    )
                else:
                    onchain_settle = resolve_onchain(
                        match_id,
                        auth.winner_wallet,
                        chain_id=m.get("chain_id") or "arc",
                        draw=False,
                        authorization=auth,
                    )
                m["onchain_settle"] = onchain_settle
                logger.info(
                    "[agentic] on-chain settle ok match=%s tx=%s",
                    match_id,
                    onchain_settle.get("tx_hash"),
                )
            except Exception as exc:
                logger.exception("[agentic] on-chain settle failed: %s", exc)
                m["onchain_settle_error"] = str(exc)
                if not allow_ledger_fallback():
                    m["status"] = "settle_failed"
                    m["updated_at"] = _now()
                    data = self._load()
                    data["matches"][match_id] = m
                    self._save(data)
                    raise DisbursementDenied(
                        f"on-chain settle failed and ledger fallback is off: {exc}"
                    ) from exc

        from gaming.src.stack.agentic.economy.lp import AgentLPPool
        from gaming.src.stack.agentic.economy.budget import budget_from_manifest

        lp = AgentLPPool()
        eco = m.get("economy") or {}

        if draw:
            esc = ledger.settle(match_id, white["wallet_address"], result="draw")
            reg.update_stats(white["agent_id"], "draw")
            reg.update_stats(black["agent_id"], "draw")
            winner_side = None
        else:
            # Pay full winner_gross to agent, then debit creator fee (no mint inflation)
            esc = ledger.settle(match_id, winner["wallet_address"], result="win")
            reg.update_stats(winner["agent_id"], "win")
            reg.update_stats(loser["agent_id"], "loss")
            c_fee = Decimal(fee_split.creator_fee)
            if c_fee > 0:
                try:
                    ledger.debit(
                        winner["wallet_address"],
                        c_fee,
                        reason="creator_fee_skill_out",
                        ref=match_id,
                    )
                except ValueError as exc:
                    logger.warning("[agentic] creator fee debit failed: %s", exc)
                creator_wallet = f"creator:{(winner.get('creator_id') or winner.get('owner_id'))}"
                ledger.credit(
                    creator_wallet,
                    c_fee,
                    reason="creator_fee_skill",
                    ref=match_id,
                )
                reg.credit_creator_fee(winner["agent_id"], str(c_fee))

            # Net skill profit that stayed on agent after creator cut = owner_payout - stake
            # (they put in stake, got owner_payout back; profit = owner_payout - stake)
            owner_payout = Decimal(fee_split.owner_payout)
            stake = Decimal(str(m["stake_usdc"]))
            net_profit = owner_payout - stake
            if net_profit > 0:
                bud_w = budget_from_manifest(winner)
                lp_share_bps = int(
                    eco.get(f"lp_profit_share_bps_{'a' if winner['agent_id'] == m['agent_a_id'] else 'b'}")
                    or bud_w.lp_profit_share_bps
                )
                dist = lp.distribute_skill_profit(
                    winner["agent_id"],
                    net_profit_usdc=net_profit,
                    lp_profit_share_bps=lp_share_bps,
                )
                m["lp_distribution"] = dist
                # Credit LP pseudo-wallets for realized profit share (claim already compounded in pool)
                for p in dist.get("lp_payouts") or []:
                    ledger.credit(
                        f"lp:{p['lp_id']}",
                        Decimal(str(p["amount"])),
                        reason="lp_skill_profit",
                        ref=match_id,
                    )
            # Loser: mark LP haircut on lost stake
            if loser:
                br_before = ledger.balance(loser["wallet_address"]) + stake
                lp.mark_loss(
                    loser["agent_id"],
                    loss_usdc=stake,
                    agent_bankroll_before=br_before,
                )
            winner_side = "a" if winner["agent_id"] == m["agent_a_id"] else "b"

        # Spectator pot settle
        try:
            from gaming.src.stack.agentic.spectator_onchain import (
                resolve_book as resolve_spectator_pool,
                spectator_onchain_enabled,
            )

            spec_book = SpectatorBook()
            live = spec_book.get(match_id) or {}
            onchain_spec = bool(live.get("onchain")) and spectator_onchain_enabled()
            if onchain_spec:
                try:
                    resolved = resolve_spectator_pool(
                        match_id,
                        winner_side,
                        chain_id=m.get("chain_id") or "arc",
                    )
                    if resolved.get("tx_hash"):
                        spec_book.project_resolve(
                            match_id,
                            tx_hash=str(resolved.get("tx_hash") or ""),
                            explorer=str(resolved.get("explorer") or ""),
                        )
                    m["spectator_pool_resolve"] = resolved
                except Exception as exc:
                    logger.warning("[agentic] SpectatorPool resolve: %s", exc)
                    m["spectator_pool_resolve_error"] = str(exc)
            spec = spec_book.settle(match_id, winner_side=winner_side)
            m["spectator_book"] = {
                "status": spec.get("status"),
                "totals": spec.get("totals"),
                "payouts": spec.get("payouts"),
                "onchain": bool(spec.get("onchain")),
                "pool": spec.get("pool"),
                "open_tx_hash": spec.get("open_tx_hash"),
                "resolve_tx_hash": spec.get("resolve_tx_hash"),
            }
            # On-chain books push creator fees in the contract. Ledger only
            # refunds JSON seeds (those were never deposited to the pool).
            if not onchain_spec:
                for c in (spec.get("payouts") or {}).get("creators") or []:
                    ledger.credit(
                        f"creator:{c['creator_id']}",
                        Decimal(str(c["amount"])),
                        reason="creator_fee_spectator",
                        ref=match_id,
                    )
            for sr in (spec.get("payouts") or {}).get("seed_refunds") or []:
                w = sr.get("wallet")
                amt = Decimal(str(sr.get("amount") or "0"))
                if w and amt > 0:
                    ledger.credit(w, amt, reason=str(sr.get("reason") or "seed_refund_draw"), ref=match_id)
            draw_book = (spec.get("payouts") or {}).get("draw_book") or {}
            for sp in draw_book.get("agent_split") or []:
                w = sp.get("wallet")
                amt = Decimal(str(sp.get("amount") or "0"))
                if w and amt > 0:
                    ledger.credit(w, amt, reason="draw_underwrite_win", ref=match_id)
            for bt in draw_book.get("bettors") or []:
                bid = bt.get("bettor_id")
                amt = Decimal(str(bt.get("amount") or "0"))
                if bid and amt > 0:
                    ledger.credit(str(bid), amt, reason="draw_win", ref=match_id)
        except Exception as exc:
            logger.warning("[agentic] spectator settle: %s", exc)

        if onchain_settle:
            esc = dict(esc)
            esc["mode"] = "onchain"
            esc["onchain_settle"] = onchain_settle
        esc = dict(esc)
        esc["fee_split"] = fee_split.to_dict()
        return esc

    def run_chess(
        self,
        match_id: str,
        *,
        move_delay_sec: float = 0.25,
        seed: Optional[int] = None,
        on_move=None,
    ) -> dict[str, Any]:
        """Back-compat alias."""
        return self.run_match(
            match_id, move_delay_sec=move_delay_sec, seed=seed, on_move=on_move
        )

    def run_match(
        self,
        match_id: str,
        *,
        move_delay_sec: float = 0.25,
        seed: Optional[int] = None,
        on_move=None,
    ) -> dict[str, Any]:
        """Lock if needed, play any registered game, settle escrow + fees + spectator."""
        data = self._load()
        m = data["matches"].get(match_id)
        if not m:
            raise ValueError("match not found")
        if m["status"] not in {"open", "partial_lock", "locked", "playing", "queued"}:
            raise ValueError(f"cannot play from status {m['status']}")

        if m["status"] in {"open", "partial_lock", "queued"}:
            m = self.lock_both(match_id)

        reg = get_registry()
        # p1 = white_agent_id (first mover)
        white = reg.get_agent(m["white_agent_id"])
        black = reg.get_agent(m["black_agent_id"])
        if not white or not black:
            raise ValueError("agents missing")

        from gaming.src.stack.agentic.chess.personas import get_persona

        for agent in (white, black):
            p = get_persona(agent["agent_id"])
            if p:
                agent["mind"] = p["mind"]
                agent.setdefault("name", p.get("name"))
                agent.setdefault("economy", p.get("economy"))
                agent.setdefault("preferred_time_controls", p.get("preferred_time_controls"))
                agent.setdefault("creator_id", p.get("creator_id"))
                agent.setdefault("creator_fee_bps", p.get("creator_fee_bps"))

        m["status"] = "playing"
        m["updated_at"] = _now()
        data = self._load()
        data["matches"][match_id] = m
        self._save(data)

        game_id = m.get("game_id") or "agentic.chess_standard"

        def _persist_live(ev) -> None:
            payload = ev.__dict__ if hasattr(ev, "__dict__") else dict(ev)
            live = self._load()
            rec = live["matches"].get(match_id)
            if not rec:
                return
            moves = list(rec.get("moves") or [])
            clk = payload.get("clock") or {}
            moves.append(
                {
                    "ply": payload.get("ply"),
                    "san": payload.get("san"),
                    "uci": payload.get("uci"),
                    "fen": payload.get("fen"),
                    "side": payload.get("side"),
                    "agent_id": payload.get("agent_id"),
                    "source": payload.get("engine_source"),
                    "clock": clk or None,
                }
            )
            rec["moves"] = moves
            rec["status"] = "playing"
            rec["updated_at"] = _now()
            if clk:
                snap = dict(rec.get("clock") or {})
                snap["control_id"] = rec.get("time_control_id") or snap.get("control_id")
                side = clk.get("side") or payload.get("side")
                if side in {"white", "black"}:
                    snap[side] = {
                        "remaining_ms": clk.get("remaining_ms"),
                        "flag": bool(clk.get("flag")),
                    }
                rec["clock"] = snap
            live["matches"][match_id] = rec
            self._save(live)
            if on_move:
                on_move(ev)

        if game_id == "agentic.chess_standard":
            from gaming.src.stack.agentic.chess.arena import play_match

            result = play_match(
                white_agent=white,
                black_agent=black,
                move_delay_sec=move_delay_sec,
                seed=seed,
                time_control_id=m.get("time_control_id"),
                use_agent_think_delay=move_delay_sec <= 0.05,
                on_move=_persist_live,
            )
        else:
            from gaming.src.stack.agentic.games.runner import play_generic_match

            result = play_generic_match(
                game_id=game_id,
                p1_agent=white,
                p2_agent=black,
                move_delay_sec=move_delay_sec,
                seed=seed,
                on_move=on_move,
            )
            # map p1/p2 → white/black keys for settle
            if result.get("result") == "p1_win":
                result["result"] = "white_win"
            elif result.get("result") == "p2_win":
                result["result"] = "black_win"

        data = self._load()
        m = data["matches"][match_id]
        esc = self._settle(match_id, m, result, white, black)

        m["status"] = "settled"
        m["result"] = result["result"]
        m["winner_agent_id"] = result.get("winner_agent_id")
        m["termination"] = result.get("termination")
        m["pgn"] = result.get("pgn")
        m["moves"] = result.get("moves")
        m["final_fen"] = result.get("final_fen")
        m["final_state"] = result.get("final_state")
        m["seed"] = result.get("seed")
        m["time_control_id"] = result.get("time_control_id") or m.get("time_control_id")
        m["clock"] = result.get("clock")
        m["escrow"] = esc
        m["fee_split"] = m.get("fee_split")
        m["settled_at"] = _now()
        m["updated_at"] = _now()
        m["play"] = {
            "result_pgn": result.get("result_pgn"),
            "plies": result.get("plies"),
            "started_at": result.get("started_at"),
            "ended_at": result.get("ended_at"),
            "engines": result.get("engines"),
            "time_control_id": result.get("time_control_id"),
            "game_id": game_id,
        }
        data["matches"][match_id] = m
        self._save(data)
        return m

    def demo_raja_vs_nero(
        self,
        *,
        stake_usdc: float = 5.0,
        white: str = "raja",
        move_delay_sec: float = 0.2,
        seed: Optional[int] = None,
        on_move=None,
    ) -> dict[str, Any]:
        reg = get_registry()
        agents = reg.ensure_demo_agents()
        by_name = {a["name"].lower(): a for a in agents}
        by_id = {a["agent_id"]: a for a in agents}
        raja = by_name.get("raja") or by_id["agent_raja_kia_alekhine"]
        nero = by_name.get("nero") or by_id["agent_nero_sicilian_french"]

        from gaming.src.stack.agentic.chess.personas import get_persona

        for a in (raja, nero):
            p = get_persona(a["agent_id"])
            if p:
                a["mind"] = p["mind"]

        if white.lower() == "nero":
            white_id, a_id, b_id = nero["agent_id"], nero["agent_id"], raja["agent_id"]
        else:
            white_id, a_id, b_id = raja["agent_id"], raja["agent_id"], nero["agent_id"]

        m = self.create_match(
            agent_a_id=a_id,
            agent_b_id=b_id,
            stake_usdc=stake_usdc,
            white_agent_id=white_id,
            game_id="agentic.chess_standard",
        )
        return self.run_match(
            m["match_id"], move_delay_sec=move_delay_sec, seed=seed, on_move=on_move
        )

    def demo_game(
        self,
        *,
        game_id: str = "agentic.connect4",
        stake_usdc: float = 5.0,
        p1: str = "raja",
        move_delay_sec: float = 0.05,
        seed: Optional[int] = None,
        on_move=None,
    ) -> dict[str, Any]:
        """Quick demo for any catalog game with Raja vs Nero."""
        reg = get_registry()
        agents = reg.ensure_demo_agents()
        by_name = {a["name"].lower(): a for a in agents}
        raja = by_name["raja"]
        nero = by_name["nero"]
        if p1.lower() == "nero":
            a_id, b_id, white_id = nero["agent_id"], raja["agent_id"], nero["agent_id"]
        else:
            a_id, b_id, white_id = raja["agent_id"], nero["agent_id"], raja["agent_id"]
        m = self.create_match(
            agent_a_id=a_id,
            agent_b_id=b_id,
            stake_usdc=stake_usdc,
            white_agent_id=white_id,
            game_id=game_id,
        )
        return self.run_match(
            m["match_id"], move_delay_sec=move_delay_sec, seed=seed, on_move=on_move
        )


@lru_cache(maxsize=1)
def get_match_service() -> AgentMatchService:
    return AgentMatchService()
