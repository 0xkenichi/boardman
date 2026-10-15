"""Country signals from chat channels, judged by the one blocked list
(CHANNELS_DESIGN §5).

A WhatsApp ``wa_id`` is the sender's phone number, so its calling code says
where the SIM is registered (not where the user is). ``channel_geo_decision``
denies a money action when any known signal is a blocked country, and in strict
mode requires at least one signal from a source the policy accepts for money.

Policy lives in ``config/compliance/geo_fence.json`` under ``channel_signals``.
``money_ok`` for ``phone_cc`` is counsel's call [COUNSEL]. ``enforce: false``
(Telegram today) only logs the decision: nothing new is blocked on Telegram.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from gaming.src.backend.middleware import geo_fence
from gaming.src.backend.middleware.geo_fence import GeoDecision
from gaming.src.channels.core.principal import CountrySignal, Principal

logger = logging.getLogger(__name__)

# ITU calling codes -> ISO country. Longest prefix wins. Not exhaustive: an
# unknown code yields no country (a strict-mode money action then needs another
# signal). The full mapping would come from `phonenumbers` [?].
CALLING_CODES: dict[str, str] = {
    "20": "EG", "27": "ZA", "30": "GR", "31": "NL", "32": "BE", "33": "FR", "34": "ES",
    "36": "HU", "39": "IT", "40": "RO", "41": "CH", "43": "AT", "44": "GB", "45": "DK",
    "46": "SE", "47": "NO", "48": "PL", "49": "DE", "51": "PE", "52": "MX", "54": "AR",
    "55": "BR", "56": "CL", "57": "CO", "58": "VE", "60": "MY", "61": "AU", "62": "ID",
    "63": "PH", "64": "NZ", "65": "SG", "66": "TH", "81": "JP", "82": "KR", "84": "VN",
    "86": "CN", "90": "TR", "91": "IN", "92": "PK", "93": "AF", "94": "LK", "95": "MM",
    "98": "IR", "211": "SS", "212": "MA", "213": "DZ", "216": "TN", "218": "LY",
    "220": "GM", "221": "SN", "222": "MR", "223": "ML", "224": "GN", "225": "CI",
    "226": "BF", "227": "NE", "228": "TG", "229": "BJ", "230": "MU", "231": "LR",
    "232": "SL", "233": "GH", "234": "NG", "235": "TD", "236": "CF", "237": "CM",
    "238": "CV", "239": "ST", "240": "GQ", "241": "GA", "242": "CG", "243": "CD",
    "244": "AO", "245": "GW", "248": "SC", "249": "SD", "250": "RW", "251": "ET",
    "252": "SO", "253": "DJ", "254": "KE", "255": "TZ", "256": "UG", "257": "BI",
    "258": "MZ", "260": "ZM", "261": "MG", "263": "ZW", "264": "NA", "265": "MW",
    "266": "LS", "267": "BW", "268": "SZ", "269": "KM", "291": "ER",
    "351": "PT", "353": "IE", "354": "IS", "358": "FI", "380": "UA",
    "852": "HK", "880": "BD", "886": "TW", "961": "LB", "962": "JO", "963": "SY",
    "964": "IQ", "965": "KW", "966": "SA", "967": "YE", "968": "OM", "971": "AE",
    "972": "IL", "973": "BH", "974": "QA", "850": "KP",
}

# +1 (NANP) and +7 share one code between countries: the area code decides.
_CA_AREA_CODES = {
    "204", "226", "236", "249", "250", "263", "289", "306", "343", "354", "365", "367",
    "368", "382", "387", "403", "416", "418", "428", "431", "437", "438", "450", "468",
    "474", "506", "514", "519", "548", "579", "581", "584", "587", "600", "604", "613",
    "639", "647", "672", "683", "705", "709", "742", "753", "778", "780", "782", "807",
    "819", "825", "867", "873", "879", "902", "905",
}
_NANP_OTHER = {"242": "BS", "246": "BB", "268": "AG", "441": "BM", "473": "GD", "758": "LC",
               "767": "DM", "784": "VC", "809": "DO", "829": "DO", "849": "DO", "868": "TT",
               "876": "JM", "658": "JM", "869": "KN", "787": "PR", "939": "PR", "671": "GU"}


def country_from_phone(phone: str) -> Optional[str]:
    """ISO country for an E.164 number (``+234…`` or digits ``234…``), else None."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) < 7:
        return None
    if digits.startswith("1"):
        area = digits[1:4]
        if area in _CA_AREA_CODES:
            return "CA"
        # Every other +1 number is treated as US: the conservative reading for
        # a blocking signal.
        return _NANP_OTHER.get(area, "US")
    if digits.startswith("7"):
        return "KZ" if digits[1:2] in {"6", "7"} else "RU"
    for n in (3, 2):
        hit = CALLING_CODES.get(digits[:n])
        if hit:
            return hit
    return None


