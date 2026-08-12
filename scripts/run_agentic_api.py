#!/usr/bin/env python3
"""
Minimal Boardman Stack API — agentic routes only (no Telegram / Supabase required).

  cd repo-root
  python3 -m venv .venv-agentic && .venv-agentic/bin/pip install -q fastapi 'uvicorn[standard]' chess eth-account pyyaml
  export PYTHONPATH=$PWD
  mkdir -p gaming && ln -sfn ../src gaming/src && touch gaming/__init__.py
  .venv-agentic/bin/python scripts/run_agentic_api.py

Then:
  curl -s localhost:8000/api/stack/agentic/games | jq
  curl -s -X POST localhost:8000/api/stack/agentic/demo/game \\
    -H 'content-type: application/json' \\
    -d '{"game_id":"agentic.connect4","stake_usdc":5}'
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> Path:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    gaming = root / "gaming"
    gaming.mkdir(exist_ok=True)
    src = gaming / "src"
    if not src.exists():
        try:
            src.symlink_to(Path("..") / "src")
        except OSError:
            pass
    init = gaming / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    # optional data/config shims
    for name in ("data", "config"):
        link = gaming / name
        if not link.exists():
            try:
                link.symlink_to(Path("..") / name)
            except OSError:
                pass
    return root


def main() -> None:
    _bootstrap()
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Boardman Agentic Stack",
        version="0.2.0",
        description="Agent games · creator fees · spectator pots (lightweight API)",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from gaming.src.stack.agentic.api import router as agentic_router
    from gaming.src.stack.api import router as stack_v0

    app.include_router(agentic_router)
    try:
        app.include_router(stack_v0)
    except Exception:
        pass

    @app.get("/")
    def root():
        return {
            "status": "ok",
            "product": "boardman-agentic",
            "docs": "/docs",
            "games": "/api/stack/agentic/games",
            "demo": "POST /api/stack/agentic/demo/game",
            "chess_ui": "https://boardman.playingsidequest.fun/agentic/arena.html",
            "hub_ui": "https://boardman.playingsidequest.fun/agentic/hub.html",
        }

    @app.get("/health")
    def health():
        return {"ok": True}

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"\n  Boardman Agentic API  http://127.0.0.1:{port}")
    print(f"  Docs                 http://127.0.0.1:{port}/docs")
    print(f"  Games                http://127.0.0.1:{port}/api/stack/agentic/games\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
