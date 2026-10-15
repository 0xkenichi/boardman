"""What flows say, independent of any channel (CHANNELS_DESIGN §3.2).

Flows emit these objects and never format for a channel. Bodies use a tiny
markup every renderer understands: ``*bold*`` and ```mono``` (WhatsApp's own
syntax; Telegram renders them as HTML, SMS strips them).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

# Option id the renderers map to each channel's main menu.
MENU_ID = "v1|menu|open|"


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    description: str = ""


@dataclass
class Text:
    body: str


@dataclass
class Choice:
    """Pick one. Renderers degrade: buttons, then a (paged) list, then numbers."""

    body: str
    options: list[Option] = field(default_factory=list)
    button_label: str = "Choose"
    page: int = 0


@dataclass
class LinkButton:
    """One URL action (WhatsApp allows exactly one per message)."""

    body: str
    url: str
    label: str


@dataclass
class MediaRequest:
    """Ask the user to send a photo or document."""

    body: str
    kind: str = "image"


Out = Union[Text, Choice, LinkButton, MediaRequest]


def plain(body: str) -> str:
    """Body without markup (SMS, logs)."""
    return body.replace("*", "").replace("`", "")
