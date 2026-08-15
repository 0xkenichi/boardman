"""
Rematch Tournament Mode v0 — Model A entry pool, T4/T8 brackets.

Money is OFF until TOURNAMENTS_MONEY_LIVE=1 (and tables/escrow ready).
Local JSON store works without SQL; Supabase used when tables exist.

See docs/TOURNAMENT_MODE.md.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import secrets
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PRESETS = (4, 8, 16)
DEFAULT_PAYOUT = {"1": 0.65, "2": 0.20, "3": 0.15}
DEFAULT_FEE_BPS = 1000  # 10%

_STORE_PATH = Path(
    os.getenv(
        "TOURNAMENT_STORE_PATH",
        str(Path(__file__).resolve().parents[3] / "data" / "tournaments.json"),
    )
)
_lock = threading.RLock()
_use_supabase: Optional[bool] = None  # None = probe later


def tournaments_enabled() -> bool:
    v = (os.getenv("TOURNAMENTS_ENABLED") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def money_live() -> bool:
    """When false: seats are RSVPs only — no USDC lock/payout."""
    v = (os.getenv("TOURNAMENTS_MONEY_LIVE") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _code(n: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


class TournamentError(Exception):
    pass


# ── Bracket ──────────────────────────────────────────────────────────────────


def build_bracket(player_ids: list[str]) -> list[dict[str, Any]]:
    """Single-elim bracket. player_ids length must be 4, 8, or 16."""
    n = len(player_ids)
    if n not in PRESETS:
        raise TournamentError(f"Bracket size must be one of {PRESETS}, got {n}")
    players = list(player_ids)
    random.shuffle(players)
    rounds = int(math.log2(n))
    matches: list[dict[str, Any]] = []

    # Round 1 — pair adjacent
    r1_count = n // 2
    for i in range(r1_count):
        matches.append(
            {
                "match_key": f"R1-M{i}",
                "round": 1,
                "index": i,
                "player_a": players[i * 2],
                "player_b": players[i * 2 + 1],
                "winner_id": None,
                "status": "ready",
                "challenge_id": None,
                "next_key": f"R2-M{i // 2}" if rounds >= 2 else None,
                "next_slot": "a" if i % 2 == 0 else "b",
            }
        )

    # Later rounds empty until fed
    for r in range(2, rounds + 1):
        count = n // (2**r)
        for i in range(count):
            next_key = f"R{r + 1}-M{i // 2}" if r < rounds else None
            next_slot = ("a" if i % 2 == 0 else "b") if next_key else None
            matches.append(
                {
                    "match_key": f"R{r}-M{i}",
                    "round": r,
                    "index": i,
                    "player_a": None,
                    "player_b": None,
                    "winner_id": None,
                    "status": "pending",
                    "challenge_id": None,
                    "next_key": next_key,
                    "next_slot": next_slot,
                }
            )

    # Optional 3rd-place for T8+ (semifinal losers)
    if n >= 8:
        matches.append(
            {
                "match_key": "R3RD-M0",
                "round": rounds,  # same depth as final conceptually
                "index": 0,
                "player_a": None,
                "player_b": None,
                "winner_id": None,
                "status": "pending",
                "challenge_id": None,
                "next_key": None,
                "next_slot": None,
                "is_third_place": True,
            }
        )

    return matches


def compute_payouts(
    pot: Decimal,
    fee_bps: int,
    places: dict[str, str],
    payout_card: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """
    places: {"1": profile_id, "2": ..., "3": ...}
    Returns list of {profile_id, place, amount_usdc, fee_share_note}
    """
    card = payout_card or DEFAULT_PAYOUT
    fee = (pot * Decimal(fee_bps) / Decimal(10000)).quantize(Decimal("0.01"))
    distributable = pot - fee
    out: list[dict[str, Any]] = []
    for place_str, share in card.items():
        pid = places.get(str(place_str))
        if not pid:
            continue
        amt = (distributable * Decimal(str(share))).quantize(Decimal("0.01"))
        out.append(
            {
                "profile_id": pid,
                "place": int(place_str),
                "amount_usdc": float(amt),
                "share": float(share),
            }
        )
    return [
        {
            "platform_fee_usdc": float(fee),
            "pot_usdc": float(pot),
            "distributable_usdc": float(distributable),
            "places": out,
            "money_live": money_live(),
            "paid": False,
        }
    ]


# ── Store ────────────────────────────────────────────────────────────────────


def _empty_store() -> dict:
    return {"tournaments": {}, "entries": {}}


def _load_json() -> dict:
    with _lock:
        if not _STORE_PATH.exists():
            return _empty_store()
        try:
            raw = json.loads(_STORE_PATH.read_text())
            if not isinstance(raw, dict):
                return _empty_store()
            raw.setdefault("tournaments", {})
            raw.setdefault("entries", {})
            return raw
        except Exception:
            logger.exception("[Tournament] load store failed")
            return _empty_store()


def _save_json(data: dict) -> None:
    with _lock:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STORE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))
        tmp.replace(_STORE_PATH)


def _sb():
    from backend.supabase_client import get_supabase

    return get_supabase()


def _probe_supabase() -> bool:
    global _use_supabase
    if _use_supabase is not None:
        return _use_supabase
    if (os.getenv("TOURNAMENT_FORCE_JSON") or "").strip() in ("1", "true", "yes"):
        _use_supabase = False
        return False
    try:
        _sb().schema("gaming").table("tournaments").select("id").limit(1).execute()
        _use_supabase = True
        logger.info("[Tournament] Using Supabase gaming.tournaments")
    except Exception as exc:
        _use_supabase = False
        logger.info("[Tournament] Supabase tables missing — JSON store (%s)", exc)
    return _use_supabase


# ── CRUD ─────────────────────────────────────────────────────────────────────


def create_tournament(
    *,
    host_profile_id: Optional[str],
    game_id: str,
    preset: int,
    entry_usdc: float,
    title: str = "Boardman Cup",
    visibility: str = "public",
    chain_id: str = "arc",
    fee_bps: int = DEFAULT_FEE_BPS,
    payout_card: Optional[dict] = None,
    partner_code: Optional[str] = None,
) -> dict[str, Any]:
    if not tournaments_enabled():
        raise TournamentError("Tournaments are disabled (TOURNAMENTS_ENABLED=0)")
    if preset not in PRESETS:
        raise TournamentError(f"preset must be one of {PRESETS}")
    if entry_usdc < 0:
        raise TournamentError("entry_usdc must be >= 0")
    if visibility not in ("public", "private"):
        raise TournamentError("visibility must be public or private")

    meta: dict[str, Any] = {"model": "A_entry_pool", "v": 0}
    if partner_code:
        try:
            from gaming.src.backend.services.partners import get_partner, normalize_partner_code

            pc = normalize_partner_code(partner_code)
            partner = get_partner(pc) if pc else None
            if not partner:
                raise TournamentError(f"Unknown partner/center code: {partner_code}")
            meta["partner_code"] = partner["code"]
            meta["partner_name"] = partner.get("display_name")
        except TournamentError:
            raise
        except Exception as exc:
            logger.warning("[Tournament] partner resolve failed: %s", exc)
            meta["partner_code"] = str(partner_code).strip().upper()

    tid = str(uuid.uuid4())
    code = _code(6)
    now = _now()
    row = {
        "id": tid,
        "code": code,
        "host_profile_id": host_profile_id,
        "title": (title or "Boardman Cup")[:80],
        "game_id": game_id,
        "preset": int(preset),
        "entry_usdc": float(entry_usdc),
        "fee_bps": int(fee_bps),
        "payout_card": payout_card or dict(DEFAULT_PAYOUT),
        "status": "open",
        "visibility": visibility,
        "chain_id": chain_id or "arc",
        "money_live": money_live(),
        "pot_usdc": 0.0,
        "bracket": [],
        "payouts": [],
        "metadata": meta,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "entries": [],  # embedded for JSON convenience
    }

    if _probe_supabase():
        try:
            insert = {k: v for k, v in row.items() if k != "entries"}
            _sb().schema("gaming").table("tournaments").insert(insert).execute()
        except Exception as exc:
            logger.warning("[Tournament] Supabase insert failed, JSON fallback: %s", exc)
            global _use_supabase
            _use_supabase = False

    if not _use_supabase:
        data = _load_json()
        data["tournaments"][tid] = row
        data["entries"][tid] = []
        _save_json(data)

    logger.info(
        "[Tournament] created code=%s preset=%s entry=%s money_live=%s",
        code,
        preset,
        entry_usdc,
        money_live(),
    )
    return get_tournament(tid) or row


def _json_get(tid: str) -> Optional[dict]:
    data = _load_json()
    t = data["tournaments"].get(tid)
    if not t:
        return None
    t = deepcopy(t)
    t["entries"] = deepcopy(data["entries"].get(tid) or [])
    return t


def get_tournament(ref: str) -> Optional[dict[str, Any]]:
    """By UUID or public code."""
    ref = (ref or "").strip()
    if not ref:
        return None

    if _probe_supabase():
        try:
            sb = _sb().schema("gaming")
            q = sb.table("tournaments").select("*")
            if len(ref) == 36 and "-" in ref:
                r = q.eq("id", ref).limit(1).execute()
            else:
                r = q.eq("code", ref.upper()).limit(1).execute()
            row = (r.data or [None])[0]
            if not row:
                return None
            er = (
                sb.table("tournament_entries")
                .select("*")
                .eq("tournament_id", row["id"])
                .execute()
            )
            row["entries"] = er.data or []
            return row
        except Exception:
            logger.exception("[Tournament] get supabase failed")

    data = _load_json()
    for tid, t in data["tournaments"].items():
        if tid == ref or str(t.get("code", "")).upper() == ref.upper():
            out = deepcopy(t)
            out["entries"] = deepcopy(data["entries"].get(tid) or [])
            return out
    return None


def list_tournaments(
    *,
    status: Optional[str] = None,
    visibility: Optional[str] = "public",
    limit: int = 20,
) -> list[dict]:
    out: list[dict] = []
    if _probe_supabase():
        try:
            q = _sb().schema("gaming").table("tournaments").select("*").order(
                "created_at", desc=True
            ).limit(limit)
            if status:
                q = q.eq("status", status)
            if visibility:
                q = q.eq("visibility", visibility)
            r = q.execute()
            for row in r.data or []:
                row["entries"] = []
                out.append(row)
            return out
        except Exception:
            logger.exception("[Tournament] list supabase failed")

    data = _load_json()
    for tid, t in data["tournaments"].items():
        if status and t.get("status") != status:
            continue
        if visibility and t.get("visibility") != visibility:
            continue
        item = deepcopy(t)
        item["entries"] = deepcopy(data["entries"].get(tid) or [])
        out.append(item)
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return out[:limit]


async def join_tournament(ref: str, profile_id: str) -> dict[str, Any]:
    t = get_tournament(ref)
    if not t:
        raise TournamentError("Tournament not found")
    if t.get("status") != "open":
        raise TournamentError(f"Tournament is {t.get('status')} — not open for join")
    entries = t.get("entries") or []
    if any(e.get("profile_id") == profile_id for e in entries):
        raise TournamentError("You already joined this cup")
    if len(entries) >= int(t["preset"]):
        raise TournamentError("Cup is full")

    entry_fee = float(t.get("entry_usdc") or 0)
    entry_tx = None
    amount_locked = 0.0
    seat = "joined"

    if money_live() and entry_fee > 0:
        try:
            from gaming.src.backend.services.tournament_money import (
                TournamentMoneyError,
                lock_entry,
            )
            from decimal import Decimal

            pay = await lock_entry(
                profile_id, Decimal(str(entry_fee)), cup_code=str(t.get("code") or "")
            )
            entry_tx = pay.get("tx_hash")
            amount_locked = float(pay.get("amount_usdc") or entry_fee)
            seat = "locked"
        except Exception as exc:
            # Re-raise as TournamentError for bot copy
            from gaming.src.backend.services.tournament_money import TournamentMoneyError

            if isinstance(exc, TournamentMoneyError):
                raise TournamentError(str(exc)) from exc
            logger.exception("[Tournament] money join failed")
            raise TournamentError(f"Could not lock entry: {exc}") from exc
    elif money_live() and entry_fee <= 0:
        seat = "locked"

    entry = {
        "id": str(uuid.uuid4()),
        "tournament_id": t["id"],
        "profile_id": profile_id,
        "seat_status": seat,
        "entry_tx_hash": entry_tx,
        "amount_usdc": amount_locked if money_live() else 0.0,
        "created_at": _now(),
    }

    new_count = len(entries) + 1
    pot = new_count * entry_fee

    if _probe_supabase() and _use_supabase:
        try:
            _sb().schema("gaming").table("tournament_entries").insert(entry).execute()
            _sb().schema("gaming").table("tournaments").update(
                {"pot_usdc": pot, "updated_at": _now(), "money_live": money_live()}
            ).eq("id", t["id"]).execute()
            return get_tournament(t["id"])  # type: ignore
        except Exception:
            logger.exception("[Tournament] join supabase failed")

    data = _load_json()
    tid = t["id"]
    data["entries"].setdefault(tid, []).append(entry)
    if tid in data["tournaments"]:
        data["tournaments"][tid]["pot_usdc"] = pot
        data["tournaments"][tid]["updated_at"] = _now()
        data["tournaments"][tid]["money_live"] = money_live()
    _save_json(data)
    return get_tournament(tid)  # type: ignore


async def leave_tournament(ref: str, profile_id: str) -> dict[str, Any]:
    t = get_tournament(ref)
    if not t:
        raise TournamentError("Tournament not found")
    if t.get("status") != "open":
        raise TournamentError("Can only leave while cup is open")
    tid = t["id"]
    mine = next(
        (e for e in (t.get("entries") or []) if e.get("profile_id") == profile_id),
        None,
    )
    if not mine:
        raise TournamentError("You are not in this cup")

    if money_live() and float(mine.get("amount_usdc") or t.get("entry_usdc") or 0) > 0:
        try:
            from gaming.src.backend.services.tournament_money import (
                TournamentMoneyError,
                refund_entry,
            )
            from decimal import Decimal

            await refund_entry(
                profile_id,
                Decimal(str(mine.get("amount_usdc") or t.get("entry_usdc") or 0)),
                cup_code=str(t.get("code") or ""),
                entry_tx_hash=mine.get("entry_tx_hash"),
            )
        except Exception as exc:
            from gaming.src.backend.services.tournament_money import TournamentMoneyError

            if isinstance(exc, TournamentMoneyError):
                raise TournamentError(str(exc)) from exc
            logger.exception("[Tournament] refund failed")
            raise TournamentError(f"Refund failed: {exc}") from exc

    entries = [e for e in (t.get("entries") or []) if e.get("profile_id") != profile_id]
    entry_fee = float(t.get("entry_usdc") or 0)
    pot = len(entries) * entry_fee

    if _probe_supabase() and _use_supabase:
        try:
            _sb().schema("gaming").table("tournament_entries").delete().eq(
                "tournament_id", tid
            ).eq("profile_id", profile_id).execute()
            _sb().schema("gaming").table("tournaments").update(
                {"pot_usdc": pot, "updated_at": _now()}
            ).eq("id", tid).execute()
            return get_tournament(tid)  # type: ignore
        except Exception:
            logger.exception("[Tournament] leave supabase failed")

    data = _load_json()
    data["entries"][tid] = [
        e for e in data["entries"].get(tid, []) if e.get("profile_id") != profile_id
    ]
    if tid in data["tournaments"]:
        data["tournaments"][tid]["pot_usdc"] = pot
        data["tournaments"][tid]["updated_at"] = _now()
    _save_json(data)
    return get_tournament(tid)  # type: ignore


def start_tournament(ref: str, *, force: bool = False) -> dict[str, Any]:
    t = get_tournament(ref)
    if not t:
        raise TournamentError("Tournament not found")
    if t.get("status") not in ("open", "locked"):
        raise TournamentError(f"Cannot start from status {t.get('status')}")
    entries = t.get("entries") or []
    preset = int(t["preset"])
    if len(entries) < preset and not force:
        raise TournamentError(
            f"Need {preset} players (have {len(entries)}). "
            "Wait for full roster or force-start (ops only, not for real money)."
        )
    if len(entries) < 2:
        raise TournamentError("Need at least 2 players")
    # Force only with power-of-two by trimming or padding is bad — require exact or force with exact 4/8
    n = len(entries)
    if n not in PRESETS:
        if force and n >= 4:
            # trim to next lower preset
            target = max(p for p in PRESETS if p <= n)
            entries = entries[:target]
            n = target
        else:
            raise TournamentError(f"Player count {n} not a preset {PRESETS}")

    # Money live: do not force-start underfilled cups
    if money_live() and force and n < preset:
        raise TournamentError("Cannot force-start underfilled cups when money is live")

    player_ids = [e["profile_id"] for e in entries[:n]]
    bracket = build_bracket(player_ids)
    pot = n * float(t.get("entry_usdc") or 0)
    now = _now()

    if _probe_supabase() and _use_supabase:
        try:
            _sb().schema("gaming").table("tournaments").update(
                {
                    "status": "live",
                    "bracket": bracket,
                    "pot_usdc": pot,
                    "started_at": now,
                    "updated_at": now,
                    "preset": n,
                }
            ).eq("id", t["id"]).execute()
            t_live = get_tournament(t["id"])  # type: ignore
        except Exception:
            logger.exception("[Tournament] start supabase failed")
            t_live = None
    else:
        t_live = None

    if not t_live:
        data = _load_json()
        tid = t["id"]
        if tid in data["tournaments"]:
            data["tournaments"][tid]["status"] = "live"
            data["tournaments"][tid]["bracket"] = bracket
            data["tournaments"][tid]["pot_usdc"] = pot
            data["tournaments"][tid]["started_at"] = now
            data["tournaments"][tid]["updated_at"] = now
            data["tournaments"][tid]["preset"] = n
            # trim entries if force
            data["entries"][tid] = [
                e for e in data["entries"].get(tid, []) if e.get("profile_id") in player_ids
            ]
        _save_json(data)
        t_live = get_tournament(tid)  # type: ignore

    # Spawn $0 1v1 challenges for R1 and notify
    try:
        from gaming.src.backend.services.tournament_matches import (
            attach_challenges_to_ready_matches,
        )

        t_live = attach_challenges_to_ready_matches(t_live or t)
    except Exception:
        logger.exception("[Tournament] spawn R1 challenges failed")

    return t_live or get_tournament(t["id"])  # type: ignore


def _save_bracket(tid: str, bracket: list, extra: Optional[dict] = None) -> None:
    extra = extra or {}
    extra["bracket"] = bracket
    extra["updated_at"] = _now()
    if _probe_supabase() and _use_supabase:
        try:
            _sb().schema("gaming").table("tournaments").update(extra).eq("id", tid).execute()
            return
        except Exception:
            logger.exception("[Tournament] save bracket supabase failed")
    data = _load_json()
    if tid in data["tournaments"]:
        data["tournaments"][tid].update(extra)
    _save_json(data)


def report_match_winner(
    ref: str,
    match_key: str,
    winner_profile_id: str,
) -> dict[str, Any]:
    """Ops or auto-settle: set winner of a bracket match and feed next round."""
    t = get_tournament(ref)
    if not t:
        raise TournamentError("Tournament not found")
    if t.get("status") != "live":
        raise TournamentError("Tournament is not live")
    bracket = list(t.get("bracket") or [])
    m = next((x for x in bracket if x.get("match_key") == match_key), None)
    if not m:
        raise TournamentError(f"Match {match_key} not found")
    if m.get("status") == "done":
        raise TournamentError("Match already done")
    a, b = m.get("player_a"), m.get("player_b")
    if not a or not b:
        raise TournamentError("Match not ready (waiting for players)")
    if winner_profile_id not in (a, b):
        raise TournamentError("Winner must be player_a or player_b")

    m["winner_id"] = winner_profile_id
    m["status"] = "done"
    loser = b if winner_profile_id == a else a

    # Feed next match
    nk, ns = m.get("next_key"), m.get("next_slot")
    if nk:
        nxt = next((x for x in bracket if x.get("match_key") == nk), None)
        if nxt:
            if ns == "a":
                nxt["player_a"] = winner_profile_id
            else:
                nxt["player_b"] = winner_profile_id
            if nxt.get("player_a") and nxt.get("player_b"):
                nxt["status"] = "ready"

    # Feed 3rd place from semis (round before final)
    rounds = int(math.log2(int(t["preset"])))
    if m.get("round") == rounds - 1 and not m.get("is_third_place"):
        third = next((x for x in bracket if x.get("is_third_place")), None)
        if third and loser:
            if not third.get("player_a"):
                third["player_a"] = loser
            elif not third.get("player_b"):
                third["player_b"] = loser
            if third.get("player_a") and third.get("player_b"):
                third["status"] = "ready"

    # Final done? → places
    final_key = f"R{rounds}-M0"
    final = next((x for x in bracket if x.get("match_key") == final_key), None)
    third = next((x for x in bracket if x.get("is_third_place")), None)
    finished = False
    payouts: list = []
    if final and final.get("status") == "done":
        # Wait for 3rd if present and both players set
        third_ok = True
        if third and third.get("player_a") and third.get("player_b"):
            third_ok = third.get("status") == "done"
        elif third and (third.get("player_a") or third.get("player_b")):
            third_ok = third.get("status") == "done" or not (
                third.get("player_a") and third.get("player_b")
            )
        if third_ok or not third:
            places = {
                "1": final.get("winner_id"),
                "2": final.get("player_b")
                if final.get("winner_id") == final.get("player_a")
                else final.get("player_a"),
            }
            if third and third.get("winner_id"):
                places["3"] = third.get("winner_id")
            pot = Decimal(str(t.get("pot_usdc") or 0))
            # If pot 0 but entry set, recompute
            if pot <= 0:
                pot = Decimal(str(t.get("entry_usdc") or 0)) * Decimal(int(t["preset"]))
            payouts = compute_payouts(
                pot,
                int(t.get("fee_bps") or DEFAULT_FEE_BPS),
                places,
                t.get("payout_card"),
            )
            finished = True

    extra: dict[str, Any] = {}
    if finished:
        extra["status"] = "final"
        extra["finished_at"] = _now()
        extra["payouts"] = payouts

    _save_bracket(t["id"], bracket, extra)
    t_out = get_tournament(t["id"])  # type: ignore

    # Spawn next-round challenges when new matches became ready
    if not finished:
        try:
            from gaming.src.backend.services.tournament_matches import (
                attach_challenges_to_ready_matches,
            )

            t_out = attach_challenges_to_ready_matches(t_out or t)
        except Exception:
            logger.exception("[Tournament] spawn next challenges failed")

    return t_out


async def finalize_tournament_payouts(ref: str) -> dict[str, Any]:
    """Pay place prizes when cup is final (money live). Idempotent-ish."""
    t = get_tournament(ref)
    if not t:
        raise TournamentError("Tournament not found")
    if t.get("status") != "final":
        raise TournamentError("Cup is not final yet")
    payouts = list(t.get("payouts") or [])
    if not payouts:
        return t
    block = payouts[0]
    if block.get("paid"):
        return t
    if not money_live():
        return t
    from gaming.src.backend.services.tournament_money import pay_payouts

    paid_block = await pay_payouts(block, cup_code=str(t.get("code") or ""))
    payouts[0] = paid_block
    _save_bracket(t["id"], list(t.get("bracket") or []), {"payouts": payouts})
    return get_tournament(t["id"])  # type: ignore


async def cancel_tournament(ref: str, reason: str = "") -> dict[str, Any]:
    t = get_tournament(ref)
    if not t:
        raise TournamentError("Tournament not found")
    if t.get("status") in ("final", "cancelled"):
        raise TournamentError(f"Already {t.get('status')}")

    # Refund locked entries while open (or anytime pre-final)
    if money_live() and t.get("status") in ("open", "locked", "live"):
        from gaming.src.backend.services.tournament_money import refund_entry
        from decimal import Decimal

        for e in t.get("entries") or []:
            amt = float(e.get("amount_usdc") or t.get("entry_usdc") or 0)
            if amt <= 0:
                continue
            try:
                await refund_entry(
                    e["profile_id"],
                    Decimal(str(amt)),
                    cup_code=str(t.get("code") or ""),
                    entry_tx_hash=e.get("entry_tx_hash"),
                )
            except Exception:
                logger.exception(
                    "[Tournament] cancel refund failed for %s", e.get("profile_id")
                )

    extra = {
        "status": "cancelled",
        "updated_at": _now(),
        "metadata": {
            **(t.get("metadata") or {}),
            "cancel_reason": reason or "ops",
        },
    }
    if _probe_supabase() and _use_supabase:
        try:
            _sb().schema("gaming").table("tournaments").update(extra).eq(
                "id", t["id"]
            ).execute()
            return get_tournament(t["id"])  # type: ignore
        except Exception:
            logger.exception("[Tournament] cancel supabase failed")
    data = _load_json()
    tid = t["id"]
    if tid in data["tournaments"]:
        data["tournaments"][tid]["status"] = "cancelled"
        data["tournaments"][tid]["updated_at"] = _now()
        meta = data["tournaments"][tid].get("metadata") or {}
        meta["cancel_reason"] = reason or "ops"
        data["tournaments"][tid]["metadata"] = meta
    _save_json(data)
    return get_tournament(tid)  # type: ignore


def format_tournament_card(t: dict, *, tags: Optional[dict[str, str]] = None) -> str:
    """HTML card for Telegram."""
    tags = tags or {}
    code = t.get("code") or "?"
    status = t.get("status") or "?"
    preset = t.get("preset")
    entry = float(t.get("entry_usdc") or 0)
    entries = t.get("entries") or []
    n = len(entries)
    pot = float(t.get("pot_usdc") or n * entry)
    money = "💵 LIVE" if t.get("money_live") or money_live() else "🧪 dry-run (no USDC yet)"
    game = t.get("game_id") or "?"
    title = t.get("title") or "Cup"

    lines = [
        f"🏆 <b>{_esc(title)}</b>",
        f"Code: <code>{_esc(code)}</code> · {money}",
        f"Game: <b>{_esc(str(game))}</b>",
        f"Size: <b>{n}/{preset}</b> · Entry: <b>${entry:,.2f}</b> · Pot ~${pot:,.2f}",
        f"Status: <b>{_esc(status)}</b>",
        f"Fee: {int(t.get('fee_bps') or DEFAULT_FEE_BPS) / 100:.0f}% · "
        f"Payout 65/20/15 after fee",
    ]
    meta = t.get("metadata") or {}
    if meta.get("partner_code"):
        pname = meta.get("partner_name") or meta.get("partner_code")
        lines.append(f"🏪 Center: <b>{_esc(pname)}</b> (<code>{_esc(meta.get('partner_code'))}</code>)")
    if entries:
        lines.append("\n<b>Roster</b>")
        for i, e in enumerate(entries, 1):
            pid = e.get("profile_id") or ""
            tag = tags.get(pid) or pid[:8]
            lines.append(f"{i}. @{_esc(tag)}")
    if status == "live" and t.get("bracket"):
        lines.append("\n<b>Ready matches</b>")
        for m in t["bracket"]:
            if m.get("status") != "ready":
                continue
            a = tags.get(m.get("player_a") or "", (m.get("player_a") or "?")[:8])
            b = tags.get(m.get("player_b") or "", (m.get("player_b") or "?")[:8])
            lines.append(f"· <code>{m['match_key']}</code> @{_esc(a)} vs @{_esc(b)}")
    if status == "final" and t.get("payouts"):
        lines.append("\n<b>Results</b>")
        block = (t["payouts"] or [{}])[0]
        for p in block.get("places") or []:
            pid = p.get("profile_id") or ""
            tag = tags.get(pid) or pid[:8]
            lines.append(
                f"#{p.get('place')} @{_esc(tag)} · ${float(p.get('amount_usdc') or 0):,.2f}"
            )
        lines.append(f"Platform fee: ${float(block.get('platform_fee_usdc') or 0):,.2f}")
        if not block.get("paid"):
            lines.append("<i>Payouts recorded — money rail not sent (dry-run)</i>")
    lines.append(
        f"\nJoin: <code>/tjoin {code}</code> · deep link <code>cup_{code}</code>\n"
        f"Status: <code>/tstatus {code}</code>"
    )
    return "\n".join(lines)


def cup_deep_link(code: str, bot_url: Optional[str] = None) -> str:
    """t.me deep link for QR / share."""
    base = (bot_url or os.getenv("TELEGRAM_BOT_URL") or "https://t.me/myboardmanOfficialBot").rstrip(
        "/"
    )
    c = (code or "").strip().upper()
    if not c:
        return base
    return f"{base}?start=cup_{c}"


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def ready_matches(t: dict) -> list[dict]:
    return [m for m in (t.get("bracket") or []) if m.get("status") == "ready"]
