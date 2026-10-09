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
  draw → A/B tickets LOSE (not a push); draw tickets win the whole pool
  draw book (separate): both agents seed the same $; fans bet "draw"
    decisive game → agents split public draw bets 50/50 and get seeds back
    actual draw → draw bettors take everything (side bets + side seeds +
                  public draw + both agent draw seeds); side bettors lose

Demo ledger only (same file store as agentic). On-chain pools later.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.store import data_dir, load_json, save_json

BOOK_FILE = "spectator_books.json"
BOOK_ARCHIVE_FILE = "spectator_books_archive.json"
# Settled books kept in the hot file. Everything older is compacted into the
# archive — the hot file is rewritten on every bet/odds tick, so letting 1.8k
# settled books accumulate froze the API for seconds per save (GIL held while
# dumping 97MB) and eventually wedged it entirely.
HOT_SETTLED_BOOKS = 50
# Process-wide parse caches keyed by path (mtime invalidates across processes).
_HOT_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}
_ARCH_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}
_CACHE_LOCK = threading.RLock()
# Pot-level tiered platform fee — mirrors SpectatorPool._platformFee (V1 tiers):
#   pot < $10   → min($1, 25% of pot)   (dust clamp, effective ≤ 25%)
#   $10 ≤ pot ≤ $1000 → 700 bps
#   pot > $1000 → 1000 bps
DEFAULT_SPECTATOR_FEE_BPS = 700
SPECTATOR_TIER_FLAT_FEE = Decimal("1.0")
SPECTATOR_TIER_FLAT_MAX = Decimal("10")
SPECTATOR_TIER_BPS_MAX = Decimal("1000")
SPECTATOR_TIER_PREMIUM_BPS = 1000
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


def spectator_platform_fee_for_pot(pot: Decimal, mid_bps: int = DEFAULT_SPECTATOR_FEE_BPS) -> Decimal:
    """Tiered spectator platform fee — mirrors SpectatorPool._platformFee."""
    pot = _d(pot)
    if pot <= 0:
        return Decimal("0.000000")
    if pot < SPECTATOR_TIER_FLAT_MAX:
        return min(SPECTATOR_TIER_FLAT_FEE, pot / 4).quantize(Decimal("0.000001"))
    if pot <= SPECTATOR_TIER_BPS_MAX:
        return _bps(pot, mid_bps)
    return _bps(pot, SPECTATOR_TIER_PREMIUM_BPS)


