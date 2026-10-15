"""Channel-neutral button ids: ``v1|<flow>|<act>|<arg>``, at most 64 bytes.

64 bytes is Telegram's ``callback_data`` cap, so one id works everywhere.
Anything longer or sensitive goes in a server-side token and only its handle
travels in the id. Every action re-validates state: WhatsApp buttons stay
tappable forever.
"""
from __future__ import annotations

from typing import Optional

PREFIX = "v1"
MAX_BYTES = 64


def encode(flow: str, act: str, arg: str = "") -> str:
    for part in (flow, act, arg):
        if "|" in part:
            raise ValueError("'|' is reserved in button ids")
    out = f"{PREFIX}|{flow}|{act}|{arg}"
    if len(out.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"button id over {MAX_BYTES} bytes: use a server-side token")
    return out


def decode(raw: str) -> Optional[tuple[str, str, str]]:
    parts = (raw or "").split("|")
    if len(parts) != 4 or parts[0] != PREFIX or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2], parts[3]


def is_core(raw: str) -> bool:
    return (raw or "").startswith(PREFIX + "|")
