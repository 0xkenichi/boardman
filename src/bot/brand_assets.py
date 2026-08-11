"""Boardman brand asset paths for the Telegram bot (logo, site links)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# gaming/src/bot/brand_assets.py → parents[3] = repo root (via gaming symlink)
_HERE = Path(__file__).resolve()
_REPO_ROOTS = [
    _HERE.parents[2],  # src/ → repo when not via gaming/
    _HERE.parents[3],  # gaming/src/bot → repo root
    Path.cwd(),
]

# Prefer square PNG for Telegram photos
_LOGO_CANDIDATES = (
    "frontend/public/brand/icon-512.png",
    "frontend/public/brand/boardman-logo.png",
    "frontend/public/boardman-logo.png",
    "frontend/public/rematch/icon-512.png",
    "frontend/public/boardman-logo.jpg",
)


def boardman_site_url() -> str:
    return (
        os.getenv("REMATCH_WEB_URL")
        or os.getenv("BOARDMAN_URL")
        or os.getenv("NEXT_PUBLIC_BOARDMAN_URL")
        or "https://boardman.playingsidequest.fun"
    ).rstrip("/")


def boardman_logo_path() -> Optional[Path]:
    """Absolute path to Boardman logo file on disk, if present."""
    explicit = (os.getenv("BOARDMAN_LOGO_PATH") or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p
    for root in _REPO_ROOTS:
        for rel in _LOGO_CANDIDATES:
            p = root / rel
            if p.is_file():
                return p
    return None


def boardman_logo_url() -> str:
    """Public HTTPS logo (for link previews / external use)."""
    return f"{boardman_site_url()}/boardman-logo.jpg"
