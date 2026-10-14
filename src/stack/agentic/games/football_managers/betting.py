"""AFM spectator betting — a parimutuel USDC pot per fixture.

Spectators bet on the outcome (home / draw / away) while a fixture is open
(from matchday open until deadline). Stakes pool into a per-fixture pot
wallet; odds are the crowd's implied prices — `pot_total / pot_side` — and
shown per USDC staked. When the House resolves the matchday, winners split
the whole pot pro-rata to their stake on the winning side (minus the
platform's 7% fee, mirroring the chess spectator book) — losing stakes fund
the pool, exactly like the racetrack. No fixed odds, no house position: the
crowd prices itself.

State: data/agentic/afm_bets.json, written under the same BOARDMAN_AGENTIC_DATA
store as everything else in the game.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

_SIDES = ("home", "draw", "away")
CLOSE_OFFSET_HOURS = 0  # betting closes at the fixture deadline (open → deadline)
PLATFORM_FEE_BPS = 700  # mirrors the chess spectator book's platform fee
MIN_BET_USDC = Decimal("1")
MAX_BET_USDC = Decimal("50")

# ledger ids a bet must never debit (pots, party/agent wallets, the House)
_SYSTEM_WALLET_PREFIXES = ("afm_", "agent_", "0x", "house", "platform", "treasury", "boardman")

_BETS_FILE = "afm_bets.json"
_lock = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _d(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")


def _q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _side_total(book: dict[str, Any], side: str) -> Decimal:
    """Total staked on one side (book['stakes'] is {side: {better: amount}})."""
    stakers = (book.get("stakes") or {}).get(side) or {}
    return sum((_d(v) for v in stakers.values()), Decimal("0"))


# ---------------------------------------------------------------- store

def _load() -> dict[str, Any]:
    from gaming.src.stack.agentic.store import load_json

    return load_json(_BETS_FILE, {"fixtures": {}})


def _save(data: dict[str, Any]) -> None:
    from gaming.src.stack.agentic.store import save_json

    save_json(_BETS_FILE, data)


def _fixture_key(season_no: int, matchday: int, home: str, away: str) -> str:
    return f"s{int(season_no)}:md{int(matchday)}:{home}:{away}"


# ---------------------------------------------------------------- betting

def place_bet(
    better: str,
    season_no: int,
    matchday: int,
    home: str,
    away: str,
    side: str,
    amount: Any,
) -> dict[str, Any]:
    """Debit the better's wallet into the fixture pot; returns the receipt.

    `better` is a spectator id (e.g. a Telegram-linked profile id) and is
    debited directly, so it must be the authenticated caller (the API layer
    enforces that) and never a system wallet — pots, owner/creator party
    wallets, agents, the House.
    Betting is only allowed while the matchday is open and before its lock.
    """
    better = str(better or "").strip()
    if not better:
        raise ValueError("better is required")
    if ":" in better or better.lower().startswith(_SYSTEM_WALLET_PREFIXES):
        raise ValueError("better must be a spectator id, not a system wallet")
    side = str(side or "").strip().lower()
    if side not in _SIDES:
        raise ValueError(f"side must be one of {', '.join(_SIDES)}")
    amt = _d(amount)
    if amt < MIN_BET_USDC:
        raise ValueError(f"minimum bet is {MIN_BET_USDC} USDC")
    if amt > MAX_BET_USDC:
        raise ValueError(f"maximum bet is {MAX_BET_USDC} USDC")
    # Spectator-betting kill switch / allowlist, before anything is debited
    # (403/451, never a ValueError the route would turn into a 422).
    from gaming.src.backend.services.spectator_policy import assert_spectator_betting_allowed

    assert_spectator_betting_allowed(
        path="football.betting.place_bet",
        match_id=f"s{season_no}:md{matchday}:{home}:{away}",
        profile_id=better,
    )

    from gaming.src.stack.agentic.games.football_managers.season import (
        _deadline,
        _open_at,
        _state,
    )
    from gaming.src.stack.agentic.games.football_managers.league import (
        schedule_season,
    )

    with _lock:
        st = _state()
        s = st.get("season")
        if not s or int(s.get("season_no") or 0) != int(season_no):
            raise ValueError("no such season running")
        sched = schedule_season(list(s.get("division") or []))
        fixtures = sched[matchday - 1] if 0 <= matchday - 1 < len(sched) else []
        fixture = next(
            (
                f
                for f in fixtures
                if f.home_agent_id == home and f.away_agent_id == away
            ),
            None,
        )
        if fixture is None:
            raise ValueError("no such fixture on this matchday")
        if s.get("status") != "open":
            raise ValueError("season is not open")
        now = _now()
        if now < _open_at(s, matchday):
            raise ValueError("betting for this matchday is not open yet")
        if now >= _deadline(s, matchday):
            raise ValueError("betting is closed for this fixture")

        from gaming.src.stack.agentic import ledger as L

        pot = f"afm_fixture_s{int(season_no)}_md{int(matchday)}_{home}_{away}"
        L.debit(better, amt, reason="afm_spectator_bet", ref=pot)
        L.credit(pot, amt, reason="afm_spectator_bet", ref=pot)

        data = _load()
        fx = _fixture_key(season_no, matchday, home, away)
        book = data["fixtures"].setdefault(
            fx,
            {
                "season_no": int(season_no),
                "matchday": int(matchday),
                "home": home,
                "away": away,
                "stakes": {},
                "bets": [],
                "status": "open",
            },
        )
        stakes = book["stakes"].setdefault(side, {})
        stakes[better] = _d(stakes.get(better) or 0) + amt
        book["bets"].append(
            {
                "better": better,
                "side": side,
                "amount": str(amt),
                "at": _iso(now),
            }
        )
        _save(data)
        odds = current_odds(season_no, matchday, home, away)
        return {
            "ok": True,
            "fixture": fx,
            "side": side,
            "amount": str(amt),
            "odds_after": odds.get("odds", {}).get(side),
            "pot_total": odds.get("pot_total"),
        }


def current_odds(
    season_no: int,
    matchday: int,
    home: str,
    away: str,
) -> dict[str, Any]:
    """The parimutuel board for one fixture: pot per side + implied odds.

    Odds are decimal, per USDC staked (stake × odds returned on a win,
    platform fee already accounted for in the math). A side nobody backed
    shows odds 0 — there is nothing to win on it.
    """
    with _lock:
        data = _load()
        book = data["fixtures"].get(_fixture_key(season_no, matchday, home, away)) or {}
        stakes: dict[str, Decimal] = {side: _side_total(book, side) for side in _SIDES}
        total = sum(stakes.values())
        fee = Decimal(10000 - PLATFORM_FEE_BPS) / Decimal(10000)
        odds: dict[str, str] = {}
        for side in _SIDES:
            if total > 0 and stakes[side] > 0:
                odds[side] = str(_q2(total * fee / stakes[side]))
            else:
                odds[side] = "0"
        return {
            "season_no": int(season_no),
            "matchday": int(matchday),
            "home": home,
            "away": away,
            "pot_total": str(_q2(total)),
            "pot": {side: str(_q2(stakes[side])) for side in _SIDES},
            "odds": odds,
            "betters": len({b["better"] for b in book.get("bets") or []}),
            "status": str(book.get("status") or "open"),
        }


def season_boards(season_no: int, matchday: Optional[int] = None) -> list[dict[str, Any]]:
    """Odds boards for a matchday (or every open book of the season)."""
    with _lock:
        data = _load()
        out = []
        for fx, book in sorted(data["fixtures"].items()):
            if int(book.get("season_no") or 0) != int(season_no):
                continue
            if matchday is not None and int(book.get("matchday") or 0) != int(matchday):
                continue
            out.append(
                current_odds(
                    int(book["season_no"]),
                    int(book["matchday"]),
                    str(book["home"]),
                    str(book["away"]),
                )
            )
        return out


def _wallet_of(agent_id: str) -> str:
    from gaming.src.stack.agentic.registry import get_registry

    a = get_registry().get_agent(agent_id)
    return str((a or {}).get("wallet_address") or "")


def settle_matchday(season_no: int, matchday: int, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Settle every open book for the matchday against the real results.

    Winners split the pot pro-rata minus the platform fee; losing stakes
    stay in the pool (that is what parimutuel means). Called by the season
    resolve — idempotent (books flip to `settled`).
    """
    from gaming.src.stack.agentic import ledger as L

    settled: list[dict[str, Any]] = []
    with _lock:
        data = _load()
        for fx, book in data["fixtures"].items():
            if book.get("status") != "open":
                continue
            if int(book.get("season_no") or 0) != int(season_no) or int(book.get("matchday") or 0) != int(matchday):
                continue
            res = next(
                (
                    r
                    for r in results
                    if r.get("home_agent_id") == book.get("home")
                    and r.get("away_agent_id") == book.get("away")
                ),
                None,
            )
            if res is None:
                continue  # fixture not resolved yet — stays open
            hg, ag = int(res.get("home_goals") or 0), int(res.get("away_goals") or 0)
            winning = "home" if hg > ag else "away" if ag > hg else "draw"
            stakes: dict[str, Decimal] = {side: _side_total(book, side) for side in _SIDES}
            pot = f"afm_fixture_s{int(season_no)}_md{int(matchday)}_{book.get('home')}_{book.get('away')}"
            pot_total = sum(stakes.values())
            paid = Decimal("0")
            payouts: dict[str, str] = {}

            if pot_total > 0:
                fee = (pot_total * Decimal(PLATFORM_FEE_BPS) / Decimal(10000)).quantize(Decimal("0.000001"))
                distributable = pot_total - fee
                if stakes[winning] > 0:
                    for better, st in (book.get("stakes", {}).get(winning) or {}).items():
                        share = (distributable * _d(st) / stakes[winning]).quantize(Decimal("0.000001"))
                        if share > 0:
                            L.credit(better, share, reason="afm_bet_payout", ref=fx)
                            payouts[better] = str(share)
                            paid += share
                # only rounding dust can remain — the winners' shares sum to
                # distributable, and losing stakes fund the pool by design
                dust = pot_total - paid
                if dust > 0:
                    L.credit(
                        f"afm_season_{int(season_no)}_pot",
                        dust,
                        reason="afm_bet_unbacked",
                        ref=fx,
                    )
                try:
                    L.debit(pot, pot_total, reason="afm_bet_settle", ref=fx)
                except Exception:
                    pass  # pot short — ledger drift; never block the season

            book["status"] = "settled"
            book["result"] = {"home_goals": hg, "away_goals": ag, "winning_side": winning}
            book["payouts"] = payouts
            book["settled_at"] = _iso(_now())
            settled.append({"fixture": fx, "winning_side": winning, "payouts": payouts})
        _save(data)
    return settled


