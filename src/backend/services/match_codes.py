"""
Public match codes — short user-facing refs that hide the DB UUID.

- Database primary key remains a UUID (``challenges.id``).
- Users only see ``public_code`` (e.g. ``K7M2P9QX``).
- Commands accept either the short code or the UUID (admin / legacy).
- Callbacks keep the UUID internally (Telegram size limit is fine).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Crockford-ish alphabet — no 0/O/1/I to reduce copy mistakes
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LEN = 8
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _secret() -> bytes:
    raw = (
        os.getenv("MATCH_CODE_SECRET")
        or os.getenv("CIRCLE_ENTITY_SECRET")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or "clawstation-dev-match-codes"
    )
    return raw.encode("utf-8")


def is_uuid(value: str) -> bool:
    if not value or not _UUID_RE.match(value.strip()):
        return False
    try:
        uuid.UUID(value.strip())
        return True
    except Exception:
        return False


def normalize_code(value: str) -> str:
    """Strip noise and uppercase for comparison."""
    return re.sub(r"[^A-Za-z0-9]", "", (value or "").strip()).upper()


def looks_like_public_code(value: str) -> bool:
    n = normalize_code(value)
    return 6 <= len(n) <= 12 and n.isalnum() and not is_uuid(value or "")


def generate_public_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LEN))


def derived_code(challenge_id: str) -> str:
    """Stable non-UUID display if DB column is missing / not yet set.

    Not reversible alone — only used as temporary display; prefer stored codes.
    """
    digest = hmac.new(_secret(), challenge_id.encode("utf-8"), hashlib.sha256).digest()
    chars: list[str] = []
    for b in digest:
        chars.append(_ALPHABET[b % len(_ALPHABET)])
        if len(chars) >= CODE_LEN:
            break
    return "".join(chars)


def display_code(challenge: Optional[dict[str, Any]], challenge_id: Optional[str] = None) -> str:
    """User-facing match ref. Never returns a full UUID."""
    if challenge:
        code = challenge.get("public_code")
        if code:
            return normalize_code(str(code))
        cid = challenge.get("id") or challenge_id
        if cid:
            return derived_code(str(cid))
    if challenge_id:
        if is_uuid(challenge_id):
            return derived_code(challenge_id)
        return normalize_code(challenge_id) or "????????"
    return "????????"


def _get_supabase():
    from backend.supabase_client import get_supabase

    return get_supabase()


def ensure_public_code(challenge: dict[str, Any]) -> str:
    """Return public_code, writing one to DB if missing."""
    existing = challenge.get("public_code")
    if existing:
        return normalize_code(str(existing))

    cid = challenge.get("id")
    if not cid:
        return "????????"

    code = generate_public_code()
    sb = _get_supabase()
    for _ in range(5):
        try:
            sb.schema("gaming").table("challenges").update({"public_code": code}).eq(
                "id", cid
            ).execute()
            challenge["public_code"] = code
            return code
        except Exception as exc:
            err = str(exc).lower()
            if "public_code" in err and ("column" in err or "schema cache" in err):
                # Column not migrated yet — use derived display only
                logger.warning("[MatchCodes] public_code column missing; using derived code")
                return derived_code(cid)
            if "unique" in err or "duplicate" in err:
                code = generate_public_code()
                continue
            logger.warning("[MatchCodes] ensure_public_code failed: %s", exc)
            return derived_code(cid)
    return derived_code(cid)


def resolve_to_uuid(ref: str) -> Optional[str]:
    """Map user input (short code or UUID) → challenge UUID.

    Returns None if not found.
    """
    if not ref or not str(ref).strip():
        return None
    raw = str(ref).strip()

    if is_uuid(raw):
        return str(uuid.UUID(raw))

    code = normalize_code(raw)
    if not code:
        return None

    sb = _get_supabase()
    # 1) Preferred: stored public_code column (migration 054)
    try:
        result = (
            sb.schema("gaming")
            .table("challenges")
            .select("id, public_code")
            .eq("public_code", code)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows:
            return rows[0]["id"]
        result = (
            sb.schema("gaming")
            .table("challenges")
            .select("id, public_code")
            .ilike("public_code", code)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows:
            return rows[0]["id"]
    except Exception as exc:
        logger.debug("[MatchCodes] public_code lookup unavailable: %s", exc)

    # 2) Fallback without column: match derived_code(id) over recent rows
    try:
        result = (
            sb.schema("gaming")
            .table("challenges")
            .select("id")
            .order("created_at", desc=True)
            .limit(400)
            .execute()
        )
        for row in result.data or []:
            rid = row.get("id")
            if rid and derived_code(str(rid)) == code:
                return rid
    except Exception as exc:
        logger.warning("[MatchCodes] derived resolve scan failed: %s", exc)

    return None


def load_challenge_by_ref(ref: str) -> Optional[dict[str, Any]]:
    """Load + normalize a challenge from short code or UUID; ensure public_code."""
    from gaming.src.backend.services.challenge_compat import normalize_challenge

    cid = resolve_to_uuid(ref)
    if not cid and is_uuid(ref or ""):
        cid = str(uuid.UUID(ref.strip()))
    if not cid:
        # Direct id lookup even if resolve failed (uuid path)
        if is_uuid(ref or ""):
            cid = str(uuid.UUID(ref.strip()))
        else:
            return None

    sb = _get_supabase()
    try:
        result = (
            sb.schema("gaming")
            .table("challenges")
            .select("*")
            .eq("id", cid)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("[MatchCodes] load challenge %s", cid)
        return None

    data = result.data
    row = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
    ch = normalize_challenge(row)
    if not ch:
        return None
    ensure_public_code(ch)
    return ch


def new_challenge_public_code() -> str:
    """Generate a unique-looking code for insert (caller retries on unique conflict)."""
    return generate_public_code()


def support_id_block(challenge: dict[str, Any]) -> str:
    """Full internal UUID for support / dispute confirmation only.

    Players normally only see ``display_code``. Reveal this when they open a
    dispute or run /support_id so support can match DB records.
    """
    match_code = display_code(challenge)
    full_id = str(challenge.get("id") or "")
    return (
        f"Match code: <code>{match_code}</code>\n"
        f"Support ID: <code>{full_id}</code>\n"
        f"<i>Share Support ID only with ClawStation support if they ask to confirm "
        f"the same match on our side.</i>"
    )


def format_dispute_copy(challenge: dict[str, Any], reason: str, *, for_opponent: bool = False) -> str:
    """Player-facing dispute message with short code + support UUID."""
    match_code = display_code(challenge)
    full_id = str(challenge.get("id") or "")
    if for_opponent:
        head = f"⚠️ Your opponent disputed match <code>{match_code}</code>."
    else:
        head = f"⚠️ Dispute raised for match <code>{match_code}</code>."
    return (
        f"{head}\n\n"
        f"Reason: <code>{reason}</code>\n\n"
        f"<b>For support</b> (only if asked):\n"
        f"Support ID: <code>{full_id}</code>\n\n"
        f"Keep screenshots. Support uses the Support ID to find the exact match "
        f"in our database — the short code is what you use in the bot."
    )
