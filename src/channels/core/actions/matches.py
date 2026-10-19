"""Skill-match services shared by the Telegram handlers and the core flows.

This is the orchestration that used to live inside aiogram callbacks
(CHANNELS_DESIGN §3.1): who may act, which checks run in which order, and
the ``gaming.challenges`` writes. Telegram handlers call these and keep their
own copy (HTML, keyboards); core flows call the same functions and render
channel-free messages. Refusals raise ``MatchRefused`` with a ``kind`` the
caller maps to its own wording, plus a plain-text default.

The money itself still moves only through the existing services:
``clawstation_escrow`` (lock), ``clawstation_settlement`` (payout, disputes),
``rematch_cancel`` (refunds) and the ``safety`` gates.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("open", "accepted", "creator_locked", "locked", "playing", "submitted", "disputed")
REPORTABLE = ("locked", "creator_locked", "submitted", "playing", "accepted")
DISPUTABLE = ("submitted", "locked", "creator_locked", "playing", "disputed")

_TAG = re.compile(r"<[^>]+>")


def plain(html_text: str) -> str:
    """Telegram HTML (``<b>``, ``<code>``) → the core's ``*bold*`` markup."""
    import html as _html

    s = re.sub(r"</?b>", "*", html_text or "")
    s = re.sub(r"</?code>", "`", s)
    s = _TAG.sub("", s)
    return _html.unescape(s).strip()