# ---------------------------------------------------------------- views

def my_bets(better: str, season_no: Optional[int] = None) -> list[dict[str, Any]]:
    """A spectator's bets with the current (or final) odds beside each."""
    with _lock:
        data = _load()
        out = []
        for fx, book in sorted(data["fixtures"].items()):
            if season_no is not None and int(book.get("season_no") or 0) != int(season_no):
                continue
            for b in book.get("bets") or []:
                if b.get("better") != better:
                    continue
                out.append(
                    {
                        "fixture": fx,
                        "season_no": book["season_no"],
                        "matchday": book["matchday"],
                        "home": book["home"],
                        "away": book["away"],
                        "side": b["side"],
                        "amount": b["amount"],
                        "at": b["at"],
                        "status": book.get("status"),
                        "winning_side": (book.get("result") or {}).get("winning_side"),
                    }
                )
        return out


def close_stale_books(max_hours: float = 6.0) -> int:
    """Guard: books whose matchday never resolved within a window flip to
    `closed` (stake refunds) instead of holding funds forever."""
    from gaming.src.stack.agentic import ledger as L

    n = 0
    with _lock:
        data = _load()
        cutoff = _now() - timedelta(hours=max_hours)
        for fx, book in data["fixtures"].items():
            if book.get("status") != "open":
                continue
            deadline = book.get("deadline_at")
            if not deadline:
                continue
            try:
                if datetime.fromisoformat(str(deadline).replace("Z", "+00:00")) > cutoff:
                    continue
            except Exception:
                continue
            # refund everything on the book
            for side, stakers in (book.get("stakes") or {}).items():
                for better, st in (stakers or {}).items():
                    if _d(st) > 0:
                        L.credit(better, _d(st), reason="afm_bet_refund", ref=fx)
            pot_total = sum(_d(v) for stakers in (book.get("stakes") or {}).values() for v in (stakers or {}).values())
            pot = f"afm_fixture_s{int(book.get('season_no') or 0)}_md{int(book.get('matchday') or 0)}_{book.get('home')}_{book.get('away')}"
            if pot_total > 0:
                try:
                    L.debit(pot, pot_total, reason="afm_bet_close", ref=fx)
                except Exception:
                    pass
            book["status"] = "closed"
            book["settled_at"] = _iso(_now())
            n += 1
        _save(data)
    return n
