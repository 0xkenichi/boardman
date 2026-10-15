"""One-time web links for withdrawals and PIN resets.

A chat never asks for a secret (CHANNELS_DESIGN §2.6). Instead it sends a link
to ``/app/withdraw/<token>`` where the player enters (or first sets) their
withdrawal PIN. The token is:

* 256 bits from ``secrets``; only its SHA-256 is stored;
* bound to one profile, one amount and one destination, chosen in the chat;
* short-lived (10 min by default) and single use: confirming claims it with
  one conditional UPDATE, so two clicks cannot both pay;
* rate limited: issuing per profile, wrong PINs per token (5, then burned) and
  per profile; a newer link supersedes older open ones.

The payout itself is ``withdrawals.perform_withdrawal`` with every existing
check. The PIN shares ``profiles.gaming_tx_password_hash`` (PBKDF2), so a
Telegram transaction password set before this change keeps working as the PIN.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Optional

from gaming.src.channels import config
from gaming.src.channels.core import ratelimit, store
from gaming.src.channels.core.identity.repo import get_repo

logger = logging.getLogger(__name__)

MICRO = Decimal("1000000")
MAX_PIN_ATTEMPTS = 5
_TASKS: set = set()  # keep fire-and-forget notices alive until they finish


class LinkRefused(Exception):
    STATUS = {
        "not_found": 404, "expired": 410, "used": 409, "wrong_profile": 403,
        "amount_mismatch": 409, "bad_pin": 401, "locked": 423, "pin_policy": 422,
        "pin_mismatch": 422, "rate_limited": 429, "bad_request": 400,
    }

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message

    @property
    def status_code(self) -> int:
        return self.STATUS.get(self.kind, 400)

    def body(self) -> dict[str, Any]:
        return {"ok": False, "error": self.kind, "message": self.message}


@dataclass
class IssuedLink:
    token: str
    url: str
    expires_at_ms: int


def ttl_ms() -> int:
    return config.int_env("CHANNELS_WITHDRAW_LINK_TTL_SEC", 600) * 1000


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def to_micro(amount: Decimal) -> int:
    return int((amount * MICRO).to_integral_value(rounding=ROUND_DOWN))


def link_url(token: str) -> str:
    return f"{config.site_url()}/app/withdraw/{token}"


def _issue(purpose: str, profile_id: str, channel: str, external_id: str, *,
           amount_micro: Optional[int], payload: dict, now_ms: Optional[int]) -> IssuedLink:
    if not ratelimit.hit(f"wd_issue:{profile_id}",
                         limit=config.int_env("CHANNELS_WITHDRAW_LINKS_PER_HOUR", 5), window_sec=3600,
                         now_ms=now_ms):
        raise LinkRefused("rate_limited", "Too many withdrawal links. Try again in an hour.")
    now = now_ms if now_ms is not None else store.now_ms()
    token = secrets.token_urlsafe(32)
    expires = now + ttl_ms()
    with store.db().transaction() as tx:
        # One open link per profile and purpose: a newer one supersedes it.
        tx.execute(
            "UPDATE channel_tokens SET status = 'superseded' "
            "WHERE profile_id = ? AND purpose = ? AND status = 'open'",
            (profile_id, purpose),
        )
        tx.execute(
            "INSERT INTO channel_tokens (token_hash, purpose, profile_id, channel, external_id, "
            "amount_micro, payload, status, attempts, created_at_ms, expires_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', 0, ?, ?)",
            (token_hash(token), purpose, profile_id, channel, str(external_id), amount_micro,
             tx.json(payload), now, expires),
        )
    return IssuedLink(token, link_url(token), expires)


def issue(profile_id: str, *, channel: str, external_id: str, amount: Decimal, address: str,
          recipient_id: Optional[str] = None, tag: Optional[str] = None,
          now_ms: Optional[int] = None) -> IssuedLink:
    payload = {"address": address, "recipient_id": recipient_id, "tag": tag}
    return _issue("withdraw", profile_id, channel, external_id,
                  amount_micro=to_micro(amount), payload=payload, now_ms=now_ms)


def issue_pin_reset(profile_id: str, *, channel: str, external_id: str,
                    now_ms: Optional[int] = None) -> IssuedLink:
    return _issue("pin_reset", profile_id, channel, external_id, amount_micro=None, payload={},
                  now_ms=now_ms)


# ── reading and redeeming ────────────────────────────────────────────────────


def _load(token: str) -> Optional[dict]:
    d = store.db()
    with d.transaction(readonly=True) as tx:
        row = tx.one("SELECT * FROM channel_tokens WHERE token_hash = ?", (token_hash(token),))
    if row is None:
        return None
    row["payload"] = d.dialect.unjson(row["payload"]) or {}
    return row


def _check_open(row: Optional[dict], now: int, session_profile_id: Optional[str]) -> dict:
    if row is None:
        raise LinkRefused("not_found", "This link is not valid.")
    if row["status"] != "open":
        raise LinkRefused("used", "This link was already used or replaced. Start again in the chat.")
    if int(row["expires_at_ms"]) <= now:
        raise LinkRefused("expired", "This link has expired. Start again in the chat.")
    if session_profile_id and session_profile_id != row["profile_id"]:
        raise LinkRefused("wrong_profile", "This link belongs to a different account.")
    return row


def _profile_hash(profile_id: str) -> str:
    prof = get_repo().get_profile(profile_id) or {}
    return str(prof.get("gaming_tx_password_hash") or "")


def view(token: str, *, session_profile_id: Optional[str] = None, now_ms: Optional[int] = None) -> dict:
    """What the web page shows before the PIN: never consumes the token."""
    now = now_ms if now_ms is not None else store.now_ms()
    row = _check_open(_load(token), now, session_profile_id)
    p = row["payload"]
    out: dict[str, Any] = {
        "ok": True,
        "purpose": row["purpose"],
        "needs_pin_setup": not _profile_hash(row["profile_id"]),
        "expires_in_sec": max(0, (int(row["expires_at_ms"]) - now) // 1000),
    }
    if row["purpose"] == "withdraw":
        out["amount"] = str(Decimal(int(row["amount_micro"])) / MICRO)
        out["destination"] = {"address": p.get("address"), "tag": p.get("tag")}
    return out


def pin_problem(pin: str) -> Optional[str]:
    if not pin.isdigit() or not 6 <= len(pin) <= 12:
        return "Use 6 to 12 digits."
    if len(set(pin)) == 1 or pin in "01234567890123456789" or pin in "98765432109876543210":
        return "That PIN is too easy to guess."
    return None


def _bump_attempts(th: str) -> int:
    with store.db().transaction() as tx:
        tx.execute(
            "UPDATE channel_tokens SET attempts = attempts + 1, "
            "status = CASE WHEN attempts + 1 >= ? THEN 'burned' ELSE status END "
            "WHERE token_hash = ? AND status = 'open'",
            (MAX_PIN_ATTEMPTS, th),
        )
        return int(tx.scalar("SELECT attempts FROM channel_tokens WHERE token_hash = ?", (th,)) or 0)


def _set_status(th: str, status: str, result: Optional[dict] = None, *, only_if: Optional[str] = None) -> bool:
    with store.db().transaction() as tx:
        sql = "UPDATE channel_tokens SET status = ?, result = ?, consumed_at_ms = ? WHERE token_hash = ?"
        params: list[Any] = [status, tx.json(result) if result is not None else None, store.now_ms(), th]
        if only_if:
            sql += " AND status = ?"
            params.append(only_if)
        return tx.rowcount(sql, params) == 1


def _claim(th: str, now: int) -> bool:
    with store.db().transaction() as tx:
        return tx.rowcount(
            "UPDATE channel_tokens SET status = 'claimed', consumed_at_ms = ? "
            "WHERE token_hash = ? AND status = 'open' AND expires_at_ms > ?",
            (now, th, now),
        ) == 1


def _verify_or_prepare_pin(row: dict, pin: str, pin_confirm: Optional[str]) -> Optional[str]:
    """Check the PIN (or validate a first one). Returns a new hash to store, or None."""
    from gaming.src.bot.utils.security import hash_tx_password, verify_tx_password

    pid = row["profile_id"]
    if not ratelimit.hit(f"wd_pin:{pid}", limit=config.int_env("CHANNELS_PIN_TRIES_PER_HOUR", 10),
                         window_sec=3600):
        raise LinkRefused("rate_limited", "Too many PIN attempts. Try again in an hour.")
    current = _profile_hash(pid)
    if row["purpose"] == "pin_reset" or not current:
        problem = pin_problem(pin)
        if problem:
            raise LinkRefused("pin_policy", problem)
        if pin_confirm is None or pin != pin_confirm:
            raise LinkRefused("pin_mismatch", "The two PINs don't match.")
        return hash_tx_password(pin)
    if not verify_tx_password(pin, current):
        n = _bump_attempts(row["token_hash"])
        if n >= MAX_PIN_ATTEMPTS:
            raise LinkRefused("locked", "Too many wrong PINs. This link is now closed; start again in the chat.")
        raise LinkRefused("bad_pin", f"Wrong PIN. {MAX_PIN_ATTEMPTS - n} tries left.")
    return None


Perform = Callable[..., Awaitable[Any]]


async def confirm(
    token: str,
    *,
    pin: str,
    pin_confirm: Optional[str] = None,
    amount: Optional[str] = None,
    session_profile_id: Optional[str] = None,
    perform: Optional[Perform] = None,
    now_ms: Optional[int] = None,
) -> dict:
    """Redeem a link: PIN, single-use claim, then the real payout."""
    now = now_ms if now_ms is not None else store.now_ms()
    row = _check_open(await asyncio.to_thread(_load, token), now, session_profile_id)
    th = row["token_hash"]

    if row["purpose"] == "withdraw":
        try:
            echoed = to_micro(Decimal(str(amount)))
        except (InvalidOperation, ValueError, TypeError):
            raise LinkRefused("bad_request", "Amount missing.")
        if echoed != int(row["amount_micro"]):
            await asyncio.to_thread(_set_status, th, "burned", {"reason": "amount_mismatch"}, only_if="open")
            logger.warning("[channels] withdraw link burned: amount tampering")
            raise LinkRefused("amount_mismatch", "The amount does not match the request. This link is now closed.")

    new_hash = await asyncio.to_thread(_verify_or_prepare_pin, row, pin or "", pin_confirm)

    if not await asyncio.to_thread(_claim, th, now):
        raise LinkRefused("used", "This link was already used or replaced. Start again in the chat.")
    if new_hash:
        await asyncio.to_thread(get_repo().update_profile, row["profile_id"],
                                {"gaming_tx_password_hash": new_hash})

    if row["purpose"] == "pin_reset":
        await asyncio.to_thread(_set_status, th, "done", {"pin": "set"})
        return {"ok": True, "status": "pin_set", "message": "Your withdrawal PIN is set."}

    if perform is None:
        from gaming.src.backend.services.withdrawals import perform_withdrawal as perform
    p = row["payload"]
    amt = Decimal(int(row["amount_micro"])) / MICRO
    try:
        outcome = await perform(
            row["profile_id"],
            recipient_address=p["address"],
            amount=amt,
            recipient_id=p.get("recipient_id"),
        )
    except Exception:
        logger.exception("[channels] withdrawal crashed after claim")
        await asyncio.to_thread(_set_status, th, "failed", {"code": "error"})
        return {"ok": False, "status": "failed", "message": "Withdrawal failed. Nothing was sent; try again in the chat."}
    result = {"code": outcome.code, "tx_hash": outcome.tx_hash, "transaction_id": outcome.transaction_id}
    await asyncio.to_thread(_set_status, th, "done" if outcome.ok else "failed", result)
    if outcome.ok:
        _notify_done(row, outcome)
    return {
        "ok": bool(outcome.ok),
        "status": "submitted" if outcome.ok else outcome.code,
        "message": outcome.message,
        "tx_hash": outcome.tx_hash,
        "pin_set": bool(new_hash),
    }


def _notify_done(row: dict, outcome: Any) -> None:
    """Tell the chat that asked for this withdrawal (best effort, background)."""
    try:
        from gaming.src.channels.core.notify import Notice, notify

        p = row["payload"]
        dest = f"@{p['tag']}" if p.get("tag") else (p.get("address") or "")
        notice = Notice(
            kind="withdrawal_update",
            params={"amount": f"{outcome.amount:,.2f}", "destination": dest, "status": "submitted"},
            text=f"Withdrawal of ${outcome.amount:,.2f} USDC to {dest} submitted.",
        )
        task = asyncio.get_running_loop().create_task(notify(row["profile_id"], notice))
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    except Exception:
        logger.debug("[channels] withdraw notice skipped", exc_info=True)
