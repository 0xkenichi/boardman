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
  draw → refund all spectator bets + seeds to origins

Demo ledger only (same file store as agentic). On-chain pools later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json, save_json

BOOK_FILE = "spectator_books.json"
DEFAULT_SPECTATOR_FEE_BPS = 300  # 3% platform
DEFAULT_CREATOR_SPECTATOR_BPS = 200  # 2% of pot split across both creators


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
            "pot_cap_usdc": str(cap),
            "bets": [],  # {bettor_id, side: a|b, amount, ts}
            "totals": {"a": str(seed_a), "b": str(seed_b)},
            "odds_history": [],  # snapshots from economy.odds
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
        if side not in {"a", "b"}:
            raise ValueError("side must be a or b")
        if amount_usdc <= 0:
            raise ValueError("amount must be positive")
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if book["status"] != "open":
            raise ValueError(f"book not open: {book['status']}")
        pot = _d(book["totals"]["a"]) + _d(book["totals"]["b"])
        cap = _d(book.get("pot_cap_usdc") or "0")
        if cap > 0 and pot + amount_usdc > cap + Decimal("0.000001"):
            room = cap - pot
            if room <= 0:
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

    def close_book(self, match_id: str, *, reason: str = "stage") -> dict[str, Any]:
        """Stop new bets (mid-game freeze) without settling."""
        data = self._load()
        book = data["books"].get(match_id)
        if not book:
            raise ValueError("book not found")
        if book["status"] == "open":
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

        total_a = _d(book["totals"]["a"])
        total_b = _d(book["totals"]["b"])
        pot = total_a + total_b
        seed_a = _d(book.get("seed_a") or "0")
        seed_b = _d(book.get("seed_b") or "0")

        if winner_side is None or pot == 0:
            # Refund fan bets + return seeds to agent wallets (caller credits)
            book["status"] = "settled"
            book["settled_at"] = _now()
            book["payouts"] = {
                "mode": "refund",
                "pot": str(pot),
                "bettors": [
                    {"bettor_id": b["bettor_id"], "amount": b["amount"], "reason": "refund"}
                    for b in book["bets"]
                ],
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
                ],
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