def _cached_load(name: str, cache: dict[str, tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
    """mtime-guarded parse cache — stat() is cheap; parsing 97MB is not."""
    path = data_dir() / name
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = None
    key = str(path)
    with _CACHE_LOCK:
        hit = cache.get(key)
        if hit is not None and hit[0] == mtime:
            return hit[1]
    data = load_json(name, {"books": {}})
    with _CACHE_LOCK:
        cache[key] = (mtime, data)
    return data


def all_books() -> dict[str, Any]:
    """Hot file merged over the archive (archive never overwrites hot)."""
    merged = dict(_cached_load(BOOK_ARCHIVE_FILE, _ARCH_CACHE).get("books") or {})
    merged.update(_cached_load(BOOK_FILE, _HOT_CACHE).get("books") or {})
    return merged


class SpectatorBook:
    def _load(self) -> dict[str, Any]:
        return _cached_load(BOOK_FILE, _HOT_CACHE)

    def _save(self, data: dict[str, Any]) -> None:
        data = self._archive_cold(data)
        save_json(BOOK_FILE, data, compact=True)
        # Invalidate rather than re-key: another thread/process may have
        # written between our replace and the stat — a stale (mtime, data)
        # pair would be worse than one extra parse of a ~1MB file.
        with _CACHE_LOCK:
            _HOT_CACHE.pop(str(data_dir() / BOOK_FILE), None)

    @staticmethod
    def _archive_cold(data: dict[str, Any]) -> dict[str, Any]:
        """Move settled books beyond the hot window into spectator_books_archive.json.

        Mirrors AgentMatchService._archive_cold: the hot file is rewritten on
        every bet/odds tick, so only live books + recent settlements stay there.
        """
        books = data.get("books") or {}
        settled = [b for b in books.values() if b.get("status") == "settled"]
        if len(settled) <= HOT_SETTLED_BOOKS:
            return data
        settled.sort(
            key=lambda b: b.get("settled_at") or b.get("created_at") or "",
            reverse=True,
        )
        keep = {
            k: b for k, b in books.items() if b.get("status") != "settled"
        }
        for b in settled[:HOT_SETTLED_BOOKS]:
            keep[b["match_id"]] = b
        drop = settled[HOT_SETTLED_BOOKS:]
        arch = load_json(BOOK_ARCHIVE_FILE, {"books": {}})
        arch_books = arch.setdefault("books", {})
        for b in drop:
            arch_books[b["match_id"]] = b
        save_json(BOOK_ARCHIVE_FILE, arch, compact=True)
        with _CACHE_LOCK:
            _ARCH_CACHE.pop(str(data_dir() / BOOK_ARCHIVE_FILE), None)
        data["books"] = keep
        return data

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

    def ensure_from_match(self, m: dict[str, Any]) -> dict[str, Any]:
        """
        Recreate a missing book from the match record (idempotent).

        A book can be lost to a failed save (disk full) or never opened if
        `open_book` crashed mid-create. Bettors would otherwise hit
        "book not found" and the match could not settle. The match record
        carries the same economy fields open_book was called with, so the
        reconstruction is faithful — except bets made before the loss, which
        live only in the book and are unrecoverable by design.
        """
        match_id = str(m.get("match_id") or "")
        if not match_id:
            raise ValueError("match has no match_id")
        data = self._load()
        if match_id in data["books"]:
            return data["books"][match_id]
        archived = _cached_load(BOOK_ARCHIVE_FILE, _ARCH_CACHE).get("books") or {}
        if match_id in archived:
            return archived[match_id]
        eco = m.get("economy") or {}
        return self.open_book(
            match_id,
            agent_a_id=str(m.get("agent_a_id") or ""),
            agent_b_id=str(m.get("agent_b_id") or ""),
            seed_a=_d(eco.get("spectator_seed_a") or "0"),
            seed_b=_d(eco.get("spectator_seed_b") or "0"),
            seed_draw=_d(eco.get("spectator_seed_draw") or "0"),
            creator_a_id=str(m.get("creator_a_id") or ""),
            creator_b_id=str(m.get("creator_b_id") or ""),
            pot_cap_usdc=_d(eco.get("pot_cap_usdc")) if eco.get("pot_cap_usdc") else None,
            agent_a_wallet=str(m.get("agent_a_wallet") or ""),
            agent_b_wallet=str(m.get("agent_b_wallet") or ""),
        )

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
        if book.get("onchain"):
            raise ValueError(
                "on-chain book — bets are recorded via project_deposit after a confirmed pool deposit"
            )
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
            label = "draw book" if side == "draw" else "pot"
            raise ValueError(f"{label} cap ${cap} — ${room} room left, asked for ${amount_usdc}")
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
        if side in {"d", "tie"}:
            side = "draw"
        if side not in {"a", "b", "draw"}:
            raise ValueError("side must be a, b, or draw")
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
            # Only settled books ever leave the hot file — an archived hit is
            # an already-finalized book, so re-settle is a no-op, not an error.
            archived = (
                _cached_load(BOOK_ARCHIVE_FILE, _ARCH_CACHE).get("books") or {}
            ).get(match_id)
            if archived:
                return archived
            raise ValueError("book not found")
        if book["status"] == "settled":
            # Idempotent no-op ONLY for the same winner. A conflicting re-settle
            # must raise so the caller cannot preserve a wrong book result.
            prev_side = book.get("payouts", {}).get("winner_side") if isinstance(book.get("payouts"), dict) else None
            if (prev_side or None) != (winner_side or None):
                raise ValueError(
                    f"book {match_id} already settled with winner_side={prev_side!r}; refusing conflicting settle winner_side={winner_side!r}"
                )
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
                fee = spectator_platform_fee_for_pot(pot_d, platform_fee_bps)
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
            # Draw is a real outcome — NOT a push. A/B side tickets LOSE; draw
            # tickets win the entire pool (side stakes + side seeds + draw
            # stakes + house draw seed), minus platform/creator fees.
            draw_pot = pot + public_draw + house_draw
            d_fee = spectator_platform_fee_for_pot(draw_pot, platform_fee_bps)
            d_creator_pool = _bps(draw_pot, creator_bps)
            d_c_each = (d_creator_pool / 2).quantize(Decimal("0.000001"))
            d_distributable = draw_pot - d_fee - d_creator_pool
            draw_winners = []
            if public_draw > 0 and d_distributable > 0:
                for b in book.get("bets") or []:
                    if str(b.get("side") or "") != "draw":
                        continue
                    share = _d(b["amount"]) / public_draw * d_distributable
                    draw_winners.append(
                        {
                            "bettor_id": b["bettor_id"],
                            "amount": str(share.quantize(Decimal("0.000001"))),
                            "reason": "draw_win",
                        }
                    )
            creators = []
            if d_c_each > 0:
                if book.get("creator_a_id"):
                    creators.append(
                        {
                            "creator_id": book["creator_a_id"],
                            "amount": str(d_c_each),
                            "reason": "creator_spectator_fee",
                        }
                    )
                if book.get("creator_b_id"):
                    creators.append(
                        {
                            "creator_id": book["creator_b_id"],
                            "amount": str(d_c_each),
                            "reason": "creator_spectator_fee",
                        }
                    )
            book["status"] = "settled"
            book["settled_at"] = _now()
            book["payouts"] = {
                "mode": "draw_hits",
                "winner_side": None,
                "pot": str(draw_pot),
                "platform_fee": str(d_fee),
                "creator_pool": str(d_creator_pool),
                "distributable": str(d_distributable),
                "bettors": draw_winners,
                "creators": creators,
                "draw_book": {},
                "seed_refunds": [],
            }
            data["books"][match_id] = book
            self._save(data)
            return book

        winner_side = winner_side.lower()
        if winner_side not in {"a", "b"}:
            raise ValueError("winner_side must be a, b, or None")

        platform_fee = spectator_platform_fee_for_pot(pot, platform_fee_bps)
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
        book = self._load()["books"].get(match_id)
        if book is None:
            book = (_cached_load(BOOK_ARCHIVE_FILE, _ARCH_CACHE).get("books") or {}).get(match_id)
        return book

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
