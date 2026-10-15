"""Webhook authentication (CHANNELS_DESIGN §4.1).

* GET verification: Meta sends ``hub.mode=subscribe``, ``hub.verify_token`` and
  ``hub.challenge``; we echo the challenge when the token matches ours.
* POST signature: ``X-Hub-Signature-256: sha256=<hex HMAC-SHA256(app_secret,
  raw body)>``, checked on the raw bytes before any JSON parsing, in constant
  time. A missing secret fails closed.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional


def app_secret() -> str:
    return (os.getenv("WHATSAPP_APP_SECRET") or "").strip()


def verify_token() -> str:
    return (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip()


def sign(secret: str, raw_body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, header: Optional[str], secret: Optional[str] = None) -> bool:
    secret = app_secret() if secret is None else secret
    if not secret or not header:
        return False
    expected = sign(secret, raw_body)
    return hmac.compare_digest(header.strip().encode("utf-8"), expected.encode("utf-8"))


def verify_subscription(mode: Optional[str], token: Optional[str], challenge: Optional[str]) -> Optional[str]:
    """The challenge to echo, or None to refuse."""
    expected = verify_token()
    if mode != "subscribe" or not expected or not token or not challenge:
        return None
    if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        return None
    return challenge
