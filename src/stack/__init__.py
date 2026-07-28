"""
Rematch Stack — platform layer under Rematch experiences.

Builders depend on this package (and /api/stack/v0), not on Telegram handlers.
"""
from __future__ import annotations

from gaming.src.stack.facade import RematchStack, get_stack
from gaming.src.stack.types import ChainInfo, StackCapabilities, StackHealth

__all__ = [
    "RematchStack",
    "get_stack",
    "ChainInfo",
    "StackCapabilities",
    "StackHealth",
]

__version__ = "0.1.0"
