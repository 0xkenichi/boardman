"""Identity repository: ``channel_identities``, ``channel_link_codes`` and the
few profile operations linking needs.

Production rows live in Supabase next to ``profiles``
(``supabase/migrations/20261016120000_channel_identities.sql``) and are reached
through the service-role client, like every other bot table.
``MemoryIdentityRepo`` is the test double (and a local-dev store with
``CHANNELS_IDENTITY_STORE=memory``).
"""
from __future__ import annotations

import copy
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

IDENTITIES = "channel_identities"
LINK_CODES = "channel_link_codes"
CHANNELS = ("telegram", "whatsapp", "web_wallet", "email", "imessage")

_TS_FIELDS = (
    "verified_at",
    "opted_in_at",
    "opted_out_at",
    "last_inbound_at",
    "revoked_at",
    "withdraw_hold_until",
    "created_at",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.astimezone(timezone.utc).isoformat() if v is not None else None


def _parse_ts(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@dataclass
class Identity:
    channel: str
    external_id: str
    profile_id: str
    id: Optional[str] = None
    address: Optional[str] = None
    handle: Optional[str] = None
    country_hint: Optional[str] = None
    verified_at: Optional[datetime] = None
    verify_method: Optional[str] = None
    opted_in_at: Optional[datetime] = None
    opted_out_at: Optional[datetime] = None
    last_inbound_at: Optional[datetime] = None
    notify_priority: int = 100
    revoked_at: Optional[datetime] = None
    withdraw_hold_until: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @property
    def opted_in(self) -> bool:
        if self.opted_in_at is None:
            return False
        return self.opted_out_at is None or self.opted_out_at < self.opted_in_at

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for k in _TS_FIELDS:
            row[k] = _iso(row[k])
        if row.get("id") is None:
            row.pop("id")
        if row.get("created_at") is None:
            row.pop("created_at")
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Identity":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in row.items() if k in names}
        for k in _TS_FIELDS:
            if k in kw:
                kw[k] = _parse_ts(kw[k])
        kw["external_id"] = str(kw.get("external_id"))
        kw["profile_id"] = str(kw.get("profile_id"))
        if kw.get("notify_priority") is None:
            kw["notify_priority"] = 100
        return cls(**kw)


@dataclass
class LinkCode:
    code_hash: str
    profile_id: str
    purpose: str  # link_channel | web_login
    issued_via: str
    expires_at: datetime
    browser_nonce: Optional[str] = None
    attempts: int = 0
    consumed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for k in ("expires_at", "consumed_at", "created_at"):
            row[k] = _iso(row[k])
        if row["created_at"] is None:
            row.pop("created_at")
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "LinkCode":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in row.items() if k in names}
        for k in ("expires_at", "consumed_at", "created_at"):
            if k in kw:
                kw[k] = _parse_ts(kw[k])
        kw["profile_id"] = str(kw["profile_id"])
        kw["attempts"] = int(kw.get("attempts") or 0)
        return cls(**kw)


class IdentityRepo(Protocol):
    # identities
    def get(self, channel: str, external_id: str) -> Optional[Identity]: ...
    def for_profile(self, profile_id: str) -> list[Identity]: ...
    def upsert(self, ident: Identity) -> Identity: ...
    def update(self, channel: str, external_id: str, **changes: Any) -> None: ...
    def move_identities(self, from_profile: str, to_profile: str) -> int: ...
    # link codes
    def put_link_code(self, code: LinkCode) -> None: ...
    def get_link_code(self, code_hash: str) -> Optional[LinkCode]: ...
    def consume_link_code(self, code_hash: str, now: datetime) -> bool: ...
    def count_link_codes(self, profile_id: str, since: datetime) -> int: ...
    # profiles
    def get_profile(self, profile_id: str) -> Optional[dict]: ...
    def create_profile(self, row: dict) -> dict: ...
    def update_profile(self, profile_id: str, changes: dict) -> None: ...
    def tag_taken(self, tag: str) -> bool: ...
    def profiles_with_telegram(self, after_id: Optional[str], limit: int) -> list[dict]: ...


def _norm_changes(changes: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in changes.items():
        out[k] = _iso(v) if isinstance(v, datetime) else v
    return out


# ── Supabase (production) ────────────────────────────────────────────────────


def _rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


class SupabaseIdentityRepo:
    """Service-role PostgREST access. Every call is one HTTP round trip."""

    PROFILE_COLS = (
        "id, display_name, gaming_tag, telegram_id, gaming_telegram_chat_id, "
        "gaming_tx_password_hash, wallet_balance_usdc, play_points, gaming_wins, "
        "gaming_losses, gaming_draws, linked_wallet"
    )

    def _sb(self):
        # Looked up per call so tests that swap the client are honoured.
        from backend.supabase_client import get_supabase

        return get_supabase()

    def get(self, channel: str, external_id: str) -> Optional[Identity]:
        r = (
            self._sb().table(IDENTITIES).select("*")
            .eq("channel", channel).eq("external_id", str(external_id))
            .limit(1).execute()
        )
        rows = _rows(r)
        if not rows:
            return None
        ident = Identity.from_row(rows[0])
        return None if ident.revoked_at else ident

    def for_profile(self, profile_id: str) -> list[Identity]:
        r = self._sb().table(IDENTITIES).select("*").eq("profile_id", profile_id).execute()
        out = [Identity.from_row(x) for x in _rows(r)]
        return sorted((i for i in out if not i.revoked_at), key=lambda i: i.notify_priority)

    def upsert(self, ident: Identity) -> Identity:
        r = (
            self._sb().table(IDENTITIES)
            .upsert(ident.to_row(), on_conflict="channel,external_id")
            .execute()
        )
        rows = _rows(r)
        return Identity.from_row(rows[0]) if rows else ident

    def update(self, channel: str, external_id: str, **changes: Any) -> None:
        (
            self._sb().table(IDENTITIES).update(_norm_changes(changes))
            .eq("channel", channel).eq("external_id", str(external_id)).execute()
        )

    def move_identities(self, from_profile: str, to_profile: str) -> int:
        r = (
            self._sb().table(IDENTITIES).update({"profile_id": to_profile})
            .eq("profile_id", from_profile).execute()
        )
        return len(_rows(r))

    def put_link_code(self, code: LinkCode) -> None:
        self._sb().table(LINK_CODES).insert(code.to_row()).execute()

    def get_link_code(self, code_hash: str) -> Optional[LinkCode]:
        r = self._sb().table(LINK_CODES).select("*").eq("code_hash", code_hash).limit(1).execute()
        rows = _rows(r)
        return LinkCode.from_row(rows[0]) if rows else None

    def consume_link_code(self, code_hash: str, now: datetime) -> bool:
        # One conditional UPDATE: PostgREST returns the updated rows by
        # default (Prefer: return=representation) [?], so exactly one row
        # back means this caller won the code.
        r = (
            self._sb().table(LINK_CODES)
            .update({"consumed_at": _iso(now)})
            .eq("code_hash", code_hash)
            .is_("consumed_at", "null")
            .gt("expires_at", _iso(now))
            .execute()
        )
        return len(_rows(r)) == 1

    def count_link_codes(self, profile_id: str, since: datetime) -> int:
        r = (
            self._sb().table(LINK_CODES).select("code_hash")
            .eq("profile_id", profile_id).gte("created_at", _iso(since)).execute()
        )
        return len(_rows(r))

    def get_profile(self, profile_id: str) -> Optional[dict]:
        r = self._sb().table("profiles").select(self.PROFILE_COLS).eq("id", profile_id).limit(1).execute()
        rows = _rows(r)
        return rows[0] if rows else None

    def create_profile(self, row: dict) -> dict:
        r = self._sb().table("profiles").insert(row).select(self.PROFILE_COLS).execute()
        rows = _rows(r)
        if not rows:
            raise RuntimeError("profile insert returned no row")
        return rows[0]

    def update_profile(self, profile_id: str, changes: dict) -> None:
        self._sb().table("profiles").update(_norm_changes(changes)).eq("id", profile_id).execute()

    def tag_taken(self, tag: str) -> bool:
        r = self._sb().table("profiles").select("id").eq("gaming_tag", tag).limit(1).execute()
        return bool(_rows(r))

    def profiles_with_telegram(self, after_id: Optional[str], limit: int) -> list[dict]:
        q = (
            self._sb().table("profiles")
            .select("id, telegram_id, gaming_telegram_chat_id, gaming_tag, linked_wallet")
            .not_.is_("telegram_id", "null")
            .order("id")
            .limit(limit)
        )
        if after_id:
            q = q.gt("id", after_id)
        return _rows(q.execute())


# ── In-memory double ─────────────────────────────────────────────────────────


class MemoryIdentityRepo:
    """Same semantics as the Supabase tables, in one process."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.identities: dict[tuple[str, str], Identity] = {}
        self.codes: dict[str, LinkCode] = {}
        self.profiles: dict[str, dict] = {}

    # identities
    def get(self, channel: str, external_id: str) -> Optional[Identity]:
        with self._lock:
            i = self.identities.get((channel, str(external_id)))
            return copy.deepcopy(i) if i and not i.revoked_at else None

    def for_profile(self, profile_id: str) -> list[Identity]:
        with self._lock:
            out = [copy.deepcopy(i) for i in self.identities.values()
                   if i.profile_id == profile_id and not i.revoked_at]
        return sorted(out, key=lambda i: i.notify_priority)

    def upsert(self, ident: Identity) -> Identity:
        if ident.channel not in CHANNELS:
            raise ValueError(f"unknown channel {ident.channel!r}")
        with self._lock:
            key = (ident.channel, str(ident.external_id))
            cur = self.identities.get(key)
            new = copy.deepcopy(ident)
            new.id = (cur.id if cur else None) or new.id or str(uuid.uuid4())
            new.created_at = (cur.created_at if cur else None) or utcnow()
            self.identities[key] = new
            return copy.deepcopy(new)

    def update(self, channel: str, external_id: str, **changes: Any) -> None:
        with self._lock:
            cur = self.identities.get((channel, str(external_id)))
            if cur is None:
                return
            for k, v in changes.items():
                if k in _TS_FIELDS and not isinstance(v, datetime):
                    v = _parse_ts(v)
                setattr(cur, k, v)

    def move_identities(self, from_profile: str, to_profile: str) -> int:
        n = 0
        with self._lock:
            for i in self.identities.values():
                if i.profile_id == from_profile:
                    i.profile_id = to_profile
                    n += 1
        return n

    # link codes
    def put_link_code(self, code: LinkCode) -> None:
        with self._lock:
            if code.code_hash in self.codes:
                raise ValueError("duplicate code")
            c = copy.deepcopy(code)
            c.created_at = c.created_at or utcnow()
            self.codes[code.code_hash] = c

    def get_link_code(self, code_hash: str) -> Optional[LinkCode]:
        with self._lock:
            c = self.codes.get(code_hash)
            return copy.deepcopy(c) if c else None

    def consume_link_code(self, code_hash: str, now: datetime) -> bool:
        with self._lock:
            c = self.codes.get(code_hash)
            if c is None or c.consumed_at is not None or c.expires_at <= now:
                return False
            c.consumed_at = now
            return True

    def count_link_codes(self, profile_id: str, since: datetime) -> int:
        with self._lock:
            return sum(1 for c in self.codes.values()
                       if c.profile_id == profile_id and (c.created_at or utcnow()) >= since)

    # profiles
    def get_profile(self, profile_id: str) -> Optional[dict]:
        with self._lock:
            p = self.profiles.get(profile_id)
            return copy.deepcopy(p) if p else None

    def create_profile(self, row: dict) -> dict:
        with self._lock:
            p = dict(row)
            p.setdefault("id", str(uuid.uuid4()))
            if p.get("telegram_id") is not None and any(
                q.get("telegram_id") == p["telegram_id"] for q in self.profiles.values()
            ):
                raise ValueError("duplicate telegram_id")
            self.profiles[p["id"]] = p
            return copy.deepcopy(p)

    def update_profile(self, profile_id: str, changes: dict) -> None:
        with self._lock:
            if profile_id in self.profiles:
                self.profiles[profile_id].update(_norm_changes(changes))

    def tag_taken(self, tag: str) -> bool:
        with self._lock:
            return any((p.get("gaming_tag") or "") == tag for p in self.profiles.values())

    def profiles_with_telegram(self, after_id: Optional[str], limit: int) -> list[dict]:
        with self._lock:
            rows = sorted(
                (copy.deepcopy(p) for p in self.profiles.values() if p.get("telegram_id") is not None),
                key=lambda p: p["id"],
            )
        if after_id:
            rows = [p for p in rows if p["id"] > after_id]
        return rows[:limit]


# ── selection ────────────────────────────────────────────────────────────────

_override: Optional[IdentityRepo] = None
_memory_singleton: Optional[MemoryIdentityRepo] = None


def set_repo(repo: Optional[IdentityRepo]) -> None:
    """Install a repo for this process (tests; ``None`` restores the default)."""
    global _override
    _override = repo


def get_repo() -> IdentityRepo:
    global _memory_singleton
    if _override is not None:
        return _override
    if (os.getenv("CHANNELS_IDENTITY_STORE") or "").strip().lower() == "memory":
        if _memory_singleton is None:
            _memory_singleton = MemoryIdentityRepo()
        return _memory_singleton
    return SupabaseIdentityRepo()
