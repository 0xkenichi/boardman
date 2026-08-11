"""
Partner / onile (game center) attribution.

Players open t.me/<bot>?start=ctr_IKEJA01 → first-touch partner_code stored.
Settled match volume later credits partner_ledger (bps from platform fee).

Config: config/partners.yaml
Local attributions: data/partner_attributions.json (until profiles.partner_code column)
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_CONFIG = _ROOT / "config" / "partners.yaml"
_ATTR_PATH = Path(
    os.getenv(
        "PARTNER_ATTR_PATH",
        str(_ROOT / "data" / "partner_attributions.json"),
    )
)
_LEDGER_PATH = Path(
    os.getenv(
        "PARTNER_LEDGER_PATH",
        str(_ROOT / "data" / "partner_ledger.json"),
    )
)
_lock = threading.RLock()

_CODE_RE = re.compile(r"^[A-Z0-9]{3,16}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    defaults = {"volume_bps": 150, "payout_currency": "USDC", "status": "active"}
    partners: list[dict[str, Any]] = []
    if not _CONFIG.is_file():
        logger.warning("[Partners] missing %s", _CONFIG)
        return {"defaults": defaults, "partners": partners}
    try:
        import yaml

        raw = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[Partners] config load failed: %s", exc)
        # Seed so deep links still work offline without PyYAML
        raw = {
            "defaults": defaults,
            "partners": [
                {
                    "code": "IKEJA01",
                    "type": "center",
                    "display_name": "Ikeja Game Hub (demo)",
                    "city": "Lagos",
                    "area": "Ikeja",
                    "status": "active",
                    "volume_bps": 150,
                }
            ],
        }
    d = dict(raw.get("defaults") or {})
    for k, v in defaults.items():
        d.setdefault(k, v)
    for p in raw.get("partners") or []:
        if not isinstance(p, dict) or not p.get("code"):
            continue
        row = dict(p)
        row["code"] = str(row["code"]).strip().upper()
        row.setdefault("type", "center")
        row.setdefault("status", d.get("status") or "active")
        row.setdefault("volume_bps", d.get("volume_bps") or 150)
        partners.append(row)
    return {"defaults": d, "partners": partners}


def reload_partners() -> None:
    _load_config.cache_clear()


def list_partners(
    *,
    partner_type: Optional[str] = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    out = []
    for p in _load_config()["partners"]:
        if active_only and str(p.get("status") or "").lower() != "active":
            continue
        if partner_type and p.get("type") != partner_type:
            continue
        out.append(dict(p))
    return out


def get_partner(code: str) -> Optional[dict[str, Any]]:
    c = normalize_partner_code(code)
    if not c:
        return None
    for p in _load_config()["partners"]:
        if p.get("code") == c:
            return dict(p)
    return None


def normalize_partner_code(raw: str) -> str:
    s = (raw or "").strip().upper()
    # Accept ctr_IKEJA01 / center_IKEJA01 / IKEJA01
    for prefix in ("CTR_", "CENTER_", "ONILE_", "PARTNER_"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    s = re.sub(r"[^A-Z0-9]", "", s)
    if not _CODE_RE.match(s):
        return ""
    return s


def deep_link_payload(code: str) -> str:
    c = normalize_partner_code(code)
    return f"ctr_{c}" if c else ""


def partner_start_url(code: str, bot_url: Optional[str] = None) -> str:
    """Full t.me deep link for QR stickers."""
    payload = deep_link_payload(code)
    base = (bot_url or os.getenv("TELEGRAM_BOT_URL") or "https://t.me/myboardmanOfficialBot").rstrip(
        "/"
    )
    if not payload:
        return base
    return f"{base}?start={payload}"


def parse_start_payload(payload: str) -> tuple[str, str]:
    """
    Returns (kind, value).
    kind: partner | cup | match | unknown
    """
    p = (payload or "").strip()
    if not p:
        return "unknown", ""
    low = p.lower()
    if low.startswith(("ctr_", "center_", "onile_", "partner_")):
        code = normalize_partner_code(p)
        return ("partner", code) if code else ("unknown", "")
    if low.startswith(("cup_", "t_", "tour_")):
        code = p.split("_", 1)[1].strip().upper()
        return ("cup", code) if code else ("unknown", "")
    if low.startswith(("m_", "join_", "match_")):
        return "match", p.split("_", 1)[1].strip()
    # bare partner code?
    code = normalize_partner_code(p)
    if code and get_partner(code):
        return "partner", code
    return "unknown", p


# ── Attribution store ────────────────────────────────────────────────────────


def _load_attr() -> dict[str, Any]:
    with _lock:
        if not _ATTR_PATH.exists():
            return {"by_profile": {}}
        try:
            raw = json.loads(_ATTR_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {"by_profile": {}}
            raw.setdefault("by_profile", {})
            return raw
        except Exception:
            return {"by_profile": {}}


def _save_attr(data: dict) -> None:
    with _lock:
        _ATTR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ATTR_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_profile_partner(profile_id: str) -> Optional[dict[str, Any]]:
    if not profile_id:
        return None
    row = _load_attr()["by_profile"].get(str(profile_id))
    if not row:
        return None
    partner = get_partner(row.get("partner_code") or "")
    return {
        "partner_code": row.get("partner_code"),
        "attributed_at": row.get("attributed_at"),
        "partner": partner,
    }


def attribute_profile(
    profile_id: str,
    partner_code: str,
    *,
    first_touch_only: bool = True,
    source: str = "start_deeplink",
) -> dict[str, Any]:
    """
    Stamp partner on profile. First-touch by default (won't overwrite).
    Returns {ok, partner, changed, message}.
    """
    partner = get_partner(partner_code)
    if not partner:
        return {
            "ok": False,
            "partner": None,
            "changed": False,
            "message": "Unknown partner code",
        }
    if str(partner.get("status") or "").lower() != "active":
        return {
            "ok": False,
            "partner": partner,
            "changed": False,
            "message": "Partner is not active",
        }

    data = _load_attr()
    pid = str(profile_id)
    existing = data["by_profile"].get(pid)
    if existing and first_touch_only:
        return {
            "ok": True,
            "partner": get_partner(existing.get("partner_code") or "") or partner,
            "changed": False,
            "message": "Already attributed (first-touch)",
            "existing_code": existing.get("partner_code"),
        }

    data["by_profile"][pid] = {
        "partner_code": partner["code"],
        "attributed_at": _now(),
        "source": source,
    }
    _save_attr(data)
    logger.info(
        "[Partners] attributed profile=%s → %s (%s)",
        pid[:8],
        partner["code"],
        partner.get("display_name"),
    )
    return {
        "ok": True,
        "partner": partner,
        "changed": True,
        "message": "Attributed",
    }


def welcome_html(partner: dict[str, Any]) -> str:
    name = partner.get("display_name") or partner.get("code")
    area = partner.get("area") or partner.get("city") or ""
    where = f" · {area}" if area else ""
    return (
        f"🏪 <b>Welcome via {name}</b>{where}\n\n"
        f"You're playing through this <b>onile / game center</b>.\n"
        f"Lock stake → play (console, mobile, or table) → settle in USDC here.\n\n"
        f"Ask the desk for help with <b>New challenge</b> or tonight's <b>Cup</b>."
    )


# ── Volume ledger (credit on settle — call from settlement later) ────────────


def _load_ledger() -> dict[str, Any]:
    with _lock:
        if not _LEDGER_PATH.exists():
            return {"rows": []}
        try:
            raw = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {"rows": []}
            raw.setdefault("rows", [])
            return raw
        except Exception:
            return {"rows": []}


def _save_ledger(data: dict) -> None:
    with _lock:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def credit_partner_volume(
    *,
    partner_code: str,
    match_ref: str,
    volume_usdc: float,
    challenge_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """
    Credit partner share of matched volume (from platform fee, not extra player tax).
    volume_usdc = 2 * stake for dual lock (total matched).
    """
    partner = get_partner(partner_code)
    if not partner or volume_usdc <= 0:
        return None
    bps = int(partner.get("volume_bps") or _load_config()["defaults"].get("volume_bps") or 150)
    credit = round(float(volume_usdc) * bps / 10000.0, 4)
    if credit <= 0:
        return None
    row = {
        "id": f"{partner['code']}-{match_ref}-{_now()}",
        "partner_code": partner["code"],
        "match_ref": match_ref,
        "challenge_id": challenge_id,
        "volume_usdc": float(volume_usdc),
        "bps": bps,
        "credit_usdc": credit,
        "created_at": _now(),
        "paid": False,
    }
    data = _load_ledger()
    data["rows"].append(row)
    _save_ledger(data)
    logger.info(
        "[Partners] ledger +$%.4f to %s on volume $%.2f (%s bps)",
        credit,
        partner["code"],
        volume_usdc,
        bps,
    )
    return row


def partner_balance(partner_code: str) -> dict[str, float]:
    code = normalize_partner_code(partner_code)
    earned = 0.0
    paid = 0.0
    for r in _load_ledger()["rows"]:
        if r.get("partner_code") != code:
            continue
        c = float(r.get("credit_usdc") or 0)
        if r.get("paid"):
            paid += c
        else:
            earned += c
    return {"pending_usdc": round(earned, 4), "paid_usdc": round(paid, 4)}


def resolve_center_for_match(
    creator_profile_id: str,
    opponent_profile_id: Optional[str] = None,
    *,
    explicit_code: Optional[str] = None,
) -> Optional[str]:
    """
    Which center earns on this match?
    Prefer explicit challenge tag; else if both share same partner; else creator only.
    """
    if explicit_code:
        p = get_partner(explicit_code)
        return p["code"] if p else None
    c = get_profile_partner(creator_profile_id)
    o = get_profile_partner(opponent_profile_id) if opponent_profile_id else None
    c_code = (c or {}).get("partner_code")
    o_code = (o or {}).get("partner_code")
    if c_code and o_code and c_code == o_code:
        return c_code
    # Room play: creator walked in with QR — still credit center
    if c_code:
        return c_code
    return o_code
