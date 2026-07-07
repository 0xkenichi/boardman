"""
gaming/src/backend/middleware/geo_fence.py — IP-based geo-fence for ClawStation.

Detection priority:
    1. ``cf-ipcountry`` header (Cloudflare)
    2. ``x-vercel-ip-country`` header (Vercel)
    3. MaxMind GeoLite2 lookup against ``gaming/data/GeoLite2-Country.mmdb`` (offline)

If the MaxMind DB file is missing, the request is allowed (a warning is logged).
If the detected country is in the configured block list, ``BlockedRegionError`` is raised.

The blocked list is loaded from ``gaming/config/blocked_regions.json``. The path can be
overridden via the ``BLOCKED_REGIONS_FILE`` env var; the MaxMind DB path via ``MAXMIND_DB_PATH``.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[4]  # gaming/src/backend/middleware -> repo root
DEFAULT_BLOCKED_FILE = REPO_ROOT / "gaming" / "config" / "blocked_regions.json"
DEFAULT_MAXMIND_DB = REPO_ROOT / "gaming" / "data" / "GeoLite2-Country.mmdb"


class BlockedRegionError(Exception):
    """Raised when a request originates from a region ClawStation does not serve."""

    def __init__(self, country_code: str):
        self.country_code = (country_code or "").upper()
        super().__init__(f"Service unavailable in region: {self.country_code}")


# ── Blocked list (lazy-loaded, cached) ─────────────────────────────────────
_blocked_cache: Optional[set[str]] = None
_blocked_cache_path: Optional[str] = None


def _load_blocked_regions(path: Optional[Path] = None) -> set[str]:
    """Load the blocked-region set from disk. Returns an empty set on any error."""
    global _blocked_cache, _blocked_cache_path

    cfg_path = Path(path or os.getenv("BLOCKED_REGIONS_FILE") or DEFAULT_BLOCKED_FILE)
    cache_key = str(cfg_path)

    if _blocked_cache is not None and _blocked_cache_path == cache_key:
        return _blocked_cache

    blocked: set[str] = set()
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        raw = data.get("blocked", []) if isinstance(data, dict) else []
        blocked = {str(c).upper() for c in raw if isinstance(c, (str, int))}
    except FileNotFoundError:
        logger.warning("Blocked regions file not found at %s; no regions blocked.", cfg_path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load blocked regions from %s: %s", cfg_path, exc)

    _blocked_cache = blocked
    _blocked_cache_path = cache_key
    return blocked


def reset_blocked_cache() -> None:
    """Clear the cached blocked-region set (useful for tests)."""
    global _blocked_cache, _blocked_cache_path
    _blocked_cache = None
    _blocked_cache_path = None


# ── MaxMind reader (lazy, cached, optional) ────────────────────────────────
_reader_cache: dict[str, object] = {"reader": None, "path": None, "available": False}


def _get_maxmind_reader(path: Optional[Path] = None):
    """Return a cached ``maxminddb.open_database`` reader, or ``None`` if unavailable.

    The reader is opened lazily and cached for the process lifetime. If the DB
    file is missing or the library is unavailable, we return ``None`` and let the
    caller fall back to "allow".
    """
    db_path = Path(path or os.getenv("MAXMIND_DB_PATH") or DEFAULT_MAXMIND_DB)
    cache_key = str(db_path)

    if _reader_cache.get("path") == cache_key:
        return _reader_cache.get("reader") if _reader_cache.get("available") else None

    _reader_cache["path"] = cache_key
    _reader_cache["reader"] = None
    _reader_cache["available"] = False

    if not db_path.exists():
        logger.warning(
            "MaxMind GeoLite2 DB not found at %s; geo-fence will fall back to allowing the request. "
            "Download from https://dev.maxmind.com/geoip/geolite2-free-geolocation-data to enable offline lookups.",
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


# ── Public API ──────────────────────────────────────────────────────────────
def _header_country(headers, names: Iterable[str]) -> Optional[str]:
    """Case-insensitive header lookup. Returns the first match, upper-cased."""
    for name in names:
        value = headers.get(name)
        if value:
            value = value.strip().upper()
            if value and value not in {"XX", "T1"}:  # Cloudflare / Tor sentinels
                return value
    return None


def detect_country(request, db_path: Optional[Path] = None) -> Optional[str]:
    """Detect the ISO country code for ``request`` using the configured priority.

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

    country = _header_country(headers, ("cf-ipcountry", "CF-IPCountry"))
    if country:
        return country

    country = _header_country(headers, ("x-vercel-ip-country", "X-Vercel-IP-Country"))
    if country:
        return country

    client_ip = None
    if hasattr(request, "client") and request.client is not None:
        client_ip = getattr(request.client, "host", None)
    if not client_ip and headers is not None:
        client_ip = headers.get("x-forwarded-for", "").split(",")[0].strip() or None

    if client_ip:
        country = _maxmind_lookup(client_ip, db_path)
        if country:
            return country

    return None


def check_region(request, blocked: Optional[Iterable[str]] = None,
                 db_path: Optional[Path] = None) -> Optional[str]:
    """Detect the request's country code and enforce the geo-fence.

    Args:
        request: Request-like object exposing ``.headers``.
        blocked: Optional override for the blocked-region set (skips disk cache).
        db_path: Optional override for the MaxMind DB path.

    Returns:
        The detected ISO country code (uppercase), or ``None`` if unknown.

    Raises:
        BlockedRegionError: if the detected country is in the blocked list.
    """
    country = detect_country(request, db_path=db_path)
    if country is None:
        return None

    blocked_set = (
        {c.upper() for c in blocked if isinstance(c, (str, int))}
        if blocked is not None
        else _load_blocked_regions()
    )

    if country in blocked_set:
        raise BlockedRegionError(country)

    return country
