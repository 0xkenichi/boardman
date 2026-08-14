"""
Spectator pot keyed by match_id — separate from skill escrow.

People watch Raja vs Nero (or any agent match) and stake USDC on a side.
Agent deploy policy can auto-seed a fraction of each side's stake into the pot
(creator "puts skin" so the market has juice).

Settlement:
  pot = seeds + all spectator bets
  platform takes spectator_fee_bps
  creators of BOTH agents split creator_spectator_bps of pot (or of fee)
  remainder goes pro-rata to bettors who picked the winning agent
  draw side-book → refund A/B bets + side seeds
  draw book (separate): both agents seed the same $; fans bet "draw"
    decisive game → agents split public draw bets 50/50 and get seeds back
    actual draw → draw bettors take public draw + both agent seeds

Demo ledger only (same file store as agentic). On-chain pools later.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json, save_json

BOOK_FILE = "spectator_books.json"
DEFAULT_SPECTATOR_FEE_BPS = 300  # 3% platform
DEFAULT_CREATOR_SPECTATOR_BPS = 200  # 2% of pot split across both creators
# 12 full moves = 24 plies. Mid-game book freeze after the opening.
DEFAULT_BOOK_CLOSE_PLIES = 24


def book_close_plies() -> int:
    """Ply count after which new spectator bets are refused."""
    try:
        n = int(os.getenv("BOARDMAN_BOOK_CLOSE_PLIES") or str(DEFAULT_BOOK_CLOSE_PLIES))
    except ValueError:
        n = DEFAULT_BOOK_CLOSE_PLIES
    return max(4, min(n, 200))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _bps(amount: Decimal, bps: int) -> Decimal:
    return (amount * Decimal(int(bps)) / Decimal(10_000)).quantize(Decimal("0.000001"))


class SpectatorBook:
    def _load(self) -> dict[str, Any]:
        return load_json(BOOK_FILE, {"books": {}})

    def _save(self, data: dict[str, Any]) -> None:
        save_json(BOOK_FILE, data)

    def open_book(
        self,
        match_id: str,
        *,
        agent_a_id: str,
        agent_b_id: str,
        seed_a: Decimal = Decimal("0"),
        seed_b: Decimal = Decimal("0"),
        seed_draw: Decimal = Decimal("0"),
        creator_a_id: str = "",
        creator_b_id: str = "",
        pot_cap_usdc: Optional[Decimal] = None,
        agent_a_wallet: str = "",
        agent_b_wallet: str = "",
    ) -> dict[str, Any]:
        data = self._load()
        if match_id in data["books"]:
            return data["books"][match_id]
        # Default cap: seeds * 20, min $5 — keeps payout sustainable vs agent liquidity
        seeds = seed_a + seed_b
        cap = pot_cap_usdc
        if cap is None:
            cap = max(Decimal("5"), seeds * 20) if seeds > 0 else Decimal("20")
        rec = {
            "match_id": match_id,
            "status": "open",
            "agent_a_id": agent_a_id,
            "agent_b_id": agent_b_id,
            "creator_a_id": creator_a_id,
            "creator_b_id": creator_b_id,
            "agent_a_wallet": agent_a_wallet,
            "agent_b_wallet": agent_b_wallet,
            "seed_a": str(seed_a),
            "seed_b": str(seed_b),
            "seed_draw": str(seed_draw),
            "pot_cap_usdc": str(cap),
            "draw_cap_usdc": str(max(Decimal("5"), seed_draw * 40) if seed_draw > 0 else Decimal("20")),
            "bets": [],  # {bettor_id, side: a|b|draw, amount, ts}
            "totals": {"a": str(seed_a), "b": str(seed_b), "draw": "0"},
            "odds_history": [],  # snapshots from economy.odds
            "onchain": False,
            "pool": "",
            "open_tx_hash": "",
            "resolve_tx_hash": "",
            "created_at": _now(),
            "settled_at": None,
            "payouts": None,
        }
        data["books"][match_id] = rec
        self._save(data)
        return rec

    def place_bet(
        self,
        match_id: str,
        *,
        bettor_id: str,
        side: str,
        amount_usdc: Decimal,
    ) -> dict[str, Any]:
        side = side.lower()
        if side in {"d", "tie"}:
            side = "draw"
        if side not in {"a", "b", "draw"}:
            raise ValueError("side must be a, b, or draw")
        if amount_usdc <= 0:
            raise ValueError("amount must be positive")
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if book.get("onchain") and side != "draw":
            raise ValueError("on-chain book — use project_deposit after a confirmed tx")
        if book["status"] != "open":
            raise ValueError(f"book not open: {book['status']}")
        book.setdefault("totals", {})
        book["totals"].setdefault("draw", "0")
        if side == "draw":
            pot = _d(book["totals"].get("draw") or "0")
            cap = _d(book.get("draw_cap_usdc") or "0")
        else:
            pot = _d(book["totals"].get("a") or "0") + _d(book["totals"].get("b") or "0")
            cap = _d(book.get("pot_cap_usdc") or "0")
        if cap > 0 and pot + amount_usdc > cap + Decimal("0.000001"):
            room = cap - pot
            if room <= 0:
                if side != "draw":
                    book["status"] = "full"
                    data["books"][match_id] = book
                    self._save(data)
                raise ValueError("pot full — no more bets")
            raise ValueError(f"bet exceeds pot room ${room}")
        book["bets"].append(
            {
                "bettor_id": bettor_id,
                "side": side,
                "amount": str(amount_usdc),
                "ts": _now(),
            }
        )
        tot = _d(book["totals"].get(side, "0")) + amount_usdc
        book["totals"][side] = str(tot)
        new_pot = _d(book["totals"]["a"]) + _d(book["totals"]["b"])
        if cap > 0 and new_pot >= cap - Decimal("0.000001"):
            book["status"] = "full"
        data["books"][match_id] = book
        self._save(data)
        return book

    def mark_onchain(
        self,
        match_id: str,
        *,
        pool: str = "",
        open_tx_hash: str = "",
    ) -> dict[str, Any]:
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        book["onchain"] = True
        if pool:
            book["pool"] = pool
        if open_tx_hash:
            book["open_tx_hash"] = open_tx_hash
        data["books"][match_id] = book
        self._save(data)
        return book

    def project_deposit(
        self,
        match_id: str,
        *,
        bettor_id: str,
        side: str,
        amount_usdc: Decimal,
        tx_hash: str,
        explorer: str = "",
    ) -> dict[str, Any]:
        """Append-only projection after a confirmed SpectatorPool deposit.

        No cap / status==open check — the chain already accepted the bet.
        Idempotent on tx_hash.
        """
        side = side.lower()
        if side not in {"a", "b"}:
            raise ValueError("side must be a or b")
        if amount_usdc <= 0:
            raise ValueError("amount must be positive")
        txh = (tx_hash or "").strip()
        if not txh:
            raise ValueError("tx_hash required")
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if not book.get("onchain"):
            raise ValueError("project_deposit only for on-chain books")
        for existing in book.get("bets") or []:
            if (existing.get("tx_hash") or "") == txh:
                return book
        book.setdefault("bets", []).append(
            {
                "bettor_id": bettor_id,
                "side": side,
                "amount": str(amount_usdc),
                "ts": _now(),
                "tx_hash": txh,
                "explorer": explorer,
            }
        )
        tot = _d(book["totals"].get(side, "0")) + amount_usdc
        book["totals"][side] = str(tot)
        data["books"][match_id] = book
        self._save(data)
        return book

    def project_resolve(
        self,
        match_id: str,
        *,
        tx_hash: str,
        explorer: str = "",
    ) -> dict[str, Any]:
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if tx_hash:
            book["resolve_tx_hash"] = tx_hash
            book["resolve_explorer"] = explorer
        data["books"][match_id] = book
        self._save(data)
        return book

    def close_book(self, match_id: str, *, reason: str = "stage") -> dict[str, Any]:
        """Stop new bets (mid-game freeze) without settling."""
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if book["status"] in {"open", "full"}:
            book["status"] = "closed"
            book["closed_reason"] = reason
            data["books"][match_id] = book
            self._save(data)
        return book

    def settle(
        self,
        match_id: str,
        *,
        winner_side: Optional[str],  # "a" | "b" | None for draw
        platform_fee_bps: int = DEFAULT_SPECTATOR_FEE_BPS,
        creator_bps: int = DEFAULT_CREATOR_SPECTATOR_BPS,
    ) -> dict[str, Any]:
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if book["status"] == "settled":
            return book

        totals = book.setdefault("totals", {})
        totals.setdefault("draw", "0")
        total_a = _d(totals.get("a") or "0")
        total_b = _d(totals.get("b") or "0")
        public_draw = sum(
            (_d(b.get("amount") or "0") for b in book.get("bets") or [] if str(b.get("side") or "") == "draw"),
            Decimal("0"),
        )
        pot = total_a + total_b
        seed_a = _d(book.get("seed_a") or "0")
        seed_b = _d(book.get("seed_b") or "0")
        seed_draw = _d(book.get("seed_draw") or "0")
        house_draw = seed_draw * 2

        def _draw_book_payouts(game_drawn: bool) -> dict[str, Any]:
            if game_drawn:
                if public_draw <= 0:
                    unused = []
                    if seed_draw > 0:
                        unused = [
                            {
                                "side": "draw",
                                "agent_id": book.get("agent_a_id"),
                                "wallet": book.get("agent_a_wallet"),
                                "amount": str(seed_draw),
                                "reason": "draw_seed_unused",
                            },
                            {
                                "side": "draw",
                                "agent_id": book.get("agent_b_id"),
                                "wallet": book.get("agent_b_wallet"),
                                "amount": str(seed_draw),
                                "reason": "draw_seed_unused",
                            },
                        ]
                    return {
                        "mode": "draw_seed_return",
                        "public_draw": "0",
                        "house_draw": str(house_draw),
                        "bettors": [],
                        "agent_split": [],
                        "seed_refunds": unused,
                    }
                pot_d = public_draw + house_draw
                fee = _bps(pot_d, platform_fee_bps)
                dist = pot_d - fee
                bettors = []
                for b in book.get("bets") or []:
                    if str(b.get("side") or "") != "draw":
                        continue
                    share = _d(b["amount"]) / public_draw * dist
                    bettors.append(
                        {
                            "bettor_id": b["bettor_id"],
                            "amount": str(share.quantize(Decimal("0.000001"))),
                            "reason": "draw_win",
                        }
                    )
                return {
                    "mode": "draw_hits",
                    "public_draw": str(public_draw),
                    "house_draw": str(house_draw),
                    "pot": str(pot_d),
                    "platform_fee": str(fee),
                    "bettors": bettors,
                    "agent_split": [],
                    "seed_refunds": [],
                }
            half = (public_draw / 2).quantize(Decimal("0.000001"))
            split = []
            if half > 0:
                split = [
                    {
                        "agent_id": book.get("agent_a_id"),
                        "wallet": book.get("agent_a_wallet"),
                        "amount": str(half),
                        "reason": "draw_underwrite_win",
                    },
                    {
                        "agent_id": book.get("agent_b_id"),
                        "wallet": book.get("agent_b_wallet"),
                        "amount": str(half),
                        "reason": "draw_underwrite_win",
                    },
                ]
            returned = []
            if seed_draw > 0:
                returned = [
                    {
                        "side": "draw",
                        "agent_id": book.get("agent_a_id"),
                        "wallet": book.get("agent_a_wallet"),
                        "amount": str(seed_draw),
                        "reason": "draw_seed_return",
                    },
                    {
                        "side": "draw",
                        "agent_id": book.get("agent_b_id"),
                        "wallet": book.get("agent_b_wallet"),
                        "amount": str(seed_draw),
                        "reason": "draw_seed_return",
                    },
                ]
            return {
                "mode": "draw_misses",
                "public_draw": str(public_draw),
                "house_draw": str(house_draw),
                "bettors": [],
                "agent_split": split,
                "seed_refunds": returned,
            }

        if winner_side is None:
            side_refunds = [
                {"bettor_id": b["bettor_id"], "amount": b["amount"], "reason": "refund"}
                for b in book.get("bets") or []
                if str(b.get("side") or "") in {"a", "b"}
            ]
            draw_book = _draw_book_payouts(game_drawn=True)
            book["status"] = "settled"
            book["settled_at"] = _now()
            book["payouts"] = {
                "mode": "refund" if winner_side is None else "empty",
                "pot": str(pot),
                "bettors": side_refunds,
                "seed_refunds": [
                    {
                        "side": "a",
                        "agent_id": book.get("agent_a_id"),
                        "wallet": book.get("agent_a_wallet"),
                        "amount": str(seed_a),
                        "reason": "seed_refund_draw",
                    },
                    {
                        "side": "b",
                        "agent_id": book.get("agent_b_id"),
                        "wallet": book.get("agent_b_wallet"),
                        "amount": str(seed_b),
                        "reason": "seed_refund_draw",
                    },
                    *draw_book.get("seed_refunds", []),
                ],
                "draw_book": draw_book,
                "creators": [],
                "platform_fee": "0",
            }
            data["books"][match_id] = book
            self._save(data)
            return book

        winner_side = winner_side.lower()
        if winner_side not in {"a", "b"}:
            raise ValueError("winner_side must be a, b, or None")

        platform_fee = _bps(pot, platform_fee_bps)
        creator_pool = _bps(pot, creator_bps)
        # split creator pool 50/50 both creators (both brought the match)
        c_each = (creator_pool / 2).quantize(Decimal("0.000001"))
        distributable = pot - platform_fee - creator_pool
        win_total = total_a if winner_side == "a" else total_b

        draw_book = _draw_book_payouts(game_drawn=False)
        bettor_payouts = []
        if win_total > 0 and distributable > 0:
            for b in book["bets"]:
                if b["side"] != winner_side:
                    continue
                share = _d(b["amount"]) / win_total * distributable
                bettor_payouts.append(
                    {
                        "bettor_id": b["bettor_id"],
                        "amount": str(share.quantize(Decimal("0.000001"))),
                        "reason": "win",
                    }
                )

        creators = []
        if c_each > 0:
            if book.get("creator_a_id"):
                creators.append(
                    {
                        "creator_id": book["creator_a_id"],
                        "amount": str(c_each),
                        "reason": "creator_spectator_fee",
                    }
                )
            if book.get("creator_b_id"):
                creators.append(
                    {
                        "creator_id": book["creator_b_id"],
                        "amount": str(c_each),
                        "reason": "creator_spectator_fee",
                    }
                )

        book["status"] = "settled"
        book["settled_at"] = _now()
        book["payouts"] = {
            "mode": "winner_take_side",
            "winner_side": winner_side,
            "pot": str(pot),
            "platform_fee": str(platform_fee),
            "creator_pool": str(creator_pool),
            "distributable": str(distributable),
            "bettors": bettor_payouts,
            "creators": creators,
            "draw_book": draw_book,
            "seed_refunds": list(draw_book.get("seed_refunds") or []),
        }
        data["books"][match_id] = book
        self._save(data)
        return book

    def get(self, match_id: str) -> Optional[dict[str, Any]]:
        return self._load()["books"].get(match_id)

    def record_odds(self, match_id: str, snapshot: dict[str, Any]) -> None:
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            return
        hist = list(book.get("odds_history") or [])
        hist.append(snapshot)
        book["odds_history"] = hist[-40:]  # cap
        book["odds_live"] = snapshot
        data["books"][match_id] = book
        self._save(data)
