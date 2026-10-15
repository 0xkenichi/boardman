"""Who is talking to us, on which channel, with which country signals."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class CountrySignal:
    """A country claim and where it came from (CHANNELS_DESIGN §5).

    ``source``: ``phone_cc`` (WhatsApp calling code), ``ip`` (web edge),
    ``kyc`` or ``tg_contact``. ``country`` is ISO-3166 alpha-2, or None when
    the source exists but could not be resolved.
    """

    source: str
    country: Optional[str]


@dataclass
class Principal:
    channel: str
    external_id: str
    profile_id: Optional[str] = None
    identity_id: Optional[str] = None
    display_name: str = ""
    address: Optional[str] = None  # where to deliver (TG chat id, E.164 phone)
    country_signals: list[CountrySignal] = field(default_factory=list)
    withdraw_hold_until: Optional[datetime] = None
    profile: dict = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return bool(self.profile_id)

    def withdraw_hold_active(self, now: Optional[datetime] = None) -> bool:
        if self.withdraw_hold_until is None:
            return False
        now = now or datetime.now(timezone.utc)
        return self.withdraw_hold_until > now
