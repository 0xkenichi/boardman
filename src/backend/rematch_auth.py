"""Boardman / Rematch server-to-server API key auth.

## How keys work

**You (platform) generate keys.** Devs never self-mint production access.
They call Stack HTTP APIs only with a key you issued.

### Env (pick one style)

1. **Master key** (you / internal services):
   ```
   BOARDMAN_API_KEY=sk_bm_...
   # still work: REMATCH_API_KEY, STACK_API_KEY
   ```

2. **Many builder keys** (recommended for third parties):
   ```
   # comma-separated  key:builder_id
   BOARDMAN_STACK_API_KEYS=sk_bm_alice:alice_lab,sk_bm_bob:bob_forge
   ```

3. **File** (one `key:builder_id` per line, `#` comments ok):
   ```
   BOARDMAN_STACK_API_KEYS_FILE=/secure/boardman_stack_keys.txt
   ```

Headers (any one):
  X-Boardman-Key: <key>       # preferred
  X-Rematch-Key: <key>        # legacy product name
  X-Stack-Key: <key>          # legacy
  Authorization: Bearer <key>

Generate a key:
  openssl rand -hex 32
  # or: python3 scripts/issue_stack_api_key.py --builder acme_lab
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ApiKeyPrincipal:
    """Who the key represents after verification."""

    key_id: str  # short fingerprint for logs (not the secret)
    builder_id: str  # e.g. platform | alice_lab
    is_master: bool


def rematch_api_key() -> str:
    """Primary master key (empty if unset). Boardman name preferred."""
    return (
        os.getenv("BOARDMAN_API_KEY")
        or os.getenv("REMATCH_API_KEY")
        or os.getenv("STACK_API_KEY")
        or ""
    ).strip()


def boardman_api_key() -> str:
    """Alias for rematch_api_key() — on-brand name."""
    return rematch_api_key()


def extract_api_key(
    *,
    x_rematch_key: Optional[str] = None,
    x_boardman_key: Optional[str] = None,
    x_stack_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> str:
    """Pull key from preferred headers / bearer."""
    for raw in (x_boardman_key, x_rematch_key, x_stack_key):
        got = (raw or "").strip()
        if got:
            return got
    if authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    return ""


def _fingerprint(key: str) -> str:
    if len(key) <= 12:
        return key[:4] + "…"
    return f"{key[:6]}…{key[-4:]}"


def load_api_key_map() -> dict[str, str]:
    """
    Map secret_key -> builder_id.

    Includes master REMATCH_API_KEY as builder_id ``platform``.
    """
    out: dict[str, str] = {}

    master = rematch_api_key()
    if master:
        out[master] = "platform"

    # BOARDMAN_STACK_API_KEYS=key1:builder1,key2:builder2
    raw = (os.getenv("BOARDMAN_STACK_API_KEYS") or "").strip()
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part or part.startswith("#"):
                continue
            if ":" in part:
                k, builder = part.split(":", 1)
                k, builder = k.strip(), builder.strip() or "builder"
            else:
                k, builder = part, "builder"
            if k:
                out[k] = builder

    # File: one key:builder per line
    path = (os.getenv("BOARDMAN_STACK_API_KEYS_FILE") or "").strip()
    if path:
        p = Path(path)
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, builder = line.split(":", 1)
                    k, builder = k.strip(), builder.strip() or "builder"
                else:
                    k, builder = line, "builder"
                if k:
                    out[k] = builder

    return out


def resolve_api_key(got: str) -> Optional[ApiKeyPrincipal]:
    """Return principal if ``got`` is a configured key."""
    if not got:
        return None
    mapping = load_api_key_map()
    if not mapping:
        return None
    builder = mapping.get(got)
    if builder is None:
        return None
    return ApiKeyPrincipal(
        key_id=_fingerprint(got),
        builder_id=builder,
        is_master=builder == "platform",
    )


def request_has_valid_api_key(request) -> bool:
    """True if request carries any configured Stack/Rematch API key."""
    headers = getattr(request, "headers", None) or {}
    got = extract_api_key(
        x_rematch_key=headers.get("x-rematch-key") or headers.get("X-Rematch-Key"),
        x_boardman_key=headers.get("x-boardman-key") or headers.get("X-Boardman-Key"),
        x_stack_key=headers.get("x-stack-key") or headers.get("X-Stack-Key"),
        authorization=headers.get("authorization") or headers.get("Authorization"),
    )
    return resolve_api_key(got) is not None


def generate_stack_api_key(*, builder_id: str = "builder", prefix: str = "sk_bm") -> str:
    """
    Generate a high-entropy key string (you store it; show builder once).

    Example: sk_bm_a1b2c3...
    """
    body = secrets.token_hex(24)
    safe_builder = "".join(c if c.isalnum() or c in "-_" else "" for c in builder_id)[:24]
    if safe_builder:
        return f"{prefix}_{safe_builder}_{body}"
    return f"{prefix}_{body}"
