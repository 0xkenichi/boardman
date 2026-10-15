"""Inbound events, already parsed by an adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Media:
    kind: str  # image | document
    ref: str  # evidence://... once copied to our storage, else the provider id
    mime: str = ""
    sha256: str = ""
    caption: str = ""


@dataclass
class Inbound:
    channel: str
    external_id: str
    kind: str  # text | button | media | location | unsupported
    text: str = ""
    button_id: str = ""
    media: Optional[Media] = None
    message_id: str = ""
    phone: Optional[str] = None  # E.164 digits (WhatsApp)
    profile_name: str = ""
    address: Optional[str] = None  # delivery address (TG chat id / phone)
    context_id: str = ""  # id of the message being replied to (WhatsApp)
    timestamp: int = 0  # unix seconds
