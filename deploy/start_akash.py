#!/usr/bin/env python3
"""Akash entrypoint: run API + Telegram bot; exit if either dies.

Pure Python (no bash). Creates monorepo-compat symlinks and preflights imports
so crash reasons show up clearly in Akash logs.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import traceback


def _ensure_layout() -> None:
    """Match start_free_local.sh package layout used by imports."""
    os.chdir("/app")
    os.makedirs("/app/gaming", exist_ok=True)

    links = {
        "/app/gaming/src": "/app/src",
        "/app/gaming/config": "/app/config",
        "/app/backend": "/app/src/backend",
    }
    for dest, src in links.items():
        if os.path.islink(dest) or os.path.exists(dest):
            continue
        try:
            os.symlink(src, dest)
            print(f"[akash] linked {dest} -> {src}", flush=True)
        except FileExistsError:
            pass

    init = "/app/gaming/__init__.py"
    if not os.path.exists(init):
        open(init, "a", encoding="utf-8").close()


def _preflight() -> None:
    """Fail fast with a clear traceback if imports are broken."""
    print("[akash] preflight: checking imports…", flush=True)
    try:
        import backend.supabase_client  # noqa: F401
        import gaming.src.backend.main  # noqa: F401
        import gaming.src.bot.main  # noqa: F401
    except Exception:
        print("[akash] FATAL: preflight import failed:", flush=True)
        traceback.print_exc()
        raise SystemExit(1)
    print("[akash] preflight: OK", flush=True)


def main() -> int:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONPATH", "/app")
    os.environ.setdefault("CLAWSTATION_BOT_MODE", "polling")
    os.environ.setdefault("CLAW_DEFAULT_CHAIN", "arc")
    port = os.environ.get("PORT", "8000")
    os.environ.setdefault("PORT", port)
    os.environ.setdefault(
        "BLOCKED_REGIONS_FILE",
        os.environ.get("BLOCKED_REGIONS_FILE", "/app/config/blocked_regions.json"),
    )

    _ensure_layout()

    token = (
        os.environ.get("TELEGRAM_BOT_TOKEN_BOARDMAN")
        or os.environ.get("TELEGRAM_BOT_TOKEN_CLAWSTATION")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
    )
    if not token:
        print(
            "[akash] FATAL: TELEGRAM_BOT_TOKEN_BOARDMAN (or TELEGRAM_BOT_TOKEN_CLAWSTATION / TELEGRAM_BOT_TOKEN) is not set",
            flush=True,
        )
        return 1

    print(
        f"[akash] env ok token_len={len(token)} chain={os.environ.get('CLAW_DEFAULT_CHAIN')} mode={os.environ.get('CLAWSTATION_BOT_MODE')}",
        flush=True,
    )

    try:
        _preflight()
    except SystemExit as e:
        return int(e.code or 1)

    env = os.environ.copy()
    env["PYTHONPATH"] = "/app"

    print(f"[akash] starting API on :{port}", flush=True)
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "gaming.src.backend.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        env=env,
    )

    # Give API a moment so bot and API don't stampede CPU on 0.5 cores
    time.sleep(2)

    print("[akash] starting Rematch bot (polling)", flush=True)
    bot = subprocess.Popen(
        [sys.executable, "-m", "gaming.src.bot.main"],
        env=env,
    )

    procs = [api, bot]

    def shutdown(signum: int | None = None, _frame=None) -> None:
        print(f"[akash] shutting down (signal={signum})", flush=True)
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        deadline = time.time() + 10
        for p in procs:
            remaining = max(0.1, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    while True:
        for name, p in (("api", api), ("bot", bot)):
            code = p.poll()
            if code is not None:
                print(
                    f"[akash] {name} exited with code {code} — stopping container",
                    flush=True,
                )
                shutdown()
                return code if code else 1
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
