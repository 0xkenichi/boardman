"""Agent match lifecycle: open → dual-lock (on-chain or demo) → play → settle."""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any, Callable, Optional

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db import journal, leases, nonces, transaction
from gaming.src.stack.agentic.db.engine import current_tx, is_retryable
from gaming.src.stack.agentic.db.tables import HOT_SETTLED_MATCHES, MATCHES, hot_matches
from gaming.src.stack.agentic.registry import get_registry

logger = logging.getLogger(__name__)

# Legacy file names (imported by scripts/migrate_json_to_db.py). Matches are
# one database row each; "archived" reads are primary-key lookups.
MATCHES_FILE = "matches.json"
ARCHIVE_FILE = "matches_archive.json"
HOT_SETTLED = HOT_SETTLED_MATCHES


class TableBusy(RuntimeError):
    """A second driver tried to run a match that is already being driven."""


# match_id -> monotonic start time of the thread currently driving the table.
# Guards against double-driving inside this process; the database lease
# (db/leases.py) guards across processes.
_RUNNING: dict[str, float] = {}
_RUNNING_LOCK = threading.Lock()


def _notify_spectator_outcomes(
    match_id: str,
    winner_side: Optional[str],
    pays: list[dict[str, Any]],
    book: Optional[dict[str, Any]] = None,
    result_code: Optional[str] = None,
    termination: Optional[str] = None,
) -> None:
    """Telegram DM *every* public bettor after the book settles.

    No ticket is ever silent: winners get how much they were paid, losers
    get a plain "didn't hit" note (never again the strand-the-pool silence
    on agm_91dadd7c75f5), and draw bets get the draw verdict. Does not
    block the table.
    """
    import threading

    def _run() -> None:
        try:
            import asyncio

            from gaming.src.bot.utils.notify import notify_user

            who = "Raja" if winner_side == "a" else "Nero" if winner_side == "b" else "draw"

            def _end_text() -> str:
                term_map = {
                    "TIMEOUT": "ran out of time",
                    "CHECKMATE": "was checkmated",
                    "RESIGN": "resigned",
                    "STALEMATE": "stalemate",
                    "INSUFFICIENT_MATERIAL": "insufficient material",
                    "THREEFOLD_REPETITION": "threefold repetition",
                    "FIFTY_MOVES": "fifty-move rule",
                }
                why = term_map.get(str(termination or "").upper())
                if winner_side and why:
                    return f"{who} won — the other side {why}."
                return f"Table ended: {who}."

            async def _send() -> None:
                paid_ids: set[str] = set()
                # 1) Winners — how much they were paid.
                for bt in pays:
                    bid = str(bt.get("bettor_id") or "")
                    amt = bt.get("amount") or "0"
                    reason = str(bt.get("reason") or "win")
                    if not bid:
                        continue
                    paid_ids.add(bid)
                    if reason == "refund":
                        text = (
                            f"↩️ <b>Refund ${float(amt):,.2f}</b>\n\n"
                            f"The table was a draw. Your ticket is back on the play wallet.\n"
                            f"<code>{match_id}</code>"
                        )
                    else:
                        text = (
                            f"💰 <b>Paid ${float(amt):,.2f}</b>\n\n"
                            f"{_end_text()}\nSame number on Telegram and the website.\n"
                            f"<code>{match_id}</code>"
                        )
                    await notify_user(bid, text)

                # 2) Everyone else holding a ticket on this table — outcome
                #    note. Includes losers whose side bets didn't hit.
                bets = list((book or {}).get("bets") or [])
                seen: set[str] = set()
                for bt in bets:
                    bid = str(bt.get("bettor_id") or "")
                    if not bid or bid in paid_ids or bid in seen:
                        continue
                    seen.add(bid)
                    side = str(bt.get("side") or "")
                    amount = float(str(bt.get("amount") or "0"))
                    picked = "Raja" if side == "a" else "Nero" if side == "b" else "Draw"
                    end = _end_text()
                    if winner_side and side != winner_side:
                        text = (
                            f"📡 <b>Table settled</b> — {end}\n\n"
                            f"Your ${amount:,.2f} on <b>{picked}</b> didn't hit this time."
                            f"\nNext table seats in about an hour.\n"
                            f"<code>{match_id}</code>"
                        )
                    elif side == "draw":
                        text = (
                            f"📡 <b>Table settled</b> — {end}\n\n"
                            f"Your ${amount:,.2f} on Draw rides the draw pool."
                            f"\n<code>{match_id}</code>"
                        )
                    else:
                        # Drawn table: side bets a/b lose by rulebook.
                        text = (
                            f"📡 <b>Table settled</b> — {end}\n\n"
                            f"Your ${amount:,.2f} on <b>{picked}</b> didn't hit this time."
                            f"\nNext table seats in about an hour.\n"
                            f"<code>{match_id}</code>"
                        )
                    await notify_user(bid, text)

            asyncio.run(_send())
        except Exception:
            logger.warning("[agentic] spectator payout notify failed", exc_info=True)

    threading.Thread(target=_run, name="spec-payout-dm", daemon=True).start()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Statuses from which run_match may start, continue or resume a table.
RUNNABLE_STATUSES = frozenset({"open", "partial_lock", "locked", "playing", "queued", "settling"})
DRAW_RESULT_CODES = frozenset({"draw", "stalemate", "insufficient_material"})
# A table stuck in "settling" is retried at most this many times, then parked
# as settle_failed for a human (each retry skips the steps already journaled).
DEFAULT_MAX_SETTLE_ATTEMPTS = 5

# Test seam: called with the step name right after each settlement step
# commits (the crash-and-retry property test raises from here).
_SETTLE_STEP_HOOK: Optional[Callable[[str], None]] = None


def _after_step(name: str) -> None:
    hook = _SETTLE_STEP_HOOK
    if hook is not None:
        hook(name)


