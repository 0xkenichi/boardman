"""Resolve chat senders to profiles, dual-write Telegram identities, and link
accounts with one-time codes (CHANNELS_DESIGN §2).

Link codes: 8 characters from an unambiguous alphabet, shown as ``ABCD-EFGH``,
valid 10 minutes, single use, stored only as an HMAC. Issuing is limited per
profile and redeeming per sender. A sender who already has their own profile
is merged in only when that profile is provably empty; anything else is
refused and sent to support (each profile owns its own wallet).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

from gaming.src.channels import config
from gaming.src.channels.core import ratelimit
from gaming.src.channels.core.geo import country_from_phone
from gaming.src.channels.core.identity.repo import (
    Identity,
    IdentityRepo,
    LinkCode,
    get_repo,
    utcnow,
)
from gaming.src.channels.core.principal import CountrySignal, Principal

logger = logging.getLogger(__name__)

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"  # no 0/O, 1/I/L, U
CODE_LEN = 8
SUPPORT_TEXT = (
    "That account already has money or match history, so we can't merge it "
    "automatically. Contact support from either account and we'll sort it out by hand."
)

EmptyCheck = Callable[[str], Awaitable[tuple[bool, list[str]]]]


class LinkError(Exception):
    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message or kind)
        self.kind = kind


def link_ttl() -> timedelta:
    return timedelta(seconds=config.int_env("CHANNELS_LINK_CODE_TTL_SEC", 600))


def withdraw_hold() -> timedelta:
    return timedelta(hours=config.int_env("CHANNELS_LINK_WITHDRAW_HOLD_HOURS", 72))


def _pepper() -> bytes:
    return (os.getenv("CHANNELS_LINK_PEPPER") or "boardman-link-codes-v1").encode("utf-8")


def normalize_code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def format_code(code: str) -> str:
    c = normalize_code(code)
    return f"{c[:4]}-{c[4:]}" if len(c) == CODE_LEN else c


def hash_code(code: str) -> str:
    return hmac.new(_pepper(), normalize_code(code).encode("ascii"), hashlib.sha256).hexdigest()


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


# ── resolve ──────────────────────────────────────────────────────────────────


def _signals(channel: str, phone: Optional[str], idents: list[Identity]) -> list[CountrySignal]:
    out: list[CountrySignal] = []
    if channel == "whatsapp" and phone:
        out.append(CountrySignal("phone_cc", country_from_phone(phone)))
    # A linked WhatsApp number lifts every other channel of the same profile.
    for i in idents:
        if i.channel == "whatsapp" and i.country_hint:
            sig = CountrySignal("phone_cc", i.country_hint)
            if sig not in out:
                out.append(sig)
    return out


def resolve(
    channel: str,
    external_id: str,
    *,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    handle: Optional[str] = None,
    inbound: bool = False,
    repo: Optional[IdentityRepo] = None,
) -> Principal:
    """``(channel, external_id)`` -> Principal (``profile_id`` None if unknown).

    ``inbound=True`` records the message time (WhatsApp 24 h window).
    """
    repo = repo or get_repo()
    ext = str(external_id)
    ident = repo.get(channel, ext)
    if ident is None:
        return Principal(channel, ext, address=address, display_name=handle or "",
                         country_signals=_signals(channel, phone, []))
    if inbound:
        changes: dict[str, Any] = {"last_inbound_at": utcnow()}
        if address and address != ident.address:
            changes["address"] = address
        if handle and handle != ident.handle:
            changes["handle"] = handle
        try:
            repo.update(channel, ext, **changes)
        except Exception:
            logger.warning("[channels] last_inbound update failed", exc_info=True)
    profile = repo.get_profile(ident.profile_id) or {}
    idents = repo.for_profile(ident.profile_id)
    return Principal(
        channel,
        ext,
        profile_id=ident.profile_id,
        identity_id=ident.id,
        display_name=profile.get("gaming_tag") or profile.get("display_name") or handle or "",
        address=address or ident.address,
        country_signals=_signals(channel, phone, idents),
        withdraw_hold_until=ident.withdraw_hold_until,
        profile=profile,
    )


# ── Telegram dual-write and backfill ─────────────────────────────────────────

_dual_written: set[tuple[str, str]] = set()
_dual_write_warned = False


def ensure_telegram_identity(
    profile_id: str,
    telegram_id: Any,
    *,
    chat_id: Any = None,
    username: Optional[str] = None,
    verify_method: str = "tg_login",
    repo: Optional[IdentityRepo] = None,
) -> Optional[Identity]:
    """Make sure ``channel_identities`` has this Telegram user -> profile row.

    Called on every Telegram profile lookup/creation (dual-write). Never raises:
    the legacy bot must keep working if the table is missing or Supabase hiccups.
    """
    if not profile_id or telegram_id in (None, ""):
        return None
    key = (str(profile_id), str(telegram_id))
    if key in _dual_written:
        return None
    try:
        repo = repo or get_repo()
        cur = repo.get("telegram", str(telegram_id))
        address = str(chat_id) if chat_id not in (None, "") else str(telegram_id)
        if cur is not None and cur.profile_id != str(profile_id):
            # profiles.telegram_id is the legacy source of truth during the
            # migration; a mismatch is a data problem, not ours to "fix" here.
            logger.warning("[channels] telegram identity points at another profile; left as is")
            return cur
        if cur is not None:
            changes = {}
            if cur.address != address:
                changes["address"] = address
            if username and cur.handle != username:
                changes["handle"] = username
            if changes:
                repo.update("telegram", str(telegram_id), **changes)
            _dual_written.add(key)
            return cur
        out = repo.upsert(Identity(
            channel="telegram",
            external_id=str(telegram_id),
            profile_id=str(profile_id),
            address=address,
            handle=username or None,
            verified_at=utcnow(),
            verify_method=verify_method,
        ))
        _dual_written.add(key)
        return out
    except Exception:
        # Loud once (e.g. the migration is not applied yet), then quiet.
        global _dual_write_warned
        if not _dual_write_warned:
            _dual_write_warned = True
            logger.warning("[channels] telegram identity dual-write failed", exc_info=True)
        else:
            logger.debug("[channels] telegram identity dual-write failed", exc_info=True)
        return None


def reset_dual_write_memo() -> None:
    _dual_written.clear()


# ── link codes ───────────────────────────────────────────────────────────────


def issue_link_code(principal: Principal, *, repo: Optional[IdentityRepo] = None,
                    now: Optional[datetime] = None) -> tuple[str, datetime]:
    """A fresh code for the signed-in ``principal``'s profile."""
    if not principal.profile_id:
        raise LinkError("no_profile", "Create your account first.")
    repo = repo or get_repo()
    if not ratelimit.hit(f"link_issue:{principal.profile_id}",
                         limit=config.int_env("CHANNELS_LINK_ISSUE_PER_HOUR", 5), window_sec=3600):
        raise LinkError("rate_limited", "Too many link codes. Try again in an hour.")
    now = now or utcnow()
    expires = now + link_ttl()
    for _ in range(5):
        code = new_code()
        try:
            repo.put_link_code(LinkCode(
                code_hash=hash_code(code),
                profile_id=principal.profile_id,
                purpose="link_channel",
                issued_via=principal.channel,
                expires_at=expires,
            ))
            return code, expires
        except ValueError:
            continue  # astronomically unlikely collision
    raise LinkError("unavailable", "Could not issue a code. Try again.")