class MatchRefused(Exception):
    """A refusal the caller words itself; ``message`` is a plain-text default."""

    def __init__(self, kind: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail


def _sb():
    from backend.supabase_client import get_supabase

    return get_supabase()


def _challenges():
    return _sb().schema("gaming").table("challenges")


# ── reading ──────────────────────────────────────────────────────────────────


def load(ref: str) -> Optional[dict]:
    """By UUID or public match code (sync: call off the event loop)."""
    from gaming.src.backend.services.match_codes import load_challenge_by_ref

    if not ref:
        return None
    return load_challenge_by_ref(str(ref))


def role(ch: dict, profile_id: Optional[str]) -> Optional[str]:
    if not profile_id or not ch:
        return None
    if str(profile_id) == str(ch.get("creator_id")):
        return "creator"
    if ch.get("opponent_id") and str(profile_id) == str(ch.get("opponent_id")):
        return "opponent"
    return None


def other_party(ch: dict, profile_id: str) -> Optional[str]:
    r = role(ch, profile_id)
    if r == "creator":
        return ch.get("opponent_id")
    if r == "opponent":
        return ch.get("creator_id")
    return None


def code_of(ch: dict) -> str:
    from gaming.src.backend.services.match_codes import display_code, ensure_public_code

    try:
        return ensure_public_code(ch)
    except Exception:
        return display_code(ch)


def list_mine(profile_id: str, *, limit: int = 10) -> list[dict]:
    """Unfinished matches this profile is in, newest first (sync)."""
    from gaming.src.backend.services.challenge_compat import normalize_list

    rows: dict[str, dict] = {}
    for col in ("issuer_id", "target_id"):
        try:
            r = (
                _challenges().select("*").eq(col, profile_id)
                .in_("status", list(ACTIVE_STATUSES)).order("created_at", desc=True)
                .limit(limit).execute()
            )
            for row in normalize_list(getattr(r, "data", None) or []):
                rows[str(row["id"])] = row
        except Exception:
            logger.warning("[matches] list query on %s failed", col, exc_info=True)
    out = sorted(rows.values(), key=lambda c: str(c.get("created_at") or ""), reverse=True)
    return out[:limit]


# ── create ───────────────────────────────────────────────────────────────────


def insert_challenge(
    *,
    creator_id: str,
    opponent_id: Optional[str],
    amount: Decimal,
    game: str,
    visibility: str,
    settlement_chain: Optional[str] = None,
    message: str = "Boardman challenge",
    expires_hours: int = 24,
) -> dict:
    """Insert one ``open`` challenge; retries once without ``settlement_chain``
    (older live schemas lack the column). Never writes ``public_code``.

    Money realms: the chain comes from ``realms.resolve_challenge_chain``
    (real money when the humans realm is live, practice otherwise; a real
    chain can't be asked for before it is live). A real-money challenge is
    never written without its chain: no retry without the column."""
    from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge
    from gaming.src.backend.services.match_codes import display_code
    from gaming.src.backend.services.realms import is_real_chain, resolve_challenge_chain

    settlement_chain = resolve_challenge_chain(settlement_chain)
    challenge_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    record = denormalize_challenge({
        "id": challenge_id,
        "creator_id": creator_id,
        "opponent_id": opponent_id,
        "amount_usdc": float(amount),
        "game": game,
        "visibility": visibility,
        "status": "open",
        "expires_at": expires.isoformat(),
        "message": message,
        "settlement_chain": settlement_chain,
    })
    try:
        result = _challenges().insert(record).execute()
    except Exception:
        if is_real_chain(settlement_chain):
            raise
        logger.warning("[matches] challenge insert failed; retrying without settlement_chain", exc_info=True)
        record.pop("settlement_chain", None)
        result = _challenges().insert(record).execute()
    data = getattr(result, "data", None) or []
    row = data[0] if isinstance(data, list) and data else record
    ch = normalize_challenge(dict(row)) or {}
    ch["public_code"] = display_code(None, challenge_id=challenge_id)
    return ch


@dataclass
class Draft:
    creator: dict
    amount: Decimal
    game: str
    opponent: Optional[dict] = None  # None: an invite anyone with the code can accept


async def create_challenge(d: Draft) -> dict:
    """Gates, balance, insert. Raises ``MatchRefused``."""
    from gaming.src.backend.services import stake_caps
    from gaming.src.backend.services.clawstation_circle import get_usdc_balance
    from gaming.src.backend.services.play_points import assert_can_start_or_accept
    from gaming.src.backend.services.realms import new_challenge_chain
    from gaming.src.backend.services.safety import assert_money_ops_allowed

    pid = str(d.creator["id"])
    gate = assert_money_ops_allowed(pid, action="challenge", amount=d.amount, kind="stake")
    if gate:
        raise MatchRefused("gate", plain(gate))
    chain = new_challenge_chain()
    capped = await asyncio.to_thread(stake_caps.check, pid, chain, d.amount)
    if capped:
        raise MatchRefused("cap", capped)
    blocked = await asyncio.to_thread(assert_can_start_or_accept, pid)
    if blocked:
        raise MatchRefused("busy", "You already have an open match. Finish it first (My matches).")
    if d.opponent is not None:
        if str(d.opponent["id"]) == pid:
            raise MatchRefused("self", "You can't challenge yourself.")
        if await asyncio.to_thread(assert_can_start_or_accept, str(d.opponent["id"])):
            tag = d.opponent.get("gaming_tag") or "They"
            raise MatchRefused("opponent_busy", f"@{tag} already has an open match.")
    try:
        bal = Decimal(str(await get_usdc_balance(pid, chain_id=chain)))
    except Exception as exc:
        raise MatchRefused("balance_error", "Could not check your balance. Try again in a minute.") from exc
    if bal < d.amount:
        raise MatchRefused("funds", f"Not enough {money_word(chain)} USDC. You have ${bal:,.2f}; "
                           f"this stake needs ${d.amount:,.2f}.", balance=bal)
    return await asyncio.to_thread(
        insert_challenge,
        creator_id=pid,
        opponent_id=str(d.opponent["id"]) if d.opponent else None,
        amount=d.amount,
        game=d.game,
        visibility="private",
        settlement_chain=chain,
    )


def challenge_chain(ch: dict) -> str:
    """The chain this challenge's money lives on (its own row, never a default
    that could have changed since it was created)."""
    from gaming.src.backend.services.chains import default_chain_id, normalize_chain_id

    return normalize_chain_id(ch.get("settlement_chain") or default_chain_id())


def money_word(chain: str) -> str:
    """``real`` or ``practice`` for player copy."""
    from gaming.src.backend.services.realms import money_kind

    return money_kind(chain)


# ── accept / decline ─────────────────────────────────────────────────────────


def create_bet(challenge: dict, opponent_id: str) -> Optional[dict]:
    record = {
        "id": str(uuid.uuid4()),
        "challenge_id": challenge["id"],
        "challenger_id": challenge["creator_id"],
        "opponent_id": opponent_id,
        "amount_usdc": float(challenge["amount_usdc"]),
        "status": "pending",
    }
    try:
        result = _sb().schema("gaming").table("bets").insert(record).execute()
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.warning("[Challenge] gaming.bets insert skipped: %s", exc)
        return None


async def accept_challenge(ref: str, accepter: dict) -> dict:
    """Accept an open challenge (its invitee, or anyone holding an invite code).

    Returns the challenge as accepted. Raises ``MatchRefused`` with kind
    ``paused | gone | own | not_yours | busy | funds``.
    """
    from gaming.src.backend.services.challenge_compat import denormalize_challenge
    from gaming.src.backend.services.clawstation_circle import get_usdc_balance
    from gaming.src.backend.services.play_points import assert_can_start_or_accept, get_active_challenge
    from gaming.src.backend.services.safety import is_paused, pause_message

    if is_paused():
        raise MatchRefused("paused", plain(pause_message()), html=pause_message())
    ch = await asyncio.to_thread(load, ref)
    if not ch or ch.get("status") != "open":
        raise MatchRefused("gone", "Challenge is no longer available.")
    aid = str(accepter["id"])
    if str(ch["creator_id"]) == aid:
        raise MatchRefused("own", "You cannot accept your own challenge.")
    if ch.get("visibility") == "private" and ch.get("opponent_id") and str(ch["opponent_id"]) != aid:
        raise MatchRefused("not_yours", "This challenge is not for you.")

    blocked = await asyncio.to_thread(assert_can_start_or_accept, aid)
    if blocked and ch.get("id") not in (blocked or ""):
        active = await asyncio.to_thread(get_active_challenge, aid)
        if active and active.get("id") != ch.get("id"):
            raise MatchRefused("busy", "You already have an open match. Finish it first.", active=active)

    amount = Decimal(str(ch["amount_usdc"]))
    chain = challenge_chain(ch)
    from gaming.src.backend.services import stake_caps

    capped = await asyncio.to_thread(stake_caps.check, aid, chain, amount, challenge_id=str(ch["id"]))
    if capped:
        raise MatchRefused("cap", capped)
    try:
        bal = Decimal(str(await get_usdc_balance(aid, chain_id=chain)))
        if bal < amount:
            raise MatchRefused("funds", f"You need ${amount:,.2f} {money_word(chain)} USDC to accept. "
                               f"You have ${bal:,.2f}.", amount=amount, balance=bal)
    except MatchRefused:
        raise
    except Exception as exc:
        logger.warning("[Challenge] balance check on accept: %s", exc)

    cid = ch["id"]

    def _write() -> Optional[dict]:
        # Conditional on still being open: two people tapping Accept on the
        # same public card at once must not both "win" (the second would
        # silently replace the first opponent and both would get a bet row).
        _challenges().update(
            denormalize_challenge({"status": "accepted", "opponent_id": aid})
        ).eq("id", cid).eq("status", "open").execute()
        fresh = load(cid)
        if not fresh or str(fresh.get("opponent_id") or "") != aid or fresh.get("status") != "accepted":
            return None
        create_bet(ch, aid)
        return fresh

    fresh = await asyncio.to_thread(_write)
    if fresh is None:
        raise MatchRefused("gone", "Challenge is no longer available.")
    return {**fresh, "status": "accepted", "opponent_id": aid}


async def decline_challenge(ref: str, decliner: dict) -> dict:
    ch = await asyncio.to_thread(load, ref)
    if not ch or ch.get("status") != "open":
        raise MatchRefused("gone", "Challenge is no longer available.")
    did = str(decliner["id"])
    # Only the invited opponent can decline. A public card has no invitee, so
    # without this anyone could "decline" (kill) every open public challenge.
    if str(ch.get("opponent_id") or "") != did:
        raise MatchRefused("not_yours", "This challenge is not for you.")
    await asyncio.to_thread(
        lambda: _challenges().update({"status": "declined"}).eq("id", ch["id"]).eq("status", "open").execute()
    )
    return {**ch, "status": "declined"}


# ── lock ─────────────────────────────────────────────────────────────────────


@dataclass
class LockResult:
    challenge: dict
    role: str  # creator | opponent
    both_locked: bool
    tx: dict = field(default_factory=dict)


async def lock_stake(ref: str, profile: dict, *, progress=None) -> LockResult:
    """The Telegram ``Lock my stake`` logic: gates, double-tap guard, stake
    readiness, then ``approve_and_create_match`` (creator) or
    ``approve_and_join_match`` (opponent). Raises ``MatchRefused`` with kind
    ``not_found | not_yours | gate | busy | funds | wallet | wait | escrow | error``.
    ``progress(amount)`` is awaited once the checks pass, before the escrow call.
    """
    from gaming.src.backend.services.clawstation_circle import (
        CircleWalletError,
        ensure_user_wallet,
        get_usdc_balance,
    )
    from gaming.src.backend.services.clawstation_escrow import (
        EscrowError,
        approve_and_create_match,
        approve_and_join_match,
    )
    from gaming.src.backend.services.funding_rails import ensure_stake_ready
    from gaming.src.backend.services.safety import (
        assert_money_ops_allowed,
        check_idempotent,
        clear_idempotent,
    )

    ch = await asyncio.to_thread(load, ref)
    if not ch:
        raise MatchRefused("not_found", "Match not found.")
    pid = str(profile["id"])
    who = role(ch, pid)
    if who is None:
        raise MatchRefused("not_yours", "Not your match.")
    cid = ch["id"]
    amount = Decimal(str(ch["amount_usdc"]))
    # The challenge's own chain: a real-money match locks real money, a
    # practice match practice chips (never the process default).
    chain = challenge_chain(ch)

    gate = assert_money_ops_allowed(pid, action="lock", amount=amount, kind="lock")
    if gate:
        raise MatchRefused("gate", plain(gate), html=gate, challenge=ch)
    from gaming.src.backend.services import stake_caps

    capped = await asyncio.to_thread(stake_caps.check, pid, chain, amount, challenge_id=str(cid))
    if capped:
        raise MatchRefused("cap", capped, challenge=ch)

    idem_key = f"lock:{cid}:{pid}"
    dup = check_idempotent(idem_key)
    if dup:
        raise MatchRefused("busy", plain(dup), challenge=ch)

    try:
        ready = await ensure_stake_ready(pid, amount, chain_id=chain)
        if not ready.ok:
            clear_idempotent(idem_key)
            raise MatchRefused("funds", plain(ready.message_html), html=ready.message_html, challenge=ch)
        wallet = await ensure_user_wallet(pid, chain_id=chain)
        bal = Decimal(str(await get_usdc_balance(pid, chain_id=chain)))
        if bal < amount:
            clear_idempotent(idem_key)
            raise MatchRefused(
                "funds",
                f"Not enough play money for this match. Need ${amount:,.2f}, have ${bal:,.2f}.",
                amount=amount, balance=bal, address=wallet.get("address") or "", challenge=ch,
            )
    except MatchRefused:
        raise
    except Exception as exc:
        clear_idempotent(idem_key)
        logger.exception("[matches] lock preflight failed")
        raise MatchRefused("wallet", "Wallet not ready. Open Wallet and try again.", error=exc) from exc

    if progress is not None:
        await progress(amount)
    try:
        await ensure_user_wallet(pid, chain_id=chain)
        if who == "creator":
            if ch.get("status") == "open" and ch.get("opponent_id"):
                await asyncio.to_thread(
                    lambda: _challenges().update({"status": "accepted"}).eq("id", cid).execute()
                )
            tx = await approve_and_create_match(pid, cid, amount)
        else:
            if ch.get("status") != "creator_locked":
                clear_idempotent(idem_key)
                raise MatchRefused("wait", "Wait for the other player to lock first.", challenge=ch)
            tx = await approve_and_join_match(pid, cid, amount)
    except MatchRefused:
        raise
    except (EscrowError, CircleWalletError) as exc:
        clear_idempotent(idem_key)
        raise MatchRefused("escrow", f"Lock failed: {exc}", error=exc, challenge=ch) from exc
    except Exception as exc:
        clear_idempotent(idem_key)
        logger.exception("[matches] lock failed")
        raise MatchRefused("error", "Lock failed. Nothing was charged; try again.", error=exc) from exc

    fresh = await asyncio.to_thread(load, cid) or ch
    return LockResult(fresh, who, who == "opponent", tx if isinstance(tx, dict) else {})


# ── sides, reports, settlement, disputes ─────────────────────────────────────


def choose_side(ch: dict, profile_id: str, side: str) -> dict:
    """HOME/AWAY for one player; the other side defaults to the opposite (sync)."""
    from gaming.src.backend.services.challenge_compat import denormalize_challenge

    if side not in ("home", "away"):
        raise MatchRefused("bad_side", "Pick home or away.")
    who = role(ch, profile_id)
    if who is None:
        raise MatchRefused("not_yours", "Not your match.")
    other = "away" if side == "home" else "home"
    mine, theirs = ("creator_side", "opponent_side") if who == "creator" else ("opponent_side", "creator_side")
    if ch.get(theirs) == side:
        label = "Opponent" if who == "creator" else "Creator"
        raise MatchRefused("side_taken", f"{label} already took {side}. Pick {other}.", other=other)
    update = {mine: side}
    if not ch.get(theirs):
        update[theirs] = other
    _challenges().update(denormalize_challenge(update)).eq("id", ch["id"]).execute()
    return {**ch, **update}


def save_ingame_name(ch: dict, profile_id: str, name: str) -> None:
    """Store the on-screen name a player claims (binary games), sync."""
    from gaming.src.backend.services.challenge_compat import denormalize_challenge

    who = role(ch, profile_id)
    if who is None:
        raise MatchRefused("not_yours", "Not your match.")
    key = "creator_console_id" if who == "creator" else "opponent_console_id"
    other_key = "opponent_console_id" if who == "creator" else "creator_console_id"
    if str(ch.get(other_key) or "").strip().lower() == name.strip().lower() and name.strip():
        raise MatchRefused("name_taken", f"Your opponent already claimed {ch.get(other_key)}. "
                                         "Use your own name from the screenshot.")
    try:
        _challenges().update(denormalize_challenge({key: name[:64], "console_platform": "ingame"})).eq(
            "id", ch["id"]).execute()
    except Exception:
        _challenges().update(denormalize_challenge({key: name[:64]})).eq("id", ch["id"]).execute()


def _side_for(profile_id: str, challenge: dict) -> Optional[str]:
    if profile_id == challenge.get("creator_id"):
        return challenge.get("creator_side")
    if profile_id == challenge.get("opponent_id"):
        return challenge.get("opponent_side")
    return None


def _my_goals(side: Optional[str], home: int, away: int) -> int:
    if side == "away":
        return away
    return home


def store_report(
    challenge_id: str,
    profile_id: str,
    *,
    single_score: Optional[int] = None,
    home: Optional[int] = None,
    away: Optional[int] = None,
) -> dict:
    """Write one player's score; flips to ``submitted`` once both reported (sync).

    The body of Telegram's ``submit_score._store_report``.
    """
    from gaming.src.backend.services.challenge_compat import denormalize_challenge

    challenge = load(challenge_id)
    if not challenge:
        raise ValueError("Challenge not found")
    uuid_id = challenge["id"]
    is_creator = profile_id == challenge["creator_id"]
    is_opponent = profile_id == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        raise ValueError("Not a participant")
    status = challenge.get("status")
    if status not in REPORTABLE:
        raise ValueError(f"Challenge status is {status}, cannot submit score")

    update: dict[str, Any] = {}
    side = _side_for(profile_id, challenge)
    if home is not None and away is not None:
        if is_creator:
            update["creator_reported_home"] = home
            update["creator_reported_away"] = away
            update["creator_score"] = _my_goals(side or "home", home, away)
        else:
            update["opponent_reported_home"] = home
            update["opponent_reported_away"] = away
            update["opponent_score"] = _my_goals(side or "away", home, away)
    elif single_score is not None:
        update["creator_score" if is_creator else "opponent_score"] = single_score
    else:
        raise ValueError("Missing score")

    merged = {**challenge, **update}
    both = (
        merged.get("creator_score") is not None and merged.get("opponent_score") is not None
    ) or (
        merged.get("creator_reported_home") is not None
        and merged.get("opponent_reported_home") is not None
    )
    if both:
        update["status"] = "submitted"
    elif status == "locked":
        update["status"] = "playing"
    _challenges().update(denormalize_challenge(update)).eq("id", uuid_id).execute()
    return load(uuid_id) or challenge


def save_evidence(ch: dict, profile_id: str, evidence_ref: str, screen_name: str = "") -> dict:
    """Screenshot ref (``evidence://…`` or a Telegram file id) on the reporter's
    column, plus the claimed on-screen name (sync)."""
    from gaming.src.backend.services.challenge_compat import denormalize_challenge

    who = role(ch, profile_id)
    if who is None:
        raise MatchRefused("not_yours", "Not your match.")
    column = "screenshot_creator_url" if who == "creator" else "screenshot_opponent_url"
    update: dict[str, Any] = {column: evidence_ref}
    if ch.get("status") == "locked":
        update["status"] = "playing"
    try:
        _challenges().update(denormalize_challenge(update)).eq("id", ch["id"]).execute()
    except Exception:
        logger.exception("[matches] save screenshot failed")
    sn = (screen_name or "").strip()
    if sn:
        key = "creator_console_id" if who == "creator" else "opponent_console_id"
        try:
            _challenges().update(denormalize_challenge({key: sn[:64]})).eq("id", ch["id"]).execute()
        except Exception:
            pass
    return load(ch["id"]) or {**ch, **update}


@dataclass
class ReportOutcome:
    challenge: dict
    fairness_hold: Optional[str] = None  # reason, when reports conflict on identity / double win


async def submit_report(ref: str, profile_id: str, *, home: int, away: int, evidence_ref: str,
                        screen_name: str = "") -> ReportOutcome:
    """Photo + result for one player (Telegram ``ui_report_finalize``'s writes)."""
    from gaming.src.backend.services.match_report import (
        analyze_reports,
        binary_both_claim_win,
        ingame_names_conflict,
    )

    ch = await asyncio.to_thread(load, ref)
    if not ch:
        raise MatchRefused("not_found", "Match not found.")
    ch = await asyncio.to_thread(save_evidence, ch, profile_id, evidence_ref, screen_name)
    try:
        if ingame_names_conflict(ch):
            raise MatchRefused("identity_conflict",
                               "Identity conflict: both players used the same in-game name. "
                               "Start again with your own name from the screenshot.")
    except MatchRefused:
        raise
    except Exception:
        pass
    try:
        challenge = await asyncio.to_thread(store_report, ch["id"], profile_id, home=int(home), away=int(away))
    except ValueError as exc:
        raise MatchRefused("report", str(exc)) from exc
    hold = None
    try:
        if ingame_names_conflict(challenge) or binary_both_claim_win(challenge):
            analysis = analyze_reports(challenge)
            if analysis.get("action") in ("conflict", "identity_conflict"):
                hold = str(analysis.get("reason") or "Reports disagree.")
    except Exception:
        pass
    return ReportOutcome(challenge, hold)


async def settle(challenge_id: str) -> dict:
    """Run settlement now (it waits for both reports / the dispute window)."""
    from gaming.src.backend.services.clawstation_settlement import settle_challenge

    try:
        return await settle_challenge(challenge_id)
    except Exception as exc:
        logger.exception("[matches] settle failed for %s", challenge_id)
        return {"success": False, "action": "error", "reason": str(exc)}


async def open_dispute(ref: str, profile_id: str, reason: str) -> tuple[dict, bool]:
    """Flag a dispute on-chain and in the DB. Returns (challenge, already_disputed)."""
    from gaming.src.backend.services.clawstation_escrow import flag_dispute

    ch = await asyncio.to_thread(load, ref)
    if not ch:
        raise MatchRefused("not_found", "Challenge not found.")
    if role(ch, profile_id) is None:
        raise MatchRefused("not_yours", "You are not part of this challenge.")
    if ch.get("status") not in DISPUTABLE:
        raise MatchRefused("status", f"Challenge status is {ch.get('status')}. Disputes can only be raised "
                                     "after the match is live / scores are in.")
    if ch.get("status") == "disputed":
        return ch, True
    try:
        await flag_dispute(ch["id"])
    except Exception as exc:
        logger.exception("[Dispute] Failed to flag dispute for %s", ch["id"])
        raise MatchRefused("escrow", f"Could not raise dispute: {exc}", error=exc) from exc
    await asyncio.to_thread(
        lambda: _challenges().update({"dispute_reason": reason, "status": "disputed"}).eq("id", ch["id"]).execute()
    )
    return {**ch, "status": "disputed", "dispute_reason": reason}, False