def _max_settle_attempts() -> int:
    try:
        return max(1, int(os.getenv("BOARDMAN_MAX_SETTLE_ATTEMPTS") or DEFAULT_MAX_SETTLE_ATTEMPTS))
    except ValueError:
        return DEFAULT_MAX_SETTLE_ATTEMPTS


def _result_kind(result: dict[str, Any]) -> str:
    return "draw" if result.get("result") in DRAW_RESULT_CODES else "win"


def _result_key(result: dict[str, Any]) -> tuple[str, str]:
    return (str(result.get("result") or ""), str(result.get("winner_agent_id") or ""))


def _onchain_already_final(match_id: str, chain_id: str) -> Optional[dict[str, Any]]:
    """After a crash, the escrow may already be resolved/cancelled on-chain."""
    try:
        from gaming.src.stack.agentic.onchain import ONCHAIN_STATUS, read_onchain_match

        on = read_onchain_match(match_id, chain_id=chain_id)
        st = int(on.get("status") or -1)
        if st in {3, 4}:
            return {"tx_hash": None, "already_final": True, "status": ONCHAIN_STATUS.get(st, str(st))}
    except Exception:
        logger.debug("[agentic] on-chain status probe failed for %s", match_id, exc_info=True)
    return None


def _adjust_already_applied(profile_id: str, reason: str) -> bool:
    """Reconcile a play_adjust payout whose journal row never got written."""
    try:
        from gaming.src.stack.agentic.store import load_json

        rec = (load_json("play_adjust.json", {"profiles": {}}).get("profiles") or {}).get(profile_id) or {}
        return any(str(h.get("reason") or "") == reason[:80] for h in rec.get("history") or [])
    except Exception:
        return False


def freeze_book(match_id: str, *, reason: str, chain_id: str = "arc") -> dict[str, Any]:
    """Ply-N betting freeze: close the demo book, and the SpectatorPool book too.

    The on-chain close() is a resolver tx (up to minutes); it runs on a daemon
    thread so the game loop never waits on it. It is idempotent on-chain, and
    a v2 pool's closeAt deadline is the backstop if it never lands.
    """
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook

    before = SpectatorBook().get(match_id) or {}
    book = SpectatorBook().close_book(match_id, reason=reason)
    just_closed = before.get("status") in {"open", "full"} and book.get("status") == "closed"
    if just_closed and book.get("onchain"):
        _close_book_onchain_async(match_id, chain_id)
    return book


def _close_book_onchain_async(match_id: str, chain_id: str) -> None:
    def _run() -> None:
        try:
            from gaming.src.stack.agentic.spectator_onchain import (
                close_book_onchain,
                spectator_onchain_enabled,
            )

            if spectator_onchain_enabled():
                out = close_book_onchain(match_id, chain_id=chain_id)
                logger.info("[agentic] SpectatorPool close %s tx=%s", match_id, out.get("tx_hash"))
        except Exception:
            logger.warning("[agentic] SpectatorPool close %s failed (closeAt still applies)", match_id, exc_info=True)

    threading.Thread(target=_run, name=f"book-close-{match_id}", daemon=True).start()


def lock_escrow_and_seeds(
    match_id: str, wallet_a: str, wallet_b: str, *, seed_a: Decimal, seed_b: Decimal, seed_draw: Decimal
) -> dict[str, Any]:
    """Both stake locks and the spectator seed debits, as ONE transaction.

    All or nothing, and a retry never debits the seeds twice (journal row).
    """
    with transaction() as tx:
        ledger.hold_wallets(tx, wallet_a, wallet_b)  # same row order at every table
        ledger.lock(match_id, wallet_a)
        esc = ledger.lock(match_id, wallet_b)
        if journal.record(tx, match_id, "lock:seeds", {"a": str(seed_a), "b": str(seed_b), "draw": str(seed_draw)}):
            if seed_a > 0:
                ledger.debit(wallet_a, seed_a, reason="spectator_seed", ref=match_id)
            if seed_b > 0:
                ledger.debit(wallet_b, seed_b, reason="spectator_seed", ref=match_id)
            if seed_draw > 0:
                ledger.debit(wallet_a, seed_draw, reason="draw_seed", ref=match_id)
                ledger.debit(wallet_b, seed_draw, reason="draw_seed", ref=match_id)
    return esc


