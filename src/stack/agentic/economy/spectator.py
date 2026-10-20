"""
Spectator pot keyed by match_id — separate from skill escrow.

People watch Raja vs Nero (or any agent match) and stake USDC on a side.
Agent deploy policy can auto-seed a fraction of each side's stake into the pot
(creator "puts skin" so the market has juice).

Settlement (mirrors SpectatorPool):
  pot = funded seeds + all spectator bets
  platform takes the tiered spectator fee
  creators of BOTH agents split creator_spectator_bps of pot
  remainder goes pro-rata to the FAN tickets on the winning side (seeds
    underwrite: they never share in the winnings)
  nobody backed the result → every ticket and seed is refunded, no fee
  draw → A/B tickets LOSE (not a push); draw tickets win the whole pool
  draw book (separate): both agents seed the same $; fans bet "draw"
    decisive game → agents split public draw bets 50/50 and get seeds back
    actual draw → draw bettors take everything (side bets + side seeds +
                  public draw + both agent draw seeds); side bettors lose

Money conservation. Every ticket records the rail its stake was taken from
(``funding``) and is paid or refunded on that same rail only:
  ledger   place_bet debits the bettor's agentic-ledger wallet in the same
           transaction that books the ticket (builder / stack API bettors);
  profile  the caller already took the stake from the bettor's play balance
           (web + Telegram via rematch_web); paid back through play_adjust;
  onchain  a confirmed SpectatorPool deposit; the pool pays, never us.
Seeds count only as far as the lock really debited them. Amounts are split in
integer micro-USDC rounding down; the remainder (dust) joins the platform fee,
which is credited to the treasury wallet — so every payout comes out of money
the book took in, and the totals always balance to the micro.

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

from gaming.src.stack.agentic.db import transaction
from gaming.src.stack.agentic.db.money import fmt, to_micro
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

# Where a ticket's stake came from — and so where its payout goes.
FUNDING_LEDGER = "ledger"
FUNDING_PROFILE = "profile"
FUNDING_ONCHAIN = "onchain"
_SYSTEM_BETTOR_PREFIXES = ("0x", "agent_", "afm_", "house", "platform", "treasury", "boardman")


def bet_funding(bet: dict[str, Any]) -> str:
    """The rail a ticket was paid from. Tickets booked before the field
    existed came from the web/bot play balance (the only path that took a
    stake), so they are refunded and paid there too."""
    f = str(bet.get("funding") or "")
    if f in {FUNDING_LEDGER, FUNDING_PROFILE, FUNDING_ONCHAIN}:
        return f
    return FUNDING_ONCHAIN if bet.get("tx_hash") else FUNDING_PROFILE


def ledger_wallet_of(bettor_id: Any) -> str:
    """The ledger wallet a ledger-funded ticket was debited from."""
    from gaming.src.stack.agentic.party_wallet import football_wallet, is_person

    b = str(bettor_id or "")
    return football_wallet(b) if is_person(b) else b


def _assert_ledger_bettor(bettor_id: str) -> None:
    """A ledger-funded ticket debits ``bettor_id`` itself: never a system
    wallet (agents, pots, owner/creator/LP wallets, the House)."""
    b = (bettor_id or "").strip()
    if not b:
        raise ValueError("bettor_id is required")
    if ":" in b or b.lower().startswith(_SYSTEM_BETTOR_PREFIXES):
        raise ValueError("bettor must be a spectator id, not a system wallet")


def book_close_plies() -> int:
    """Ply count after which new spectator bets are refused."""
    try:
        n = int(os.getenv("BOARDMAN_BOOK_CLOSE_PLIES") or str(DEFAULT_BOOK_CLOSE_PLIES))
    except ValueError:
        n = DEFAULT_BOOK_CLOSE_PLIES
    return max(4, min(n, 200))


def book_close_sec() -> int:
    """Seconds after kickoff when new spectator bets are refused (0 = off).

    Friendlies close on whichever comes first: this clock or
    book_close_plies(). The clock is steadier than a ply count, since engine
    games move at very different speeds.
    """
    try:
        n = int(float(os.getenv("BOARDMAN_BOOK_CLOSE_SEC") or "0"))
    except ValueError:
        n = 0
    return max(0, min(n, 3600))


def book_close_reason(match: dict[str, Any], *, now: Optional[datetime] = None) -> Optional[str]:
    """Why the book of a live ``match`` must be closed now, or None."""
    ply = len(match.get("moves") or [])
    if ply >= book_close_plies():
        return f"ply_{ply}"
    secs = book_close_sec()
    raw = str(match.get("play_started_at") or "")
    if secs and raw:
        try:
            started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if ((now or datetime.now(timezone.utc)) - started).total_seconds() >= secs:
            return f"clock_{secs}s"
    return None


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
        funding: str = FUNDING_LEDGER,
    ) -> dict[str, Any]:
        """Book one ticket.

        ``funding="ledger"`` (default) debits the bettor's agentic-ledger
        wallet in the same transaction as the ticket: no debit, no ticket.
        ``funding="profile"`` means the caller takes (or already took) the
        stake from the bettor's play balance; the payout goes back there.
        """
        side = side.lower()
        if side in {"d", "tie"}:
            side = "draw"
        if side not in {"a", "b", "draw"}:
            raise ValueError("side must be a, b, or draw")
        if amount_usdc <= 0:
            raise ValueError("amount must be positive")
        amount_usdc = _d(amount_usdc)
        if to_micro(amount_usdc) <= 0:
            raise ValueError("amount must be at least 0.000001 USDC")
        if funding not in {FUNDING_LEDGER, FUNDING_PROFILE}:
            raise ValueError("funding must be ledger or profile (on-chain tickets use project_deposit)")
        if funding == FUNDING_LEDGER:
            _assert_ledger_bettor(bettor_id)
        # Kill switch / country allowlist — before any state is touched.
        _betting_gate(match_id)

        def _apply(book: dict[str, Any]) -> None:
            if book.get("onchain"):
                raise ValueError(
                    "on-chain book — bets are recorded via project_deposit after a confirmed pool deposit"
                )
            if book["status"] != "open":
                raise ValueError(f"book not open: {book['status']}")
            self._book_bet(book, bettor_id=bettor_id, side=side, amount_usdc=amount_usdc, funding=funding)

        try:
            with transaction():
                book = BOOKS.update(match_id, _apply)
                if book is None:
                    raise ValueError("book not found")
                if funding == FUNDING_LEDGER:
                    from gaming.src.stack.agentic import ledger
                    from gaming.src.stack.agentic.party_wallet import football_wallet, merge_legacy_wallet

                    # The person's one ledger wallet (owner:<id>). Same
                    # transaction as the ticket: InsufficientFunds rolls the
                    # ticket back too.
                    merge_legacy_wallet(bettor_id)
                    ledger.debit(football_wallet(bettor_id), amount_usdc, reason="spectator_bet", ref=match_id)
        except _PotFull as exc:
            # Mark the book full (its own small transaction), then refuse.
            if exc.mark_full:
                BOOKS.update(match_id, lambda b: b.update(status="full") if b.get("status") == "open" else None)
            raise ValueError(str(exc)) from None
        return book

    @staticmethod
    def _book_bet(
        book: dict[str, Any], *, bettor_id: str, side: str, amount_usdc: Decimal, funding: str
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
                "funding": funding,
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
                    "funding": FUNDING_ONCHAIN,
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

    def void(self, match_id: str, *, reason: str = "interrupted") -> dict[str, Any]:
        """The game never produced a result: every ticket gets its stake back.

        No fee, no creator cut, no winner. Marks the book ``void`` with a
        ``payouts`` block listing one full refund per bet (``refunds``). The
        agents' seeds are refunded by the caller from the lock journal (the
        exact amounts debited), not from here. Idempotent: voiding a void book
        returns it unchanged; a settled book refuses.
        """

        def _apply(book: dict[str, Any]) -> None:
            if book.get("status") == "void":
                return
            if book.get("status") == "settled":
                raise ValueError(f"book {match_id} is already settled; refusing to void it")
            refunds = [
                {
                    "bettor_id": b.get("bettor_id"),
                    "side": b.get("side"),
                    "amount": str(_d(b.get("amount") or "0")),
                    "reason": "refund_void",
                    "funding": bet_funding(b),
                }
                for b in book.get("bets") or []
                if b.get("bettor_id") and _d(b.get("amount") or "0") > 0
            ]
            book["status"] = "void"
            book["closed_reason"] = reason
            book["voided_at"] = _now()
            book["payouts"] = {
                "mode": "void",
                "winner_side": None,
                "reason": reason,
                "refunds": refunds,
                "bettors": [],
                "creators": [],
                "draw_book": {},
                "seed_refunds": [],
            }

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
        funded_seeds: Optional[dict[str, Any]] = None,
        wallets: Optional[tuple[str, str]] = None,
    ) -> dict[str, Any]:
        """Settle once. ``funded_seeds`` ({a, b, draw_a, draw_b}) are the seeds
        the lock really debited (see ``funded_seeds_from_ledger``); default:
        the book's own seeds. ``wallets`` are the agents' ledger wallets."""
        def _apply(book: dict[str, Any]) -> None:
            if book.get("status") == "void":
                # A void book already refunded every ticket and seed: settling
                # it would pay the same pot a second time as winnings.
                raise ValueError(f"book {match_id} was voided (refunded); it cannot be settled")
            if book["status"] == "settled":
                # Idempotent no-op ONLY for the same winner. A conflicting re-settle
                # must raise so the caller cannot preserve a wrong book result.
                prev_side = book.get("payouts", {}).get("winner_side") if isinstance(book.get("payouts"), dict) else None
                if (prev_side or None) != (winner_side or None):
                    raise ValueError(
                        f"book {match_id} already settled with winner_side={prev_side!r}; refusing conflicting settle winner_side={winner_side!r}"
                    )
                return
            self._settle_book(book, winner_side, platform_fee_bps, creator_bps, funded_seeds, wallets)

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
        funded_seeds: Optional[dict[str, Any]] = None,
        wallets: Optional[tuple[str, str]] = None,
    ) -> None:
        """Compute payouts and mark the book settled (pure, on the row being written).

        Everything is integer micro-USDC; every split rounds down and the
        remainder goes to the house, so ``money in == money out`` exactly.
        """
        if winner_side is not None:
            winner_side = winner_side.lower()
            if winner_side not in {"a", "b"}:
                raise ValueError("winner_side must be a, b, or None")
        book.setdefault("totals", {}).setdefault("draw", "0")
        wa = str((wallets[0] if wallets else "") or book.get("agent_a_wallet") or "")
        wb = str((wallets[1] if wallets else "") or book.get("agent_b_wallet") or "")
        agents = {
            "a": (book.get("agent_a_id"), wa),
            "b": (book.get("agent_b_id"), wb),
        }

        def _cap(key: str, book_key: str) -> int:
            have = to_micro(book.get(book_key) or "0")
            if funded_seeds is None:
                return max(0, have)
            return max(0, min(have, to_micro(funded_seeds.get(key) or "0")))

        seeds = {
            "a": _cap("a", "seed_a"),
            "b": _cap("b", "seed_b"),
            "draw_a": _cap("draw_a", "seed_draw"),
            "draw_b": _cap("draw_b", "seed_draw"),
        }
        tickets = [
            {
                "bettor_id": str(b.get("bettor_id") or ""),
                "side": str(b.get("side") or ""),
                "micro": to_micro(b.get("amount") or "0"),
                "funding": bet_funding(b),
            }
            for b in book.get("bets") or []
            if b.get("bettor_id") and to_micro(b.get("amount") or "0") > 0
        ]
        house = {"fee": 0, "dust": 0, "unassigned": 0}
        bettors: list[dict[str, Any]] = []
        creators: list[dict[str, Any]] = []
        seed_refunds: list[dict[str, Any]] = []

        def _pay_agent(side: str, micro: int, reason: str, *, draw: bool = False) -> Optional[dict[str, Any]]:
            if micro <= 0:
                return None
            agent_id, wallet = agents[side]
            if not wallet:
                house["unassigned"] += micro  # nobody to pay: never vanishes
                return None
            row = {"agent_id": agent_id, "wallet": wallet, "amount": fmt(micro), "reason": reason}
            if draw:
                row["side"] = "draw"
            return row

        def _refund_seed(key: str, reason: str) -> None:
            side = "a" if key in {"a", "draw_a"} else "b"
            row = _pay_agent(side, seeds[key], reason, draw=key.startswith("draw"))
            if row:
                seed_refunds.append(row)

        def _refund_tickets(pred) -> None:
            for t in tickets:
                if pred(t):
                    bettors.append(
                        {
                            "bettor_id": t["bettor_id"],
                            "side": t["side"],
                            "amount": fmt(t["micro"]),
                            "reason": "refund",
                            "funding": t["funding"],
                        }
                    )

        def _split(pot: int, winners: list[dict[str, Any]], reason: str) -> dict[str, Any]:
            """Fee + creator pool off the pot; the rest pro-rata to winners."""
            fee = to_micro(spectator_platform_fee_for_pot(fmt(pot), platform_fee_bps))
            creator_pool = pot * max(0, int(creator_bps)) // 10_000
            if fee + creator_pool > pot:  # unreachable under the tiers; guard anyway
                creator_pool = min(creator_pool, pot)
                fee = pot - creator_pool
            dist = pot - fee - creator_pool
            fan_win = sum(t["micro"] for t in winners)
            paid = 0
            for t in winners:
                share = t["micro"] * dist // fan_win
                paid += share
                if share > 0:
                    bettors.append(
                        {
                            "bettor_id": t["bettor_id"],
                            "side": t["side"],
                            "amount": fmt(share),
                            "reason": reason,
                            "funding": t["funding"],
                        }
                    )
            house["fee"] += fee
            house["dust"] += dist - paid
            half = creator_pool // 2
            for cid, amt in ((book.get("creator_a_id"), half), (book.get("creator_b_id"), creator_pool - half)):
                if amt <= 0:
                    continue
                if cid:
                    creators.append({"creator_id": cid, "amount": fmt(amt), "reason": "creator_spectator_fee"})
                else:
                    house["unassigned"] += amt
            return {"pot": fmt(pot), "platform_fee": fmt(fee), "creator_pool": fmt(creator_pool), "distributable": fmt(dist)}

        side_fans = [t for t in tickets if t["side"] in {"a", "b"}]
        draw_fans = [t for t in tickets if t["side"] == "draw"]
        public_draw = sum(t["micro"] for t in draw_fans)
        draw_book: dict[str, Any] = {}

        if book.get("onchain"):
            # SpectatorPool holds (and pays) every fan ticket. The seeds the
            # ledger debited were never deposited to the pool: all go back.
            for key in ("a", "b", "draw_a", "draw_b"):
                _refund_seed(key, "seed_refund_onchain")
            summary: dict[str, Any] = {"mode": "onchain", "pot": "0", "platform_fee": "0", "creator_pool": "0", "distributable": "0"}
            bettors = []
        elif winner_side is None:
            # Draw is a real outcome — NOT a push. A/B side tickets LOSE; draw
            # tickets win the entire pool (side stakes + side seeds + draw
            # stakes + both draw seeds), minus platform/creator fees.
            pot = sum(t["micro"] for t in tickets) + sum(seeds.values())
            if pot <= 0:
                summary = {"mode": "draw_hits", "pot": "0", "platform_fee": "0", "creator_pool": "0", "distributable": "0"}
            elif public_draw <= 0:
                # Nobody backed the draw: everything goes back (as the pool does).
                _refund_tickets(lambda t: True)
                for key in ("a", "b", "draw_a", "draw_b"):
                    _refund_seed(key, "seed_refund_no_winner")
                summary = {"mode": "refund_no_winner", "pot": fmt(pot), "platform_fee": "0", "creator_pool": "0", "distributable": "0"}
            else:
                summary = {"mode": "draw_hits", **_split(pot, draw_fans, "draw_win")}
        else:
            pot = sum(t["micro"] for t in side_fans) + seeds["a"] + seeds["b"]
            winners = [t for t in side_fans if t["side"] == winner_side]
            if pot <= 0:
                summary = {"mode": "winner_take_side", "pot": "0", "platform_fee": "0", "creator_pool": "0", "distributable": "0"}
            elif not winners:
                # Nobody backed the winner: the side market is refunded.
                _refund_tickets(lambda t: t["side"] in {"a", "b"})
                _refund_seed("a", "seed_refund_no_winner")
                _refund_seed("b", "seed_refund_no_winner")
                summary = {"mode": "refund_no_winner", "pot": fmt(pot), "platform_fee": "0", "creator_pool": "0", "distributable": "0"}
            else:
                summary = {"mode": "winner_take_side", **_split(pot, winners, "win")}
            # Separate draw book: the game was decisive, so draw tickets lose
            # to the agents that underwrote them, and their draw seeds return.
            half = public_draw // 2
            split = [r for r in (
                _pay_agent("a", half, "draw_underwrite_win"),
                _pay_agent("b", public_draw - half, "draw_underwrite_win"),
            ) if r]
            returned = [r for r in (
                _pay_agent("a", seeds["draw_a"], "draw_seed_return", draw=True),
                _pay_agent("b", seeds["draw_b"], "draw_seed_return", draw=True),
            ) if r]
            draw_book = {
                "mode": "draw_misses",
                "public_draw": fmt(public_draw),
                "house_draw": fmt(seeds["draw_a"] + seeds["draw_b"]),
                "bettors": [],
                "agent_split": split,
                "seed_refunds": returned,
            }
            seed_refunds.extend(returned)

        house_take = house["fee"] + house["dust"] + house["unassigned"]
        book["status"] = "settled"
        book["settled_at"] = _now()
        book["payouts"] = {
            **summary,
            "winner_side": winner_side,
            "funded_seeds": {k: fmt(v) for k, v in seeds.items()},
            "bettors": bettors,
            "creators": creators,
            "draw_book": draw_book,
            "seed_refunds": seed_refunds,
            "house": {k: fmt(v) for k, v in house.items()},
            "house_take": fmt(house_take),
        }

    @staticmethod
    def ledger_credits(payouts: dict[str, Any]) -> list[tuple[str, Decimal, str]]:
        """Every agentic-ledger credit a settled book owes: ledger-funded
        tickets, creators, agents (seeds, draw underwriting) and the house.
        Profile- and on-chain-funded tickets are never paid here."""
        from gaming.src.stack.agentic.ledger import TREASURY_WALLET

        out: list[tuple[str, Decimal, str]] = []

        def _add(wallet: Any, amount: Any, reason: str) -> None:
            amt = _d(amount or "0")
            if wallet and amt > 0:
                out.append((str(wallet), amt, reason))

        for bt in payouts.get("bettors") or []:
            if bet_funding(bt) == FUNDING_LEDGER:
                _add(ledger_wallet_of(bt.get("bettor_id")), bt.get("amount"), f"spectator_{bt.get('reason') or 'win'}")
        for c in payouts.get("creators") or []:
            _add(f"creator:{c['creator_id']}", c.get("amount"), "creator_fee_spectator")
        for sr in payouts.get("seed_refunds") or []:
            _add(sr.get("wallet"), sr.get("amount"), str(sr.get("reason") or "seed_refund"))
        for sp in (payouts.get("draw_book") or {}).get("agent_split") or []:
            _add(sp.get("wallet"), sp.get("amount"), "draw_underwrite_win")
        _add(TREASURY_WALLET, payouts.get("house_take"), "spectator_fee")
        return out

    @staticmethod
    def profile_payouts(payouts: dict[str, Any]) -> list[dict[str, Any]]:
        """Tickets paid back on the play balance (web / Telegram bettors)."""
        return [bt for bt in payouts.get("bettors") or [] if bet_funding(bt) == FUNDING_PROFILE]

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


def funded_seeds_from_ledger(match_id: str, wallet_a: str, wallet_b: str) -> dict[str, Decimal]:
    """The seeds the lock really debited for this table, per agent.

    Read from the ledger rows themselves (``spectator_seed`` / ``draw_seed``
    debits with ref=match_id), so a book whose lock never ran pays out no
    seed it never held.
    """
    from gaming.src.stack.agentic import ledger

    wa, wb = (wallet_a or "").lower(), (wallet_b or "").lower()
    out = {"a": 0, "b": 0, "draw_a": 0, "draw_b": 0}
    for t in ledger.txs(ref=match_id):
        if t.get("type") != "debit":
            continue
        w = str(t.get("wallet") or "").lower()
        side = "a" if w and w == wa else "b" if w and w == wb else None
        if side is None:
            continue
        reason = t.get("reason")
        if reason == "spectator_seed":
            out[side] += to_micro(t.get("amount") or "0")
        elif reason == "draw_seed":
            out[f"draw_{side}"] += to_micro(t.get("amount") or "0")
    return {k: Decimal(fmt(v)) for k, v in out.items()}