@dataclass
class LinkResult:
    status: str  # linked | merged | already_linked | invalid | rate_limited | refused_funded | conflict
    profile_id: Optional[str] = None
    merged_from: Optional[str] = None
    reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {"linked", "merged", "already_linked"}


async def redeem_link_code(
    channel: str,
    external_id: str,
    raw_code: str,
    *,
    profile_is_empty: EmptyCheck,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    handle: Optional[str] = None,
    repo: Optional[IdentityRepo] = None,
    now: Optional[datetime] = None,
) -> LinkResult:
    """Attach ``(channel, external_id)`` to the profile that issued ``raw_code``."""
    repo = repo or get_repo()
    ext = str(external_id)
    now = now or utcnow()
    if not ratelimit.hit(f"link_redeem:{channel}:{ext}",
                         limit=config.int_env("CHANNELS_LINK_REDEEM_PER_10MIN", 5), window_sec=600):
        return LinkResult("rate_limited")
    code = normalize_code(raw_code)
    if len(code) != CODE_LEN:
        return LinkResult("invalid")
    h = hash_code(code)
    row = repo.get_link_code(h)
    if row is None or row.consumed_at is not None or row.expires_at <= now or row.purpose != "link_channel":
        return LinkResult("invalid")
    target = row.profile_id

    existing = repo.get(channel, ext)
    if existing is not None and existing.profile_id == target:
        repo.consume_link_code(h, now)
        return LinkResult("already_linked", target)
    if any(i.channel == channel and i.external_id != ext for i in repo.for_profile(target)):
        return LinkResult("conflict", target)

    merged_from = None
    if existing is not None:
        empty, reasons = await profile_is_empty(existing.profile_id)
        if not empty:
            repo.consume_link_code(h, now)
            logger.info("[channels] link refused: source profile not empty (%s)", ",".join(reasons))
            return LinkResult("refused_funded", target, reasons=reasons)
        merged_from = existing.profile_id

    if not repo.consume_link_code(h, now):
        return LinkResult("invalid")

    if merged_from:
        repo.move_identities(merged_from, target)
        tomb: dict[str, Any] = {"merged_into": target}
        if channel == "telegram":
            tomb.update({"telegram_id": None, "gaming_telegram_chat_id": None})
        repo.update_profile(merged_from, tomb)

    country = country_from_phone(phone) if (channel == "whatsapp" and phone) else None
    repo.upsert(Identity(
        channel=channel,
        external_id=ext,
        profile_id=target,
        address=address,
        handle=handle,
        country_hint=country,
        verified_at=now,
        verify_method="link_code",
        opted_in_at=now if channel == "whatsapp" else None,
        last_inbound_at=now if channel == "whatsapp" else None,
        withdraw_hold_until=now + withdraw_hold(),
    ))
    if channel == "telegram":
        # Dual-write: legacy handlers still find the user by profiles.telegram_id.
        try:
            repo.update_profile(target, {
                "telegram_id": int(ext),
                "gaming_telegram_chat_id": int(address) if address else int(ext),
            })
        except Exception:
            logger.warning("[channels] telegram_id dual-write on link failed", exc_info=True)
    return LinkResult("merged" if merged_from else "linked", target, merged_from)