class AgentMatchService:
    """Match lifecycle over the ``agentic_matches`` table.

    Every write is an atomic read-modify-write of one row (``_update``); no
    method ever saves a copy of the record it read before a slow step.
    """

    def __init__(self) -> None:
        self._mem: dict[str, Any] = {}

    # ── storage ──────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        """Legacy whole-file view (live tables + the newest settled ones)."""
        return MATCHES.snapshot(hot_matches(), "match_id")

    def _save(self, data: dict[str, Any], *, upsert_id: Optional[str] = None) -> None:
        """Write back only what the caller changed in a ``_load()`` snapshot."""
        MATCHES.save_snapshot(data)
        if upsert_id:
            self._log_if_settled(upsert_id)

    @staticmethod
    def _log_if_settled(match_id: str, rec: Optional[dict[str, Any]] = None) -> None:
        try:
            from gaming.src.stack.agentic.tx_log import upsert_match

            rec = rec or MATCHES.get(match_id)
            if rec and rec.get("status") == "settled":
                upsert_match(rec)
        except Exception:
            logger.debug("[agentic] house log upsert failed for %s", match_id, exc_info=True)

    @staticmethod
    def _record(match_id: str) -> Optional[dict[str, Any]]:
        return MATCHES.get(match_id)

    @staticmethod
    def _update(match_id: str, fn: Callable[[dict[str, Any]], Any]) -> Optional[dict[str, Any]]:
        return MATCHES.update(match_id, fn)

    def _set(self, match_id: str, **fields: Any) -> dict[str, Any]:
        def _apply(r: dict[str, Any]) -> None:
            r.update(fields)
            r["updated_at"] = _now()

        rec = self._update(match_id, _apply)
        if rec is None:
            raise ValueError("match not found")
        return rec

    def set_status(self, match_id: str, status: str, **extra: Any) -> dict[str, Any]:
        """Atomic status change that can never rewind a settlement."""

        def _apply(r: dict[str, Any]) -> None:
            cur = str(r.get("status") or "")
            if cur == "settled" and status != "settled":
                raise ValueError(f"match {match_id} is settled; refusing to set {status}")
            if cur == "settling" and status not in {"settling", "settled", "settle_failed"}:
                raise ValueError(f"match {match_id} is settling; refusing to set {status}")
            r["status"] = status
            r["updated_at"] = _now()
            r.update(extra)

        rec = self._update(match_id, _apply)
        if rec is None:
            raise ValueError("match not found")
        return rec

    # ── reads ────────────────────────────────────────────────────────────────

    def list_matches(self, limit: int = 50) -> list[dict[str, Any]]:
        ms = hot_matches()
        ms.sort(key=lambda m: m.get("updated_at") or m.get("created_at") or "", reverse=True)
        slim: list[dict[str, Any]] = []
        for m in ms[:limit]:
            rec = {
                k: m.get(k)
                for k in (
                    "match_id",
                    "status",
                    "game_id",
                    "agent_a_id",
                    "agent_b_id",
                    "white_agent_id",
                    "black_agent_id",
                    "stake_usdc",
                    "result",
                    "winner_agent_id",
                    "created_at",
                    "updated_at",
                    "settled_at",
                    "locked_at",
                    "bet_window_ends_at",
                    "ply",
                )
            }
            rec["spectator_book"] = {
                "status": (m.get("spectator_book") or {}).get("status"),
                "totals": (m.get("spectator_book") or {}).get("totals"),
            }
            slim.append(rec)
        return slim

    def get(self, match_id: str) -> Optional[dict[str, Any]]:
        """Indexed lookup — live or long-settled, no archive file to parse."""
        m = self._record(match_id)
        if m:
            self._overlay_live_book(m)
        return m

    @staticmethod
    def _overlay_live_book(m: dict[str, Any]) -> None:
        """Serve live spectator totals, not the open-time snapshot."""
        mid = str(m.get("match_id") or "")
        if not mid:
            return
        try:
            from gaming.src.stack.agentic.economy.spectator import SpectatorBook

            live = SpectatorBook().get(mid)
        except Exception:
            return
        if not live:
            return
        snap = dict(m.get("spectator_book") or {})
        snap["totals"] = live.get("totals") or snap.get("totals")
        snap["status"] = live.get("status") or snap.get("status")
        if live.get("pot_cap_usdc") is not None:
            snap["pot_cap_usdc"] = live.get("pot_cap_usdc")
        snap["bets"] = live.get("bets") or snap.get("bets") or []
        if live.get("payouts") is not None:
            snap["payouts"] = live.get("payouts")
        if live.get("odds_live") is not None:
            snap["odds_live"] = live.get("odds_live")
        if live.get("closed_reason"):
            snap["closed_reason"] = live.get("closed_reason")
        m["spectator_book"] = snap

    def persist_spectator_snapshot(self, match_id: str, book: dict[str, Any]) -> None:
        def _apply(rec: dict[str, Any]) -> None:
            rec["spectator_book"] = {
                "match_id": match_id,
                "totals": book.get("totals"),
                "status": book.get("status"),
                "pot_cap_usdc": book.get("pot_cap_usdc"),
                "bets": book.get("bets") or [],
                "payouts": book.get("payouts"),
                "odds_live": book.get("odds_live"),
                "closed_reason": book.get("closed_reason"),
            }
            rec["updated_at"] = _now()

        self._update(match_id, _apply)

    def _record_live_odds(self, rec: dict[str, Any], eval_pawns: Optional[float]) -> None:
        from gaming.src.stack.agentic.economy.odds import build_market
        from gaming.src.stack.agentic.economy.spectator import SpectatorBook

        mid = rec.get("match_id") or ""
        book = SpectatorBook().get(mid) or rec.get("spectator_book") or {}
        totals = book.get("totals") or {}
        eco = rec.get("economy") or {}
        snap = build_market(
            match_id=mid,
            agent_a={"agent_id": rec.get("agent_a_id"), "name": "Raja"},
            agent_b={"agent_id": rec.get("agent_b_id"), "name": "Nero"},
            pot_a=Decimal(str(totals.get("a") or "0")),
            pot_b=Decimal(str(totals.get("b") or "0")),
            seed_a=Decimal(str(eco.get("spectator_seed_a") or book.get("seed_a") or "0")),
            seed_b=Decimal(str(eco.get("spectator_seed_b") or book.get("seed_b") or "0")),
            eval_pawns=eval_pawns if eval_pawns is not None else rec.get("last_eval"),
            a_is_white=rec.get("white_agent_id") == rec.get("agent_a_id"),
            ply=int(rec.get("ply") or len(rec.get("moves") or [])),
        )
        SpectatorBook().record_odds(mid, snap.to_dict())
        rec["odds_live"] = snap.to_dict()

    # ── create / lock ────────────────────────────────────────────────────────

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
        from gaming.src.stack.agentic.economy.spectator import (
            SpectatorBook,
            betting_open_for_new_books,
        )
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

        # Spectator-betting kill switch: no seeding, and the book never opens.
        book_closed_reason = ""
        if not betting_open_for_new_books():
            seed_a = seed_b = seed_draw = Decimal("0")
            book_closed_reason = "betting_disabled"
            negotiation = {**negotiation, "spectator_seeds": "off (spectator betting disabled)"}

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
            closed_reason=book_closed_reason,
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
        stored, _ = MATCHES.insert_if_absent(match_id, rec)
        return stored

    def lock_both(self, match_id: str) -> dict[str, Any]:
        from gaming.src.stack.agentic.onchain import dual_lock_onchain, onchain_enabled
        from gaming.src.stack.agentic.disbursement import (
            DisbursementDenied,
            allow_ledger_fallback,
            authorize_skill_lock,
        )

        m = self._record(match_id)
        if not m:
            raise ValueError("match not found")
        existing = ledger.get_escrow(match_id)
        if existing and existing.get("status") == "locked":

            def _mark_locked(r: dict[str, Any]) -> None:
                r["escrow"] = existing
                if r.get("status") in {"open", "partial_lock", "queued"}:
                    r["status"] = "locked"
                    r["updated_at"] = _now()

            return self._update(match_id, _mark_locked) or m
        authorize_skill_lock(m)

        # Fields to apply to the *current* row at the end. On-chain calls below
        # take up to minutes; nothing read before them is ever saved back whole.
        changes: dict[str, Any] = {}
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
                changes["onchain"] = onchain_result
                changes["settlement_mode"] = "onchain"
                p1 = onchain_result.get("player1")
                p2 = onchain_result.get("player2")
                if p1 and p2:
                    changes["onchain_player1"] = p1
                    changes["onchain_player2"] = p2
                    if white_is_a:
                        changes["agent_a_wallet"] = p1
                        changes["agent_b_wallet"] = p2
                    else:
                        changes["agent_a_wallet"] = p2
                        changes["agent_b_wallet"] = p1
                logger.info(
                    "[agentic] on-chain dual-lock ok match=%s create=%s join=%s",
                    match_id,
                    onchain_result.get("create_tx_hash"),
                    onchain_result.get("join_tx_hash"),
                )
            except Exception as exc:
                logger.exception("[agentic] on-chain lock failed: %s", exc)
                if isinstance(exc, nonces.TxPendingConfirmation):
                    # The lock tx may still mine; record it so ops/abort can
                    # reconcile against the escrow instead of guessing.
                    changes["onchain_pending_tx"] = {"label": exc.label, "tx_hash": exc.tx_hash}
                if not allow_ledger_fallback():
                    self._set(match_id, onchain_error=str(exc), status="lock_failed", **changes)
                    raise DisbursementDenied(
                        f"on-chain lock failed and ledger fallback is off: {exc}"
                    ) from exc
                changes["onchain_error"] = str(exc)
                changes["settlement_mode"] = "demo_ledger_fallback"
                onchain_result = None
        m.update(changes)

        # Mirror lock in demo ledger (always) for balances UI. Both locks and
        # the spectator seed debits are ONE transaction: all or nothing, and a
        # retry never debits the seeds twice.
        eco = m.get("economy") or {}
        seed_a = Decimal(str(eco.get("spectator_seed_a") or "0"))
        seed_b = Decimal(str(eco.get("spectator_seed_b") or "0"))
        seed_draw = Decimal(str(eco.get("spectator_seed_draw") or "0"))
        esc = lock_escrow_and_seeds(
            match_id, m["agent_a_wallet"], m["agent_b_wallet"],
            seed_a=seed_a, seed_b=seed_b, seed_draw=seed_draw,
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

        book_snap: Optional[dict[str, Any]] = None
        try:
            from gaming.src.stack.agentic.spectator_onchain import (
                open_book_onchain,
                spectator_onchain_enabled,
            )
            from gaming.src.stack.agentic.economy.spectator import SpectatorBook

            live_book = SpectatorBook().get(match_id) or {}
            if spectator_onchain_enabled() and live_book.get("closed_reason") != "betting_disabled":
                opened = open_book_onchain(m, chain_id=m.get("chain_id") or "arc")
                SpectatorBook().mark_onchain(
                    match_id,
                    pool=str(opened.get("pool") or ""),
                    open_tx_hash=str(opened.get("tx_hash") or ""),
                )
                changes["spectator_pool"] = {
                    "pool": opened.get("pool"),
                    "open_tx_hash": opened.get("tx_hash"),
                    "explorer": opened.get("explorer"),
                    "already_open": opened.get("already_open"),
                }
                book_snap = {
                    "onchain": True,
                    "pool": opened.get("pool"),
                    "open_tx_hash": opened.get("tx_hash"),
                }
        except Exception as exc:
            logger.warning("[agentic] SpectatorPool openBook: %s", exc)
            changes["spectator_pool_error"] = str(exc)

        def _finish(r: dict[str, Any]) -> None:
            r.update(changes)
            if book_snap:
                snap = dict(r.get("spectator_book") or {})
                snap.update(book_snap)
                r["spectator_book"] = snap
            r["escrow"] = esc
            # Only move forward from a pre-lock status; a table cancelled or
            # started meanwhile keeps its newer status.
            if r.get("status") in {"open", "partial_lock", "queued", "locking", "locked"}:
                r["status"] = "locked" if esc.get("status") == "locked" else "partial_lock"
                if r["status"] == "locked" and not r.get("locked_at"):
                    r["locked_at"] = _now()
            r["updated_at"] = _now()

        rec = self._update(match_id, _finish)
        if rec is None:
            raise ValueError("match not found")
        return rec

    # ── settlement ───────────────────────────────────────────────────────────

    def _step(self, match_id: str, name: str, fn: Callable[[], Any]) -> Any:
        """Run a money step exactly once.

        The journal row and every ledger/book/pool change the step makes commit
        in ONE transaction, under a fresh check that this process still holds
        the match lease. A retry finds the row and reuses its recorded detail.
        """
        attempt = 0
        while True:
            try:
                with transaction() as tx:
                    leases.assert_held(tx, match_id)
                    row = journal.get(tx, match_id, name)
                    if row is not None:
                        return row["detail"]
                    out = fn()
                    journal.record(tx, match_id, name, out, owner=leases.process_owner())
                break
            except Exception as exc:
                # A step credits several wallets; two settlements sharing
                # bettors can deadlock on Postgres, which rolls one back
                # whole. Nothing of it committed, so run it again.
                attempt += 1
                if attempt > 3 or current_tx() is not None or not is_retryable(exc):
                    raise
                logger.warning("[agentic] %s step %s rolled back (%s); retry %d", match_id, name, exc, attempt)
                time.sleep(0.05 * attempt)
        _after_step(name)
        return out

    def _external_step(self, match_id: str, name: str, fn: Callable[[], Any]) -> Any:
        """A step that leaves the database (chain, registry file, Telegram).

        Journaled right after it returns; ``fn`` must itself be safe to repeat
        (it is re-run only if the process died between the call and the row).
        """
        if journal.done(match_id, name):
            with transaction(readonly=True) as tx:
                row = journal.get(tx, match_id, name)
            return (row or {}).get("detail")
        out = fn()
        with transaction() as tx:
            leases.assert_held(tx, match_id)
            journal.record(tx, match_id, name, out, owner=leases.process_owner())
        _after_step(name)
        return out

    def _players(self, m: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
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
        return white, black

    def settle_result(self, match_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """Settle a match from a terminal result (resume / ops), under its lease."""
        m = self._record(match_id)
        if not m:
            raise ValueError("match not found")
        white, black = self._players(m)
        try:
            with leases.hold(match_id):
                return self._finish_settlement(match_id, result, white, black)
        except leases.LeaseBusy as exc:
            raise TableBusy(str(exc)) from exc

    def _finish_settlement(
        self, match_id: str, result: dict[str, Any], white: dict, black: dict
    ) -> dict[str, Any]:
        """Claim the match for settlement, run the journaled steps, mark settled."""
        outcome: dict[str, Any] = {}
        max_attempts = _max_settle_attempts()

        def _claim(r: dict[str, Any]) -> Any:
            st = str(r.get("status") or "")
            if st == "settled":
                outcome["settled"] = True
                return False
            if st == "settling":
                prev = r.get("pending_result") or {}
                if prev and _result_key(prev) != _result_key(result) and result:
                    outcome["conflict"] = prev
                    return False
                r["settle_attempts"] = int(r.get("settle_attempts") or 0) + 1
                if r["settle_attempts"] > max_attempts:
                    r["status"] = "settle_failed"
                    r["settle_error"] = f"settlement retried {max_attempts}x — needs ops"
                    outcome["parked"] = True
                if not prev:
                    r["pending_result"] = result
            else:
                prev = r.get("pending_result") or {}
                if prev and result and _result_key(prev) != _result_key(result):
                    # e.g. a settle_failed table retried with another result.
                    outcome["conflict"] = prev
                    return False
                # The first transfer happens only after this commits.
                r["status"] = "settling"
                r["pending_result"] = result
                r["settle_attempts"] = 1
                r["settling_since"] = _now()
            r["updated_at"] = _now()
            return None

        rec = self._update(match_id, _claim)
        if rec is None:
            logger.error("[agentic] match %s vanished before settle", match_id)
            return {"match_id": match_id, "status": "error", "play_error": "match missing after play"}
        if outcome.get("settled"):
            prev_esc = rec.get("escrow") or {}
            prev_result = str(prev_esc.get("result") or "")
            if prev_result and result and prev_result != _result_kind(result):
                logger.error(
                    "[agentic] settle conflict %s: already settled as %s, refusing %s",
                    match_id, prev_result, _result_kind(result),
                )
                raise RuntimeError(
                    f"match {match_id} already settled ({prev_result}); conflicting re-settle refused"
                )
            logger.warning("[agentic] settle %s: already settled, no-op", match_id)
            return rec
        if outcome.get("conflict"):
            raise RuntimeError(
                f"match {match_id} is settling with a different result; conflicting re-settle refused"
            )
        if outcome.get("parked"):
            raise RuntimeError(f"match {match_id}: settlement attempts exhausted — parked as settle_failed")

        _after_step("settling")
        res = rec.get("pending_result") or result
        if not res:
            raise RuntimeError(f"match {match_id} is settling with no recorded result")
        updates: dict[str, Any] = {}
        esc = self._settle(match_id, rec, res, white, black, updates=updates)

        game_id = rec.get("game_id") or "agentic.chess_standard"

        def _finalize() -> dict[str, Any]:
            def _apply(m: dict[str, Any]) -> None:
                m.update(updates)
                m["status"] = "settled"
                m["result"] = res["result"]
                m["winner_agent_id"] = res.get("winner_agent_id")
                m["termination"] = res.get("termination")
                m["pgn"] = res.get("pgn")
                m["moves"] = res.get("moves")
                m["final_fen"] = res.get("final_fen")
                m["final_state"] = res.get("final_state")
                m["seed"] = res.get("seed")
                m["time_control_id"] = res.get("time_control_id") or m.get("time_control_id")
                m["clock"] = res.get("clock")
                m["escrow"] = esc
                m["settled_at"] = _now()
                m["updated_at"] = _now()
                m["play"] = {
                    "result_pgn": res.get("result_pgn"),
                    "plies": res.get("plies"),
                    "started_at": res.get("started_at"),
                    "ended_at": res.get("ended_at"),
                    "engines": res.get("engines"),
                    "time_control_id": res.get("time_control_id"),
                    "game_id": game_id,
                }
                m.pop("pending_result", None)

            done = self._update(match_id, _apply) or {}
            return {"settled_at": done.get("settled_at")}

        self._step(match_id, "finalize", _finalize)
        final = self._record(match_id) or rec
        self._log_if_settled(match_id, final)
        return final

    def _settle(
        self,
        match_id: str,
        m: dict[str, Any],
        result: dict[str, Any],
        white: dict,
        black: dict,
        *,
        updates: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Move the money, one journaled step at a time.

        Steps: onchain_resolve → escrow → stats → creator_fee → lp_profit →
        lp_loss → opening_stats → spectator_resolve_onchain → spectator_settle
        → play_adjust:<i> → notify. Each money step commits with its journal
        row; a retry after a crash skips completed steps, so nothing is paid
        twice and nothing is skipped.
        """
        if updates is None:
            updates = {}
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
            self._set(
                match_id,
                status="settle_failed",
                settle_error="disbursement denied — result is not a contract trigger",
            )
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

        updates["disbursement"] = auth.to_dict()

        fee_split = FeeRouter().split_skill_pot(
            stake_usdc=Decimal(str(m["stake_usdc"])),
            winner_agent=winner,
            loser_agent=loser,
            draw=draw,
        )
        updates["fee_split"] = fee_split.to_dict()

        chain = m.get("chain_id") or "arc"
        onchain_settle = None
        onchain_needed = require_onchain_settlement(m) or (
            onchain_enabled() and m.get("onchain") and not m.get("onchain_error")
        )
        if onchain_needed:

            def _resolve() -> dict[str, Any]:
                if int(m.get("settle_attempts") or 1) > 1:
                    # A previous attempt may have resolved it (or left the tx
                    # pending): never send a second resolve for a final escrow.
                    final = _onchain_already_final(match_id, chain)
                    if final is not None:
                        return final
                try:
                    return resolve_onchain(
                        match_id,
                        white["wallet_address"] if draw else auth.winner_wallet,
                        chain_id=chain,
                        draw=draw,
                        authorization=auth,
                    )
                except Exception:
                    # A retry after a crash may find the escrow already final.
                    final = _onchain_already_final(match_id, chain)
                    if final is not None:
                        return final
                    raise

            try:
                onchain_settle = self._external_step(match_id, "onchain_resolve", _resolve)
                updates["onchain_settle"] = onchain_settle
                logger.info(
                    "[agentic] on-chain settle ok match=%s tx=%s",
                    match_id,
                    (onchain_settle or {}).get("tx_hash"),
                )
            except nonces.TxPendingConfirmation:
                # Broadcast but unconfirmed: NOT a failure. Stay "settling";
                # the retry probes the escrow before sending anything again.
                logger.warning("[agentic] on-chain settle %s pending confirmation — will retry", match_id)
                raise
            except Exception as exc:
                logger.exception("[agentic] on-chain settle failed: %s", exc)
                updates["onchain_settle_error"] = str(exc)
                if not allow_ledger_fallback():
                    self._set(match_id, status="settle_failed", **updates)
                    raise DisbursementDenied(
                        f"on-chain settle failed and ledger fallback is off: {exc}"
                    ) from exc

        from gaming.src.stack.agentic.economy.lp import AgentLPPool
        from gaming.src.stack.agentic.economy.budget import budget_from_manifest

        lp = AgentLPPool()
        eco = m.get("economy") or {}

        if draw:
            esc = self._step(
                match_id, "escrow", lambda: ledger.settle(match_id, white["wallet_address"], result="draw")
            )

            def _stats_draw() -> dict[str, Any]:
                reg.update_stats(white["agent_id"], "draw")
                reg.update_stats(black["agent_id"], "draw")
                return {"draw": [white["agent_id"], black["agent_id"]]}

            self._external_step(match_id, "stats", _stats_draw)
            winner_side = None
        else:
            assert winner is not None and loser is not None
            # Pay full winner_gross to agent, then debit creator fee (no mint inflation)
            esc = self._step(
                match_id, "escrow", lambda: ledger.settle(match_id, winner["wallet_address"], result="win")
            )

            def _stats_win() -> dict[str, Any]:
                reg.update_stats(winner["agent_id"], "win")
                reg.update_stats(loser["agent_id"], "loss")
                return {"win": winner["agent_id"], "loss": loser["agent_id"]}

            self._external_step(match_id, "stats", _stats_win)
            c_fee = Decimal(fee_split.creator_fee)
            if c_fee > 0:
                creator_wallet = f"creator:{(winner.get('creator_id') or winner.get('owner_id'))}"

                def _creator_fee() -> dict[str, Any]:
                    try:
                        ledger.debit(
                            winner["wallet_address"],
                            c_fee,
                            reason="creator_fee_skill_out",
                            ref=match_id,
                        )
                    except ValueError as exc:
                        # Never credit a fee nobody paid (that would mint USDC).
                        logger.warning("[agentic] creator fee debit failed: %s", exc)
                        return {"skipped": str(exc)}
                    ledger.credit(creator_wallet, c_fee, reason="creator_fee_skill", ref=match_id)
                    return {"amount": str(c_fee), "creator_wallet": creator_wallet}

                fee_out = self._step(match_id, "creator_fee", _creator_fee) or {}
                if not fee_out.get("skipped"):
                    self._external_step(
                        match_id,
                        "creator_fee_registry",
                        lambda: (reg.credit_creator_fee(winner["agent_id"], str(c_fee)), {"amount": str(c_fee)})[1],
                    )

            # Net skill profit that stayed on agent after creator cut = owner_payout - stake
            owner_payout = Decimal(fee_split.owner_payout)
            stake = Decimal(str(m["stake_usdc"]))
            net_profit = owner_payout - stake
            if net_profit > 0:
                bud_w = budget_from_manifest(winner)
                lp_share_bps = int(
                    eco.get(f"lp_profit_share_bps_{'a' if winner['agent_id'] == m['agent_a_id'] else 'b'}")
                    or bud_w.lp_profit_share_bps
                )

                def _lp_profit() -> dict[str, Any]:
                    dist = lp.distribute_skill_profit(
                        winner["agent_id"],
                        net_profit_usdc=net_profit,
                        lp_profit_share_bps=lp_share_bps,
                    )
                    # Credit LP pseudo-wallets for realized profit share (claim already compounded in pool)
                    for p in dist.get("lp_payouts") or []:
                        ledger.credit(
                            f"lp:{p['lp_id']}",
                            Decimal(str(p["amount"])),
                            reason="lp_skill_profit",
                            ref=match_id,
                        )
                    return dist

                updates["lp_distribution"] = self._step(match_id, "lp_profit", _lp_profit)

            # Loser: mark LP haircut on lost stake
            def _lp_loss() -> dict[str, Any]:
                br_before = ledger.balance(loser["wallet_address"]) + stake
                out = dict(lp.mark_loss(loser["agent_id"], loss_usdc=stake, agent_bankroll_before=br_before))
                out.pop("pool", None)
                return out

            self._step(match_id, "lp_loss", _lp_loss)
            winner_side = "a" if winner["agent_id"] == m["agent_a_id"] else "b"

        # Opening-line learning — remember which repertoire line produced this
        # result so the next book pick weights it (and rotates openers).
        def _opening() -> dict[str, Any]:
            try:
                from gaming.src.stack.agentic.chess import opening_stats

                opening_stats.record_result(
                    agent_a_id=str(m.get("agent_a_id") or ""),
                    agent_b_id=str(m.get("agent_b_id") or ""),
                    sans=[str(mv.get("san")) for mv in (result.get("moves") or m.get("moves") or []) if mv.get("san")],
                    winner_side=winner_side,
                    match_id=match_id,
                )
                return {"ok": True}
            except Exception as exc:
                logger.warning("[agentic] opening stats record failed: %s", exc)
                return {"ok": False, "error": str(exc)}

        self._external_step(match_id, "opening_stats", _opening)

        # Spectator pot settle
        try:
            from gaming.src.stack.agentic.spectator_onchain import (
                resolve_book as resolve_spectator_pool,
                spectator_onchain_enabled,
            )

            spec_book = SpectatorBook()
            live = spec_book.get(match_id) or {}
            if not live:
                # Self-heal: a lost book must not block settlement — recreate
                # it from the match economy fields.
                try:
                    live = spec_book.ensure_from_match(m)
                    logger.warning("[agentic] spectator book recreated for %s", match_id)
                except Exception as exc:
                    logger.warning("[agentic] spectator book recreate failed %s: %s", match_id, exc)
            onchain_spec = bool(live.get("onchain")) and spectator_onchain_enabled()
            if onchain_spec:
                try:
                    resolved = self._external_step(
                        match_id,
                        "spectator_resolve_onchain",
                        lambda: resolve_spectator_pool(match_id, winner_side, chain_id=chain),
                    ) or {}
                    if resolved.get("tx_hash"):
                        spec_book.project_resolve(
                            match_id,
                            tx_hash=str(resolved.get("tx_hash") or ""),
                            explorer=str(resolved.get("explorer") or ""),
                        )
                    updates["spectator_pool_resolve"] = resolved
                except leases.LeaseLost:
                    raise
                except Exception as exc:
                    logger.warning("[agentic] SpectatorPool resolve: %s", exc)
                    updates["spectator_pool_resolve_error"] = str(exc)

            def _spectator_settle() -> dict[str, Any]:
                spec = (
                    spec_book.settle(match_id, winner_side=winner_side)
                    if live
                    else {
                        "status": "missing",
                        "totals": {},
                        "payouts": {},
                        "onchain": False,
                        "pool": "",
                        "open_tx_hash": "",
                        "resolve_tx_hash": "",
                    }
                )
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
                fan_pays = list((spec.get("payouts") or {}).get("bettors") or [])
                for bt in fan_pays:
                    bid = str(bt.get("bettor_id") or "")
                    amt = Decimal(str(bt.get("amount") or "0"))
                    if not bid or amt <= 0:
                        continue
                    ledger.credit(bid, amt, reason=f"spectator_{bt.get('reason') or 'win'}", ref=match_id)
                return {
                    "book": {
                        "status": spec.get("status"),
                        "totals": spec.get("totals"),
                        "payouts": spec.get("payouts"),
                        "onchain": bool(spec.get("onchain")),
                        "pool": spec.get("pool"),
                        "open_tx_hash": spec.get("open_tx_hash"),
                        "resolve_tx_hash": spec.get("resolve_tx_hash"),
                    },
                    "fan_pays": fan_pays,
                    "bets": list(spec.get("bets") or []),
                }

            spec_out = self._step(match_id, "spectator_settle", _spectator_settle) or {}
            updates["spectator_book"] = spec_out.get("book") or {}
            fan_pays = list(spec_out.get("fan_pays") or [])
            for i, bt in enumerate(fan_pays):
                bid = str(bt.get("bettor_id") or "")
                amt = Decimal(str(bt.get("amount") or "0"))
                if not bid or amt <= 0:
                    continue
                tag = f"payout:{match_id}:{bt.get('reason') or 'win'}#{i}"

                def _adjust(bid: str = bid, amt: Decimal = amt, tag: str = tag) -> dict[str, Any]:
                    if _adjust_already_applied(bid, tag):
                        return {"reconciled": True}
                    from gaming.src.backend.services.play_adjust import add_adjust

                    add_adjust(bid, amt, reason=tag)
                    return {"applied": str(amt)}

                try:
                    self._external_step(match_id, f"play_adjust:{i}", _adjust)
                except leases.LeaseLost:
                    raise
                except Exception:
                    logger.warning("[agentic] play_adjust payout failed %s", bid, exc_info=True)

            def _notify() -> dict[str, Any]:
                _notify_spectator_outcomes(
                    match_id,
                    winner_side,
                    fan_pays,
                    book={**(spec_out.get("book") or {}), "bets": spec_out.get("bets") or []},
                    result_code=str(result.get("result") or ""),
                    termination=str(result.get("termination") or ""),
                )
                return {"sent": len(fan_pays)}

            self._external_step(match_id, "notify", _notify)
        except leases.LeaseLost:
            raise
        except Exception as exc:
            logger.warning("[agentic] spectator settle: %s", exc)

        if onchain_settle:
            esc = dict(esc)
            esc["mode"] = "onchain"
            esc["onchain_settle"] = onchain_settle
        esc = dict(esc)
        esc["fee_split"] = fee_split.to_dict()
        m.update(updates)
        return esc

    # ── play ─────────────────────────────────────────────────────────────────

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
        """Lock if needed, play any registered game, settle escrow + fees + spectator.

        Runs under the match lease: a table another process is driving raises
        TableBusy; a table whose driver died (expired lease) is taken over, and
        a table that died mid-settlement resumes from its journal.
        """
        m = self._record(match_id)
        if not m:
            raise ValueError("match not found")
        if m["status"] not in RUNNABLE_STATUSES:
            raise ValueError(f"cannot play from status {m['status']}")

        with _RUNNING_LOCK:
            if match_id in _RUNNING:
                raise TableBusy(
                    f"match {match_id} is already being driven by another worker"
                )
            _RUNNING[match_id] = time.monotonic()
        try:
            with ExitStack() as stack:
                try:
                    stack.enter_context(leases.hold(match_id))
                except leases.LeaseBusy as exc:
                    raise TableBusy(str(exc)) from exc
                return self._run_match_inner(
                    match_id, move_delay_sec=move_delay_sec, seed=seed, on_move=on_move
                )
        finally:
            with _RUNNING_LOCK:
                _RUNNING.pop(match_id, None)

    def _run_match_inner(
        self,
        match_id: str,
        *,
        move_delay_sec: float = 0.25,
        seed: Optional[int] = None,
        on_move=None,
    ) -> dict[str, Any]:
        # Fresh read: the game state may have moved while we waited.
        m = self._record(match_id)
        if not m:
            raise ValueError("match not found")
        if m["status"] == "settling":
            white, black = self._players(m)
            logger.warning("[agentic] resuming settlement of %s from its journal", match_id)
            return self._finish_settlement(match_id, m.get("pending_result") or {}, white, black)
        if m["status"] in {"open", "partial_lock", "queued"}:
            m = self.lock_both(match_id)

        white, black = self._players(m)

        def _start(r: dict[str, Any]) -> None:
            st = str(r.get("status") or "")
            if st not in RUNNABLE_STATUSES or st == "settling":
                raise ValueError(f"cannot play from status {st}")
            r["status"] = "playing"
            r["updated_at"] = _now()

        m = self._update(match_id, _start) or m

        game_id = m.get("game_id") or "agentic.chess_standard"
        chain = m.get("chain_id") or "arc"

        def _persist_live(ev) -> None:
            payload = ev.__dict__ if hasattr(ev, "__dict__") else dict(ev)
            flags: dict[str, Any] = {}

            def _apply(rec: dict[str, Any]) -> Any:
                moves = list(rec.get("moves") or [])
                ply = payload.get("ply")
                if ply is not None and any(x.get("ply") == ply for x in moves):
                    flags["dup"] = True
                    return False
                clk = payload.get("clock") or {}
                ev_eval = payload.get("eval_pawns")
                moves.append(
                    {
                        "ply": ply,
                        "san": payload.get("san"),
                        "uci": payload.get("uci"),
                        "fen": payload.get("fen"),
                        "side": payload.get("side"),
                        "agent_id": payload.get("agent_id"),
                        "source": payload.get("engine_source"),
                        "eval_pawns": ev_eval,
                        "clock": clk or None,
                    }
                )
                rec["moves"] = moves
                if rec.get("status") in {"locked", "playing", "partial_lock", "queued"}:
                    rec["status"] = "playing"
                rec["updated_at"] = _now()
                rec["ply"] = ply
                if ev_eval is not None:
                    rec["last_eval"] = ev_eval
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
                try:
                    from gaming.src.stack.agentic.economy.spectator import (
                        SpectatorBook,
                        book_close_plies,
                    )

                    close_at = book_close_plies()
                    if ply is not None and int(ply) >= close_at:
                        before = (SpectatorBook().get(match_id) or {}).get("status")
                        book = SpectatorBook().close_book(match_id, reason=f"ply_{ply}")
                        snap_b = dict(rec.get("spectator_book") or {})
                        snap_b["status"] = book.get("status")
                        snap_b["closed_reason"] = book.get("closed_reason")
                        rec["spectator_book"] = snap_b
                        if before in {"open", "full"} and book.get("onchain"):
                            flags["close_onchain"] = True
                    if ev_eval is not None or (ply and int(ply) % 2 == 0):
                        self._record_live_odds(rec, ev_eval)
                except Exception:
                    logger.warning("[agentic] live book/odds update failed", exc_info=True)
                return None

            self._update(match_id, _apply)
            if flags.get("dup"):
                return
            if flags.get("close_onchain"):
                # Ply-N freeze on the SpectatorPool too (after our commit).
                _close_book_onchain_async(match_id, chain)
            if on_move:
                on_move(ev)

        if game_id == "agentic.chess_standard":
            from gaming.src.stack.agentic.chess.arena import play_match

            prior = list(m.get("moves") or [])
            result = play_match(
                white_agent=white,
                black_agent=black,
                move_delay_sec=move_delay_sec,
                seed=seed,
                time_control_id=m.get("time_control_id"),
                use_agent_think_delay=move_delay_sec <= 0.05,
                on_move=_persist_live,
                prior_moves=prior,
                clock_snap=m.get("clock"),
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

        return self._finish_settlement(match_id, result, white, black)

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
