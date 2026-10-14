"""Spectator-betting kill switch (docs/compliance/KYC_AML_PLAN.md §6).

One decision function; every gated path calls it and nothing re-implements it.

Env (read per call, never cached):
  SPECTATOR_BETTING_ENABLED   1/true/yes/on | 0/false/no/off; anything else = off
                              (logged once). Unset: off on mainnet, on otherwise.
  SPECTATOR_BETTING_COUNTRIES comma-separated ISO-3166 alpha-2 allowlist.
                              Required on mainnet (empty allows nobody); on
                              testnet it applies only when non-empty.

The caller's country comes from the geo-fence middleware (``GeoDecision.country``),
which stores it per request with ``set_request_country``. Service-layer gates
read it back with ``request_country()``; outside an HTTP request it is None, so
mainnet refuses (bot spectator betting has no country signal yet).
"""
from __future__ import annotations

import contextvars
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
REASONS = ("ok", "disabled", "country_unknown", "country_not_allowed", "country_blocked")

_country: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "boardman_request_country", default=None
)
_warned_values: set[str] = set()
_warn_lock = threading.Lock()
_refusals: dict[str, int] = {}


def set_request_country(country: Optional[str]) -> contextvars.Token:
    return _country.set((country or "").strip().upper() or None)


def request_country() -> Optional[str]:
    return _country.get()


def is_mainnet() -> bool:
    """§6.1 "chain is mainnet". Any resolution error counts as mainnet."""
    try:
        from gaming.src.backend.middleware.geo_fence import is_production

        if is_production():
            return True
        raw = (
            os.getenv("SPECTATOR_CHAIN")
            or os.getenv("BOARDMAN_SETTLEMENT_RAIL")
            or ""
        ).strip().lower()
        from gaming.src.backend.services.chains import default_chain_id, get_chain, normalize_chain_id

        cid = normalize_chain_id(raw) if raw else default_chain_id()
        if cid == "arc_mainnet":
            return True
        cfg = get_chain(cid) or {}
        return str(cfg.get("chain_id") or "") == "5042"
    except Exception:
        logger.warning("[spectator_policy] chain resolution failed — treating as mainnet", exc_info=True)
        return True


def _switch_on(mainnet: bool) -> bool:
    raw = os.getenv("SPECTATOR_BETTING_ENABLED")
    if raw is None or not raw.strip():
        return not mainnet
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    with _warn_lock:
        if v not in _warned_values:
            _warned_values.add(v)
            logger.error("[spectator_policy] SPECTATOR_BETTING_ENABLED=%r is not on/off — treating as OFF", raw)
    return False


def _allowlist() -> set[str]:
    raw = os.getenv("SPECTATOR_BETTING_COUNTRIES") or ""
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def _blocked(country: str) -> bool:
    try:
        from gaming.src.backend.middleware.geo_fence import _load_blocked_regions

        return country in _load_blocked_regions()
    except Exception:
        return False


def spectator_betting_decision(country: str | None) -> tuple[bool, str]:
    """Return (allowed, reason). reason ∈
    {"ok", "disabled", "country_unknown", "country_not_allowed", "country_blocked"}."""
    try:
        from gaming.src.backend.services.safety import is_paused

        if is_paused():
            return False, "disabled"
    except Exception:
        pass
    mainnet = is_mainnet()
    if not _switch_on(mainnet):
        return False, "disabled"
    c = (country or "").strip().upper() or None
    if c and _blocked(c):
        return False, "country_blocked"
    allow = _allowlist()
    if mainnet or allow:
        if c is None:
            return False, "country_unknown"
        if c not in allow:
            return False, "country_not_allowed"
    return True, "ok"


def betting_globally_enabled() -> bool:
    """Switch + pause only (no country): may books be opened/seeded at all?"""
    try:
        from gaming.src.backend.services.safety import is_paused

        if is_paused():
            return False
    except Exception:
        pass
    return _switch_on(is_mainnet())


def public_policy() -> dict[str, Any]:
    """For read-only views: ``spectator_betting: {enabled, reason}`` (no country list)."""
    ok, reason = spectator_betting_decision(request_country())
    return {"enabled": ok, "reason": reason}


try:  # FastAPI renders HTTPException with the right status even unhandled
    from fastapi import HTTPException as _Base
except Exception:  # pragma: no cover - fastapi always present in the API
    class _Base(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: Any = None) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail


class SpectatorBettingUnavailable(_Base):
    """Refusal of new spectator money (403 disabled / 451 region)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        if reason == "disabled":
            status, body = 403, {"error": "spectator_betting_disabled"}
        else:
            status, body = 451, {"error": "spectator_betting_unavailable_in_region", "reason": reason}
        self.body = body
        super().__init__(status_code=status, detail=body)

    def __str__(self) -> str:
        return "Spectator pools aren't available here."


def assert_spectator_betting_allowed(
    *, path: str, match_id: str = "", profile_id: str = "", country: Optional[str] = None
) -> None:
    """Gate for new spectator money in. Raises SpectatorBettingUnavailable."""
    c = country if country is not None else request_country()
    ok, reason = spectator_betting_decision(c)
    if ok:
        return
    _refusals[reason] = _refusals.get(reason, 0) + 1
    logger.info(
        "[spectator_policy] refused reason=%s country=%s match=%s path=%s profile=%s",
        reason, c, match_id, path, profile_id,
    )
    raise SpectatorBettingUnavailable(reason)


def refusal_counts() -> dict[str, int]:
    return dict(_refusals)
