"""
auth.py - Authentication utilities for JWT verification.
Supports both backend HS256 JWTs (user_id claim) and Supabase JWTs (sub claim).
"""

import os
import jwt
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase_client import get_supabase

logger = logging.getLogger(__name__)

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# ─── JWKS cache for Supabase token verification ───────────────────────────────
_jwks_client = None

def _get_jwks_client():
    """Return a cached PyJWKClient for Supabase JWKS (1-hour TTL)."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    supabase_url = os.getenv("SUPABASE_URL", "")
    if not supabase_url:
        return None
    try:
        from jwt import PyJWKClient
        jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        return _jwks_client
    except Exception as e:
        logger.warning(f"Failed to initialize JWKS client: {e}")
        return None


def _extract_user_id(payload: dict) -> str | None:
    """Extract user_id from JWT payload, supporting both backend and Supabase token shapes."""
    # Backend tokens use 'user_id', Supabase tokens use 'sub'
    user_id = payload.get("user_id") or payload.get("sub", "")
    if not user_id:
        return None
    # Supabase sub may contain a provider prefix like "provider:uuid"
    if ":" in user_id:
        user_id = user_id.split(":")[-1]
    return user_id or None


def _verify_backend_token(token: str) -> dict | None:
    """Verify a backend HS256 JWT. Returns payload or None."""
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        logger.error("JWT_SECRET_KEY not set — this is a security risk. Set it immediately.")
        return None
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


def _verify_supabase_token(token: str) -> dict | None:
    """Verify a Supabase RS256 JWT via JWKS. Returns payload or None."""
    jwks_client = _get_jwks_client()
    if not jwks_client:
        return None
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated")
    except Exception:
        return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current user from JWT token.

    Tries backend HS256 verification first, then Supabase RS256/JWKS.
    Returns the user_id string.
    """
    token = credentials.credentials

    # Try backend token (HS256)
    payload = _verify_backend_token(token)
    if payload:
        user_id = _extract_user_id(payload)
        if user_id:
            return user_id

    # Try Supabase token (RS256 via JWKS)
    payload = _verify_supabase_token(token)
    if payload:
        user_id = _extract_user_id(payload)
        if user_id:
            return user_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token"
    )

def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(optional_security)):
    """Optional dependency to get current user from JWT token, returns None if no token."""
    if credentials is None:
        return None

    token = credentials.credentials

    # Try backend token (HS256)
    payload = _verify_backend_token(token)
    if payload:
        user_id = _extract_user_id(payload)
        if user_id:
            return user_id

    # Try Supabase token (RS256 via JWKS)
    payload = _verify_supabase_token(token)
    if payload:
        user_id = _extract_user_id(payload)
        if user_id:
            return user_id

    return None

def require_beta_approval(user_id: str = Depends(get_current_user)):
    """Dependency to require beta approval."""
    supabase = get_supabase()

    try:
        beta_user = supabase.table("beta_users").select("approved").eq("user_id", user_id).execute()

        if not beta_user.data or not beta_user.data[0].get("approved", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Beta approval required"
            )

        return user_id

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking beta approval"
        )

def get_current_admin_user(user_id: str = Depends(get_current_user)):
    """Dependency to require admin privileges."""
    supabase = get_supabase()

    try:
        profile = supabase.table("profiles").select("is_admin").eq("id", user_id).execute()

        if not profile.data or not profile.data[0].get("is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )

        return user_id

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking admin privileges"
        )


# ─── Password reset (canonical, used by routes/auth.py) ────────────────
import hashlib as _hashlib
import secrets as _secrets
from datetime import datetime as _dt, timedelta as _td, timezone as _tz


def _hash_reset_token(token: str) -> str:
    """SHA-256 the token before storing (never store raw tokens)."""
    return _hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token(email: str, ttl_minutes: int = 30) -> str | None:
    """
    Create a one-time password-reset token for the given email.

    Returns the *raw* token (only the caller can see it once).
    Returns None if the user does not exist (we still return None silently
    to avoid email-enumeration; the route layer returns the same response
    in both cases).
    """
    supabase = get_supabase()
    res = supabase.table("profiles").select("id").eq("email", email.lower().strip()).execute()
    if not res.data:
        return None

    user_id = res.data[0]["id"]
    raw_token = _secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = (_dt.now(_tz.utc) + _td(minutes=ttl_minutes)).isoformat()

    # Invalidate previous tokens for this user.
    try:
        supabase.table("password_reset_tokens").update({"used": True})\
            .eq("user_id", user_id).eq("used", False).execute()
    except Exception:
        pass

    supabase.table("password_reset_tokens").insert({
        "user_id": user_id,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "used": False,
        "created_at": _dt.now(_tz.utc).isoformat(),
    }).execute()

    return raw_token


def consume_password_reset_token(token: str) -> str | None:
    """
    Validate a password-reset token. Returns user_id on success, None on
    failure (missing, expired, used). Does NOT mark as used — the route
    does that atomically with the password update.
    """
    supabase = get_supabase()
    token_hash = _hash_reset_token(token)
    now_iso = _dt.now(_tz.utc).isoformat()

    res = supabase.table("password_reset_tokens").select("*")\
        .eq("token_hash", token_hash).eq("used", False)\
        .gt("expires_at", now_iso).execute()

    if not res.data:
        return None
    return res.data[0]["user_id"]


def mark_reset_token_used(token: str) -> None:
    """Idempotent: mark a reset token as used after the password is changed."""
    supabase = get_supabase()
    token_hash = _hash_reset_token(token)
    supabase.table("password_reset_tokens").update({"used": True})\
        .eq("token_hash", token_hash).execute()