# ── first contact on a new channel ───────────────────────────────────────────

TAG_RE = re.compile(r"^[a-z0-9_]{3,20}$")


def clean_tag(raw: str) -> str:
    return (raw or "").strip().lstrip("@").lower()


def create_profile_for_channel(
    channel: str,
    external_id: str,
    tag: str,
    *,
    display_name: str = "",
    phone: Optional[str] = None,
    address: Optional[str] = None,
    repo: Optional[IdentityRepo] = None,
) -> Identity:
    """New player who arrived on ``channel`` (not Telegram): profile + identity.

    The profile row carries no ``telegram_id``; production must allow that
    column to be NULL [?] (it is NULL-able for wallet-first users in theory,
    but no migration in this repo defines ``profiles``).
    """
    repo = repo or get_repo()
    tag = clean_tag(tag)
    if not TAG_RE.match(tag):
        raise LinkError("bad_tag", "Use 3 to 20 letters, digits or _ .")
    if tag.startswith("sq_") or repo.tag_taken(tag):
        raise LinkError("tag_taken", "That tag is taken. Try another.")
    if repo.get(channel, str(external_id)) is not None:
        raise LinkError("exists", "You already have an account.")
    profile = repo.create_profile({"display_name": (display_name or tag)[:64], "gaming_tag": tag})
    now = utcnow()
    return repo.upsert(Identity(
        channel=channel,
        external_id=str(external_id),
        profile_id=str(profile["id"]),
        address=address,
        handle=display_name or None,
        country_hint=country_from_phone(phone) if phone else None,
        verified_at=now,
        verify_method="inbound_message",
        opted_in_at=now if channel == "whatsapp" else None,
        last_inbound_at=now if channel == "whatsapp" else None,
    ))


def opt_out(channel: str, external_id: str, *, repo: Optional[IdentityRepo] = None) -> None:
    (repo or get_repo()).update(channel, str(external_id), opted_out_at=utcnow())


def opt_in(channel: str, external_id: str, *, repo: Optional[IdentityRepo] = None) -> None:
    (repo or get_repo()).update(channel, str(external_id), opted_in_at=utcnow(), opted_out_at=None)
