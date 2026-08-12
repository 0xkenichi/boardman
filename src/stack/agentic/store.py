"""JSON file store under data/agentic/ (no DB required for demo / Phase 1)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


_lock = threading.RLock()


def data_dir() -> Path:
    env = os.getenv("BOARDMAN_AGENTIC_DATA")
    if env:
        p = Path(env)
    else:
        # repo_root/data/agentic — works from monorepo or gaming/ layout
        here = Path(__file__).resolve()
        # .../src/stack/agentic/store.py → repo root is parents[3]
        root = here.parents[3]
        p = root / "data" / "agentic"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(name: str) -> Path:
    return data_dir() / name


def load_json(name: str, default: Any) -> Any:
    path = _path(name)
    with _lock:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default


def save_json(name: str, payload: Any) -> None:
    path = _path(name)
    with _lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)