_DEFAULT_SIGNALS = {
    "whatsapp": {"source": "phone_cc", "money_ok": True, "spectator_ok": False, "enforce": True},
    "telegram": {"source": "none", "money_ok": False, "spectator_ok": False, "enforce": False},
    "web": {"source": "ip", "money_ok": True, "spectator_ok": True, "enforce": True},
}


def channel_policy(channel: str) -> dict:
    pol = (geo_fence.load_policy() or {}).get("channel_signals") or {}
    merged = dict(_DEFAULT_SIGNALS.get(channel, {"source": "none", "money_ok": False, "enforce": True}))
    own = pol.get(channel)
    if isinstance(own, dict):
        merged.update(own)
    return merged


def _money_ok_sources() -> set[str]:
    """Signal sources the policy accepts for money (plus KYC, always)."""
    pol = (geo_fence.load_policy() or {}).get("channel_signals") or {}
    srcs = {"kyc"}
    for ch in set(_DEFAULT_SIGNALS) | {k for k in pol if not k.startswith("_")}:
        p = channel_policy(ch)
        if p.get("money_ok") and p.get("source") not in (None, "none"):
            srcs.add(p["source"])
    return srcs


def channel_geo_decision(signals: Iterable[CountrySignal], money_kind: str) -> GeoDecision:
    sigs = [s for s in signals if s is not None]
    blocked = geo_fence._load_blocked_regions()
    list_ok = geo_fence.blocked_list_loaded()
    strict = geo_fence.strict_mode()
    for s in sigs:
        if s.country and s.country in blocked:
            return GeoDecision(False, "blocked", s.country, money_kind, strict, s.source)
    if strict and not list_ok:
        return GeoDecision(False, "blocklist_unavailable", None, money_kind, strict, "")
    ok_sources = _money_ok_sources()
    usable = [s for s in sigs if s.country and s.source in ok_sources]
    if strict and not usable:
        return GeoDecision(False, "country_unknown", None, money_kind, strict, "")
    first = usable[0] if usable else next((s for s in sigs if s.country), None)
    return GeoDecision(
        True, "allowed", first.country if first else None, money_kind, strict, first.source if first else ""
    )


def check_money(principal: Principal, money_kind: str) -> Optional[GeoDecision]:
    """The decision when it refuses AND the channel enforces; else None.

    Every refusal is logged with its ``country_source``, enforced or not.
    """
    decision = channel_geo_decision(principal.country_signals, money_kind)
    if decision.allowed:
        return None
    enforce = bool(channel_policy(principal.channel).get("enforce", True))
    logger.info(
        "channel geo %s reason=%s country=%s country_source=%s kind=%s channel=%s",
        "denied" if enforce else "would-deny (observe only)",
        decision.reason, decision.country, decision.source, money_kind, principal.channel,
    )
    return decision if enforce else None


def refusal_text(decision: GeoDecision) -> str:
    if decision.reason == "blocked":
        return "Sorry, money features are not available for your region."
    if decision.reason == "blocklist_unavailable":
        return "Money features are briefly unavailable. Please try again later."
    return "This action needs a verifiable location and is not available right now."
