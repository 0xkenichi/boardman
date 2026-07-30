#!/usr/bin/env python3
"""Akash entrypoint: run API + Telegram bot; exit if either dies.

Uses pure Python so the image does not depend on bash (python:slim often has none).
Logs to stdout for Akash Console.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def main() -> int:
    os.chdir("/app")
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

    # gaming.src.* layout
    gaming = "/app/gaming"
    src = "/app/src"
    if not os.path.exists(f"{gaming}/src"):
        os.makedirs(gaming, exist_ok=True)
        try:
            os.symlink(src, f"{gaming}/src")
        except FileExistsError:
            pass
        open(f"{gaming}/__init__.py", "a").close()

    token = os.environ.get("TELEGRAM_BOT_TOKEN_CLAWSTATION") or os.environ.get(
        "TELEGRAM_BOT_TOKEN"
    )
    if not token:
        print(
            "[akash] FATAL: TELEGRAM_BOT_TOKEN_CLAWSTATION (or TELEGRAM_BOT_TOKEN) is not set",
            flush=True,
        )
        return 1

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
        env=os.environ.copy(),
    )

    print("[akash] starting Rematch bot (polling)", flush=True)
    bot = subprocess.Popen(
        [sys.executable, "-m", "gaming.src.bot.main"],
        env=os.environ.copy(),
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

    # Supervise: if either exits, tear down and exit non-zero so Akash restarts.
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
