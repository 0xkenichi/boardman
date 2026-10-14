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

Demo book in the agentic database (one row per match); on-chain books are a
projection of confirmed SpectatorPool txs. Every mutation is an atomic
read-modify-write of that row.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator, Optional

from gaming.src.stack.agentic.db.tables import BOOKS, HOT_SETTLED_BOOKS, hot_books  # noqa: F401

# Legacy file names (imported by scripts/migrate_json_to_db.py). Books are one
# database row each now: a bet or odds tick rewrites one row, not a 97MB file.
BOOK_FILE = "spectator_books.json"
BOOK_ARCHIVE_FILE = "spectator_books_archive.json"
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


class _AllBooks(Mapping):
    """Every book (live + settled), lazily: ``.get(id)`` is one indexed read.

    Replaces the old hot+archive merge that parsed ~67MB per call.
    """

    def __getitem__(self, key: str) -> dict[str, Any]:
        b = BOOKS.get(str(key))
        if b is None:
            raise KeyError(key)
        return b

    def get(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
        b = BOOKS.get(str(key or ""))
        return default if b is None else b

    def __iter__(self) -> Iterator[str]:
        return iter(BOOKS.keys())

    def __len__(self) -> int:
        return BOOKS.count()

    def items(self):  # type: ignore[override]
        return [(str(b.get("match_id")), b) for b in BOOKS.query()]

    def values(self):  # type: ignore[override]
        return BOOKS.query()


def all_books() -> Mapping[str, Any]:
    """All books keyed by match_id (lazy mapping over the database)."""
    return _AllBooks()


def _betting_gate(match_id: str) -> None:
    from gaming.src.backend.services.spectator_policy import assert_spectator_betting_allowed

    assert_spectator_betting_allowed(path="SpectatorBook.place_bet", match_id=match_id)


def betting_open_for_new_books() -> bool:
    """Kill switch (no country): may a new book be opened / seeded?"""
    try:
        from gaming.src.backend.services.spectator_policy import betting_globally_enabled

        return betting_globally_enabled()
    except Exception:
        return False


class SpectatorBook:
    def _load(self) -> dict[str, Any]:
        """Legacy whole-file view (live books + the newest settled ones)."""
        return BOOKS.snapshot(hot_books(), "match_id")

    def _save(self, data: dict[str, Any]) -> None:
        """Write back only what the caller changed in a ``_load()`` snapshot."""
        BOOKS.save_snapshot(data)

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
        closed_reason: str = "",
    ) -> dict[str, Any]:
        existing = BOOKS.get(match_id)
        if existing is not None:
            return existing
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
        if closed_reason:
            # Kill switch off: the book exists (settlement and views expect
            # one) but never takes a ticket.
            rec["status"] = "closed"
            rec["closed_reason"] = closed_reason
        stored, _created = BOOKS.insert_if_absent(match_id, rec)
        return stored

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
        existing = BOOKS.get(match_id)
        if existing is not None:
            return existing
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
        amount_usdc = _d(amount_usdc)
        # Kill switch / country allowlist — before any state is touched.
        _betting_gate(match_id)

        def _apply(book: dict[str, Any]) -> None:
            if book.get("onchain"):
                raise ValueError(
                    "on-chain book — bets are recorded via project_deposit after a confirmed pool deposit"
                )
            if book["status"] != "open":
                raise ValueError(f"book not open: {book['status']}")
            self._book_bet(book, bettor_id=bettor_id, side=side, amount_usdc=amount_usdc)

        try:
            book = BOOKS.update(match_id, _apply)
        except _PotFull as exc:
            # Mark the book full (its own small transaction), then refuse.
            if exc.mark_full:
                BOOKS.update(match_id, lambda b: b.update(status="full") if b.get("status") == "open" else None)
            raise ValueError(str(exc)) from None
        if book is None:
            raise ValueError("book not found")
        return book

    @staticmethod
    def _book_bet(
        book: dict[str, Any], *, bettor_id: str, side: str, amount_usdc: Decimal
    ) -> None:
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
                raise _PotFull("pot full — no more bets", mark_full=side != "draw")
            label = "draw book" if side == "draw" else "pot"
            raise _PotFull(f"{label} cap ${cap} — ${room} room left, asked for ${amount_usdc}", mark_full=False)
        book.setdefault("bets", []).append(
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

    def mark_onchain(
        self,
        match_id: str,
        *,
        pool: str = "",
        open_tx_hash: str = "",
    ) -> dict[str, Any]:
        def _apply(book: dict[str, Any]) -> None:
            book["onchain"] = True
            if pool:
                book["pool"] = pool
            if open_tx_hash:
                book["open_tx_hash"] = open_tx_hash

        book = BOOKS.update(match_id, _apply)
        if book is None:
            raise ValueError("book not found")
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
        amount_usdc = _d(amount_usdc)

        def _apply(book: dict[str, Any]) -> None:
            if not book.get("onchain"):
                raise ValueError("project_deposit only for on-chain books")
            for existing in book.get("bets") or []:
                if (existing.get("tx_hash") or "") == txh:
                    return
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
            totals = book.setdefault("totals", {})
            totals[side] = str(_d(totals.get(side, "0")) + amount_usdc)

        book = BOOKS.update(match_id, _apply)
        if book is None:
            raise ValueError("book not found")
        return book

    def project_resolve(
        self,
        match_id: str,
        *,
        tx_hash: str,
        explorer: str = "",
    ) -> dict[str, Any]:
        def _apply(book: dict[str, Any]) -> None:
            if tx_hash:
                book["resolve_tx_hash"] = tx_hash
                book["resolve_explorer"] = explorer

        book = BOOKS.update(match_id, _apply)
        if book is None:
            raise ValueError("book not found")
        return book

    def close_book(self, match_id: str, *, reason: str = "stage") -> dict[str, Any]:
        """Stop new bets (mid-game freeze) without settling."""
        def _apply(book: dict[str, Any]) -> None:
            if book["status"] in {"open", "full"}:
                book["status"] = "closed"
                book["closed_reason"] = reason

        book = BOOKS.update(match_id, _apply)
        if book is None:
            raise ValueError("book not found")
        return book

    def settle(
        self,
        match_id: str,
        *,
        winner_side: Optional[str],  # "a" | "b" | None for draw
        platform_fee_bps: int = DEFAULT_SPECTATOR_FEE_BPS,
        creator_bps: int = DEFAULT_CREATOR_SPECTATOR_BPS,
    ) -> dict[str, Any]:
        def _apply(book: dict[str, Any]) -> None:
            if book["status"] == "settled":
                # Idempotent no-op ONLY for the same winner. A conflicting re-settle
                # must raise so the caller cannot preserve a wrong book result.
                prev_side = book.get("payouts", {}).get("winner_side") if isinstance(book.get("payouts"), dict) else None
                if (prev_side or None) != (winner_side or None):
                    raise ValueError(
                        f"book {match_id} already settled with winner_side={prev_side!r}; refusing conflicting settle winner_side={winner_side!r}"
                    )
                return
            self._settle_book(book, winner_side, platform_fee_bps, creator_bps)

        book = BOOKS.update(match_id, _apply)
        if book is None:
            raise ValueError("book not found")
        return book

    @staticmethod
    def _settle_book(
        book: dict[str, Any],
        winner_side: Optional[str],
        platform_fee_bps: int,
        creator_bps: int,
    ) -> None:
        """Compute payouts and mark the book settled (pure, on the row being written)."""
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
            return

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

    def get(self, match_id: str) -> Optional[dict[str, Any]]:
        """Indexed lookup — live or settled, no archive file to parse."""
        return BOOKS.get(match_id)

    def record_odds(self, match_id: str, snapshot: dict[str, Any]) -> None:
        def _apply(book: dict[str, Any]) -> None:
            hist = list(book.get("odds_history") or [])
            hist.append(snapshot)
            book["odds_history"] = hist[-40:]  # cap
            book["odds_live"] = snapshot

        BOOKS.update(match_id, _apply)


class _PotFull(Exception):
    def __init__(self, msg: str, *, mark_full: bool) -> None:
        super().__init__(msg)
        self.mark_full = mark_full
