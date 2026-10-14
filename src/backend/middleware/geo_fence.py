"""
gaming/src/backend/middleware/geo_fence.py — IP-based geo-fence for Boardman.

Two public entry points:

``check_region(request)``
    Detects the request's country and raises ``BlockedRegionError`` when it is on
    the blocked list. Used by the Telegram bot handlers and by the current
    ``main.py`` middleware. In strict mode it also raises ``RegionUnverifiedError``
    (a ``BlockedRegionError`` subclass) for a money route whose country is unknown.

``evaluate_request(request) -> GeoDecision``
    The full policy decision for an HTTP request: exempt paths, money routes,
    strict (fail-closed) mode, API-key traffic and the trusted forwarded-country
    header. ``main.py`` should call this instead of its own bypass list (see
    COMPLIANCE.md, "Wiring").

Country detection for direct (browser / unkeyed) traffic:
    1. Edge headers from the policy file (default ``cf-ipcountry``, then
       ``x-vercel-ip-country``).
    2. MaxMind GeoLite2 lookup against ``data/GeoLite2-Country.mmdb`` (offline).

Server-to-server traffic carrying the **master** API key (the Vercel BFF) is
judged only by the trusted forwarded-country header (default
``x-boardman-client-country``), because the edge headers and IP on that hop
describe Vercel, not the user. The header is ignored on any other request.

Strict mode (``GEO_FENCE_STRICT``; default on in production, see
``strict_mode()``) makes money routes FAIL CLOSED: no detected country, or a
blocked list that failed to load, means the request is refused. Non-money
routes keep the permissive behaviour (allowed and logged).

Files (all tracked in git, resolved from the repo root, not the CWD):
    config/blocked_regions.json      canonical blocked list (``BLOCKED_REGIONS_FILE``)
    config/compliance/geo_fence.json route policy          (``GEO_FENCE_POLICY_FILE``)
    data/GeoLite2-Country.mmdb       optional MaxMind DB    (``MAXMIND_DB_PATH``)
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────────────
# resolve() follows the gaming/src -> src symlink, so parents[3] is the repo
# root (the directory holding src/ and config/) in a checkout and /app in the
# Docker images. The previous parents[4] + "gaming/config" pointed one level
# above the repo and silently loaded an empty list unless BLOCKED_REGIONS_FILE
# was set.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BLOCKED_FILE = REPO_ROOT / "config" / "blocked_regions.json"
DEFAULT_POLICY_FILE = REPO_ROOT / "config" / "compliance" / "geo_fence.json"
DEFAULT_MAXMIND_DB = REPO_ROOT / "data" / "GeoLite2-Country.mmdb"

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}
_MUTATING = ["POST", "PUT", "PATCH", "DELETE"]

# Used when the policy file is missing or unreadable: every mutating /api/ call
# counts as a money route, so a lost config fails closed rather than open.
_FALLBACK_POLICY: dict[str, Any] = {
    "exempt_prefixes": ["/api/health", "/docs", "/redoc", "/openapi.json", "/webhooks/"],
    "edge_country_headers": ["cf-ipcountry", "x-vercel-ip-country"],
    "trusted_country_header": "x-boardman-client-country",
    "money_routes": [{"kind": "unknown", "methods": _MUTATING, "pattern": "/api/*"}],
}


class BlockedRegionError(Exception):
    """Raised when a request originates from a region Boardman does not serve."""

    def __init__(self, country_code: str):
        self.country_code = (country_code or "").upper()
        super().__init__(f"Service unavailable in region: {self.country_code}")


class RegionUnverifiedError(BlockedRegionError):
    """Strict mode: a money route was called and the country could not be verified."""

    def __init__(self, reason: str = "country_unknown"):
        self.reason = reason
        super().__init__("")
        self.args = (f"Region could not be verified for a money route ({reason})",)


# ── Env helpers ─────────────────────────────────────────────────────────────
def _env_flag(name: str) -> Optional[bool]:
    raw = (os.getenv(name) or "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return None


def _resolve_path(raw: Optional[str], default: Path) -> Path:
    """Absolute paths as-is; relative ones tried against the CWD, then the repo root."""
    if not raw:
        return default
    p = Path(raw)
    if p.is_absolute() or p.exists():
        return p
    return REPO_ROOT / p


def is_production() -> bool:
    """True when the process is configured for production / mainnet money.

    Any of: ``BOARDMAN_ENV`` / ``APP_ENV`` / ``ENVIRONMENT`` in {production, prod,
    mainnet}; ``NETWORK=mainnet``; ``CLAW_DEFAULT_CHAIN`` or
    ``BOARDMAN_SETTLEMENT_RAIL`` = ``arc_mainnet``. The hosted testnet stack sets
    none of these, so it stays permissive unless ``GEO_FENCE_STRICT=1``.
    """
    for name in ("BOARDMAN_ENV", "APP_ENV", "ENVIRONMENT"):
        if (os.getenv(name) or "").strip().lower() in {"production", "prod", "mainnet"}:
            return True
    if (os.getenv("NETWORK") or "").strip().lower() == "mainnet":
        return True
    for name in ("CLAW_DEFAULT_CHAIN", "BOARDMAN_SETTLEMENT_RAIL"):
        if (os.getenv(name) or "").strip().lower() == "arc_mainnet":
            return True
    return False


def strict_mode() -> bool:
    """``GEO_FENCE_STRICT`` if set to a boolean value, else ``is_production()``."""
    flag = _env_flag("GEO_FENCE_STRICT")
    return is_production() if flag is None else flag


# ── Blocked list (lazy-loaded, cached) ─────────────────────────────────────
_blocked_cache: Optional[set[str]] = None
_blocked_cache_path: Optional[str] = None
_blocked_cache_ok: bool = False


def _load_blocked_regions(path: Optional[Path] = None) -> set[str]:
    """Load the blocked-region set from disk. Returns an empty set on any error.

    Use ``blocked_list_loaded()`` to tell "empty list" apart from "failed to load".
    """
    global _blocked_cache, _blocked_cache_path, _blocked_cache_ok

    cfg_path = Path(path) if path else _resolve_path(os.getenv("BLOCKED_REGIONS_FILE"), DEFAULT_BLOCKED_FILE)
    cache_key = str(cfg_path)

    if _blocked_cache is not None and _blocked_cache_path == cache_key:
        return _blocked_cache

    blocked: set[str] = set()
    ok = False
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        raw = data.get("blocked") if isinstance(data, dict) else None
        if isinstance(raw, list):
            blocked = {str(c).strip().upper() for c in raw if isinstance(c, (str, int)) and str(c).strip()}
            ok = True
        else:
            logger.error("Blocked regions file %s has no 'blocked' list.", cfg_path)
    except FileNotFoundError:
        logger.error("Blocked regions file not found at %s; no regions blocked.", cfg_path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load blocked regions from %s: %s", cfg_path, exc)

    _blocked_cache = blocked
    _blocked_cache_path = cache_key
    _blocked_cache_ok = ok
    return blocked


def blocked_list_loaded() -> bool:
    """True if the configured blocked list was read and parsed successfully."""
    _load_blocked_regions()
    return _blocked_cache_ok


def reset_blocked_cache() -> None:
    """Clear cached blocked list and route policy (useful for tests)."""
    global _blocked_cache, _blocked_cache_path, _blocked_cache_ok
    _blocked_cache = None
    _blocked_cache_path = None
    _blocked_cache_ok = False
    _policy_cache.clear()


# ── Route policy (lazy-loaded, cached) ─────────────────────────────────────
_policy_cache: dict[str, Any] = {}


def load_policy() -> dict[str, Any]:
    """Return the route policy from ``config/compliance/geo_fence.json``.

    Falls back to ``_FALLBACK_POLICY`` (all mutating /api/ calls are money
    routes) if the file is missing or malformed.
    """
    cfg_path = _resolve_path(os.getenv("GEO_FENCE_POLICY_FILE"), DEFAULT_POLICY_FILE)
    key = str(cfg_path)
    if _policy_cache.get("path") == key:
        return _policy_cache["policy"]

    policy: dict[str, Any] = dict(_FALLBACK_POLICY)
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("money_routes"), list):
            raise ValueError("missing money_routes list")
        for k in ("exempt_prefixes", "edge_country_headers", "trusted_country_header", "money_routes"):
            if k in data:
                policy[k] = data[k]
    except (OSError, ValueError) as exc:  # JSONDecodeError is a ValueError
        logger.error(
            "Geo-fence policy %s unusable (%s); treating every mutating /api/ call as a money route.",
            cfg_path,
            exc,
        )
        policy = dict(_FALLBACK_POLICY)

    _policy_cache["path"] = key
    _policy_cache["policy"] = policy
    return policy


def _norm_path(path: str) -> str:
    path = path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return path


def is_exempt_path(path: str) -> bool:
    path = path or ""
    return any(path.startswith(p) for p in load_policy().get("exempt_prefixes", []))


def money_route_kind(method: str, path: str) -> Optional[str]:
    """Return the money-route ``kind`` for ``method path``, or ``None``."""
    method = (method or "").upper()
    path = _norm_path(path)
    for route in load_policy().get("money_routes", []):
        if not isinstance(route, dict):
            continue
        methods = [str(m).upper() for m in route.get("methods") or _MUTATING]
        if method not in methods:
            continue
        pattern = str(route.get("pattern") or "")
        if pattern and fnmatch.fnmatchcase(path, pattern):
            return str(route.get("kind") or "money")
    return None


# ── MaxMind reader (lazy, cached, optional) ────────────────────────────────
_reader_cache: dict[str, object] = {"reader": None, "path": None, "available": False}


def _get_maxmind_reader(path: Optional[Path] = None):
    """Return a cached ``maxminddb.open_database`` reader, or ``None`` if unavailable."""
    db_path = Path(path) if path else _resolve_path(os.getenv("MAXMIND_DB_PATH"), DEFAULT_MAXMIND_DB)
    cache_key = str(db_path)

    if _reader_cache.get("path") == cache_key:
        return _reader_cache.get("reader") if _reader_cache.get("available") else None

    _reader_cache["path"] = cache_key
    _reader_cache["reader"] = None
    _reader_cache["available"] = False

    if not db_path.exists():
        logger.warning(
            "MaxMind GeoLite2 DB not found at %s; IP lookups unavailable (strict mode refuses "
            "money routes with no edge country header).",
            db_path,
        )
        return None

    try:
        import maxminddb  # local import: dependency is optional at runtime
    except ImportError:
        logger.warning("maxminddb package is not installed; geo-fence cannot do offline lookups.")
        return None

    try:
        reader = maxminddb.open_database(str(db_path))
    except Exception as exc:  # noqa: BLE001 — bad DB file, corrupt, etc.
        logger.warning("Failed to open MaxMind DB at %s: %s", db_path, exc)
        return None

    _reader_cache["reader"] = reader
    _reader_cache["available"] = True
    return reader


def _maxmind_lookup(client_ip: str, db_path: Optional[Path] = None) -> Optional[str]:
    """Return ISO country code for ``client_ip`` via MaxMind, or ``None``."""
    if not client_ip:
        return None
    reader = _get_maxmind_reader(db_path)
    if reader is None:
        return None
    try:
        result = reader.get(client_ip)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.warning("MaxMind lookup failed for %s: %s", client_ip, exc)
        return None
    if not isinstance(result, dict):
        return None
    country = result.get("country") or {}
    iso = country.get("iso_code")
    return iso.upper() if isinstance(iso, str) else None


# ── Detection ───────────────────────────────────────────────────────────────
def _header_country(headers, names: Iterable[str]) -> Optional[str]:
    """Header lookup trying each name as given and lower-cased. Returns upper-cased ISO-2."""
    for name in names:
        value = headers.get(name) or headers.get(name.lower())
        if value:
            value = str(value).strip().upper()
            if len(value) == 2 and value.isalpha() and value not in {"XX", "T1"}:  # CF unknown / Tor
                return value
    return None


def detect_country(request, db_path: Optional[Path] = None) -> Optional[str]:
    """Detect the ISO country code for direct traffic (edge headers, then MaxMind).

    Args:
        request: An object exposing a ``.headers`` mapping (e.g. ``fastapi.Request``,
            ``starlette.requests.Request``, or a plain mapping for tests).
        db_path: Optional override for the MaxMind DB path.

    Returns:
        The detected ISO 3166-1 alpha-2 country code, or ``None`` if unknown.
    """
    headers = getattr(request, "headers", None)
    if headers is None:
        return None

    edge = list(load_policy().get("edge_country_headers") or [])
    # Accept the legacy capitalised spellings when callers pass a plain dict.
    names: list[str] = []
    for h in edge:
        names.append(h)
        if h == "cf-ipcountry":
            names.append("CF-IPCountry")
        elif h == "x-vercel-ip-country":
            names.append("X-Vercel-IP-Country")
    country = _header_country(headers, names)
    if country:
        return country

    client_ip = None
    if hasattr(request, "client") and request.client is not None:
        client_ip = getattr(request.client, "host", None)
    if not client_ip:
        client_ip = (headers.get("x-forwarded-for") or "").split(",")[0].strip() or None

    if client_ip:
        country = _maxmind_lookup(client_ip, db_path)
        if country:
            return country

    return None


def trusted_forwarded_country(request) -> Optional[str]:
    """Country from the trusted forwarded header, only if the master API key is present."""
    principal = _api_principal(request)
    if principal is None or not getattr(principal, "is_master", False):
        return None
    header = str(load_policy().get("trusted_country_header") or "")
    if not header:
        return None
    return _header_country(getattr(request, "headers", {}) or {}, [header])


def _api_principal(request):
    """Resolve the API-key principal on ``request`` (``None`` if absent/invalid)."""
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    try:
        from gaming.src.backend.rematch_auth import extract_api_key, resolve_api_key
    except Exception:  # noqa: BLE001 — auth module unavailable → treat as unkeyed
        return None
    got = extract_api_key(
        x_rematch_key=headers.get("x-rematch-key") or headers.get("X-Rematch-Key"),
        x_boardman_key=headers.get("x-boardman-key") or headers.get("X-Boardman-Key"),
        x_stack_key=headers.get("x-stack-key") or headers.get("X-Stack-Key"),
        authorization=headers.get("authorization") or headers.get("Authorization"),
    )
    try:
        return resolve_api_key(got)
    except Exception:  # noqa: BLE001
        return None


def _request_method_path(request) -> tuple[str, str]:
    url = getattr(request, "url", None)
    path = getattr(url, "path", "") if url is not None else ""
    return str(getattr(request, "method", "") or "").upper(), str(path or "")


# ── Public API ──────────────────────────────────────────────────────────────
def check_region(request, blocked: Optional[Iterable[str]] = None,
                 db_path: Optional[Path] = None) -> Optional[str]:
    """Detect the request's country code and enforce the geo-fence.

    Args:
        request: Request-like object exposing ``.headers`` (and, for HTTP
            requests, ``.method`` and ``.url.path``).
        blocked: Optional override for the blocked-region set (skips disk cache).
        db_path: Optional override for the MaxMind DB path.

    Returns:
        The detected ISO country code (uppercase), or ``None`` if unknown.

    Raises:
        BlockedRegionError: if the detected country is in the blocked list.
        RegionUnverifiedError: strict mode, money route, and the country is
            unknown or the blocked list failed to load.
    """
    method, path = _request_method_path(request)
    money = bool(path) and money_route_kind(method, path) is not None
    strict = money and strict_mode()

    country = detect_country(request, db_path=db_path)

    if blocked is not None:
        blocked_set = {str(c).upper() for c in blocked if isinstance(c, (str, int))}
        list_ok = True
    else:
        blocked_set = _load_blocked_regions()
        list_ok = _blocked_cache_ok

    if strict and not list_ok:
        raise RegionUnverifiedError("blocklist_unavailable")
    if country is None:
        if strict:
            raise RegionUnverifiedError("country_unknown")
        return None
    if country in blocked_set:
        raise BlockedRegionError(country)
    return country


@dataclass
class GeoDecision:
    """Outcome of ``evaluate_request``."""

    allowed: bool
    reason: str
    country: Optional[str] = None
    money_kind: Optional[str] = None
    strict: bool = False
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def status_code(self) -> int:
        if self.allowed:
            return 200
        return 503 if self.reason == "blocklist_unavailable" else 451

    def body(self) -> dict[str, Any]:
        if self.reason == "blocked":
            return {"error": "service_unavailable_in_region"}
        if self.reason == "blocklist_unavailable":
            return {"error": "geo_fence_unavailable"}
        return {
            "error": "region_unverified",
            "detail": "This action needs a verifiable location and is not available right now.",
        }


def evaluate_request(request) -> GeoDecision:
    """Full geo-fence policy decision for an HTTP request.

    Order:
      1. Exempt paths (health, docs, signed webhooks) → allow.
      2. ``GEO_FENCE_DISABLED`` → allow, except money routes in strict mode.
      3. API-key traffic on a non-money route → allow (server-to-server).
      4. Country: master key → trusted forwarded header only; builder key or
         no key → edge headers, then MaxMind.
      5. Blocked country → 451 ``service_unavailable_in_region``.
      6. Strict + money route + (unknown country or unreadable list) → refuse.
    """
    method, path = _request_method_path(request)

    if is_exempt_path(path):
        return GeoDecision(True, "exempt")

    kind = money_route_kind(method, path)
    strict = strict_mode()
    fail_closed = strict and kind is not None

    if _env_flag("GEO_FENCE_DISABLED"):
        if not fail_closed:
            return GeoDecision(True, "disabled", money_kind=kind, strict=strict)
        logger.warning("GEO_FENCE_DISABLED ignored for money route %s %s in strict mode", method, path)

    principal = _api_principal(request)
    if principal is not None and kind is None:
        return GeoDecision(True, "api_key_non_money", strict=strict)

    if principal is not None and getattr(principal, "is_master", False):
        country = trusted_forwarded_country(request)
        source = "forwarded" if country else ""
    else:
        country = detect_country(request)
        source = "edge_or_ip" if country else ""

    blocked_set = _load_blocked_regions()
    list_ok = _blocked_cache_ok

    if country and country in blocked_set:
        return GeoDecision(False, "blocked", country, kind, strict, source)
    if fail_closed and not list_ok:
        return GeoDecision(False, "blocklist_unavailable", country, kind, strict, source)
    if fail_closed and country is None:
        return GeoDecision(False, "country_unknown", None, kind, strict, source)
    if country is None and kind is not None:
        logger.info("geo-fence: money route %s %s allowed with unknown country (strict off)", method, path)
    return GeoDecision(True, "allowed", country, kind, strict, source)
