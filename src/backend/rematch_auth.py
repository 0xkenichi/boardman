"""Rematch server-to-server API key helpers (on-brand names).

Preferred env:
  REMATCH_API_KEY

Legacy alias (still accepted):
  STACK_API_KEY

Headers (either works):
  X-Rematch-Key: <key>
  X-Stack-Key: <key>          # legacy
  Authorization: Bearer <key>
"""
from __future__ import annotations

import os
from typing import Optional


def rematch_api_key() -> str:
    """Configured Rematch API key, or empty if unset."""
    return (
        os.getenv("REMATCH_API_KEY") or os.getenv("STACK_API_KEY") or ""
    ).strip()


def extract_api_key(
    *,
    x_rematch_key: Optional[str] = None,
    x_stack_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> str:
    """Pull key from preferred headers / bearer."""
    got = (x_rematch_key or "").strip()
    if not got:
        got = (x_stack_key or "").strip()
    if not got and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    return got


def request_has_valid_api_key(request) -> bool:
    """True if request carries the configured Rematch API key."""
    expected = rematch_api_key()
    if not expected:
        return False
    headers = getattr(request, "headers", None) or {}
    got = extract_api_key(
        x_rematch_key=headers.get("x-rematch-key") or headers.get("X-Rematch-Key"),
        x_stack_key=headers.get("x-stack-key") or headers.get("X-Stack-Key"),
        authorization=headers.get("authorization") or headers.get("Authorization"),
    )
    return bool(got) and got == expected
