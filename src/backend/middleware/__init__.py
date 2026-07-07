"""
gaming/src/backend/middleware — HTTP and request-level middleware for the ClawStation gaming backend.

Exports:
    BlockedRegionError  — raised when a request originates from a blocked region.
    check_region        — detects the requester's ISO country code (header-first, MaxMind fallback).
"""

from gaming.src.backend.middleware.geo_fence import BlockedRegionError, check_region

__all__ = ["BlockedRegionError", "check_region"]
