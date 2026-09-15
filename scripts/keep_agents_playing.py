#!/usr/bin/env python3
"""Keep the Boardman stack alive 24/7, round the clock.

Supervises every process that makes Raja and Nero play chess continuously
and the venue they play on:

  - house-session  scripts/run_house_session.py --games 0   (Boardman money
                   path; pauses only when there is no fund, resumes when
                   funded)
  - api            uvicorn gaming.src.backend.main:app :8000 (arena site)
  - bot            gaming.src.bot.main (Telegram)
  - pike           builders/free_stockfish_agent.py :18763 (free agent)
  - lichess bots   builders/lichess_bots/run.py --agent raja|nero (public gym)
  - challenge-loop builders/lichess_bots/challenge_loop.py (Raja keeps
                   challenging Nero on Lichess)

Any child that dies is restarted with exponential backoff (so a permanently
broken child, e.g. an invalid token, cannot spin the CPU). The API child is
port-aware: it only (re)starts when :8000 is free, so a manually started
API wins and the supervisor fills in when it goes away. Exit the whole
supervisor with SIGTERM/SIGINT — children are terminated with it.

  PYTHONPATH=. nohup python3 scripts/keep_agents_playing.py >> logs/keep-agents-playing.log 2>&1 &

Env:
  KEEP_PLAYING_HOUSE    = "0" disables the Boardman house session
  KEEP_PLAYING_LICHESS  = "0" disables the Lichess bots + challenge loop
  KEEP_PLAYING_API      = "0" disables the API (:8000)
  KEEP_PLAYING_BOT      = "0" disables the Telegram bot
  KEEP_PLAYING_PIKE     = "0" disables the Pike webhook
  LICHESS_CHALLENGE_INTERVAL = seconds between re-challenges (default 90)
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PORT = int(os.getenv("PORT", "8000"))


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _port_listening(port: int) -> bool:
    try:
        s = socket.socket()
        s.settimeout(0.4)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def _children(enable_lichess: bool) -> list[dict]:
    py = sys.executable
    kids: list[dict] = [
        {
            "name": "api",
            "cmd": [
                py,
                "-m",
                "uvicorn",
                "gaming.src.backend.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(API_PORT),
            ],
            "port": API_PORT,
        },
        {
            "name": "bot",
            "cmd": [py, "-m", "gaming.src.bot.main"],
        },
        {
            "name": "pike",
            "cmd": [py, "builders/free_stockfish_agent.py"],
            "port": 18763,
        },
        {
            "name": "house-session",
            "cmd": [
                py,
                "scripts/run_house_session.py",
                "--games",
                os.environ.get("BOARDMAN_HOUSE_GAMES", "0"),
                "--delay",
                os.environ.get("BOARDMAN_HOUSE_MOVE_DELAY", "0.05"),
                "--pause",
                os.environ.get("BOARDMAN_HOUSE_PAUSE", "2"),
            ],
        },
    ]
    if enable_lichess:
        kids += [
            {
                "name": "lichess-raja",
                "cmd": [py, "builders/lichess_bots/run.py", "--agent", "raja"],
            },
            {
                "name": "lichess-nero",
                "cmd": [py, "builders/lichess_bots/run.py", "--agent", "nero"],
            },
            {
                "name": "challenge-loop",
                "cmd": [
                    py,
                    "builders/lichess_bots/challenge_loop.py",
                    "--interval",
                    os.environ.get("LICHESS_CHALLENGE_INTERVAL", "90"),
                ],
            },
        ]
    return kids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-every", type=float, default=5.0)
    args = parser.parse_args()

    os.chdir(ROOT)
    env = {**_load_dotenv(ROOT / ".env"), **os.environ}
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env.setdefault("PYTHONUNBUFFERED", "1")

    def enabled(name: str) -> bool:
        return os.environ.get(f"KEEP_PLAYING_{name}", "1") not in {
            "0",
            "false",
            "no",
        }

    specs = [
        s
        for s in _children(enable_lichess=enabled("LICHESS"))
        if s["name"] != "house-session" or enabled("HOUSE")
    ]
    if not specs:
        print("nothing to supervise — enable house, api, bot, pike and/or lichess", flush=True)
        return 1

    procs: dict[str, subprocess.Popen] = {}
    started_at: dict[str, float] = {}
    failures: dict[str, int] = {}
    stop = False

    def _spawn(spec: dict) -> None:
        # Port-guarded children never fight an external process for the port.
        if spec.get("port") and _port_listening(spec["port"]):
            print(
                f"[keep-playing] {spec['name']} skipped — port {spec['port']} already in use",
                flush=True,
            )
            return
        print(f"[keep-playing] starting {spec['name']}: {' '.join(spec['cmd'])}", flush=True)
        procs[spec["name"]] = subprocess.Popen(spec["cmd"], cwd=str(ROOT), env=env)
        started_at[spec["name"]] = time.time()

    def _shutdown(signum=None, _frame=None) -> None:
        nonlocal stop
        stop = True
        print(f"[keep-playing] signal {signum} — stopping children", flush=True)
        for p in procs.values():
            try:
                p.terminate()
            except Exception:
                pass
        deadline = time.time() + 10
        for p in list(procs.values()):
            remaining = max(0.1, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    for spec in specs:
        _spawn(spec)

    def _afm_tick() -> None:
        """Daily AFM heartbeat — open season matchdays / cup rounds, resolve due ones."""
        try:
            import sys

            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))  # keeper main process needs gaming on path
            from gaming.src.stack.agentic.games.football_managers.season import (
                tick as afm_tick,
            )

            out = afm_tick()
            if out.get("opened") or out.get("resolved") or out.get("season_status") == "finished":
                print(f"[afm] season tick → {out}", flush=True)
        except Exception as exc:  # never let the keeper die on AFM state
            print(f"[afm] season tick failed: {exc!r}", flush=True)
        try:
            from gaming.src.stack.agentic.games.football_managers.cup import (
                tick as afm_cup_tick,
            )

            out = afm_cup_tick()
            if out.get("opened") or out.get("resolved") or out.get("cup_status") == "finished":
                print(f"[afm] cup tick → {out}", flush=True)
        except Exception as exc:  # never let the keeper die on cup state
            print(f"[afm] cup tick failed: {exc!r}", flush=True)

    while not stop:
        time.sleep(args.check_every)
        _afm_tick()
        for spec in specs:
            name = spec["name"]
            p = procs.get(name)
            if p is None:
                _spawn(spec)
                continue
            code = p.poll()
            if code is None:
                continue
            uptime = time.time() - started_at.get(name, 0)
            if uptime >= 120:
                failures[name] = 0
            failures[name] = failures.get(name, 0) + 1
            delay = min(300, 15 * (2 ** failures[name]))
            procs.pop(name, None)
            # A port-guarded child that died because someone else took the
            # port (e.g. a manual restart-local.sh) should not be fought over:
            # if the port is taken again, wait for it to free up instead of
            # crash-looping.
            if spec.get("port") and _port_listening(spec["port"]):
                print(
                    f"[keep-playing] {name} exited code={code} — port {spec['port']} "
                    f"held by another process; waiting for it to free up",
                    flush=True,
                )
                continue
            print(
                f"[keep-playing] {name} exited code={code} after {uptime:.0f}s "
                f"(fail#{failures[name]}) — restart in {delay:.0f}s",
                flush=True,
            )
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                _shutdown()
                break
            if not stop:
                _spawn(spec)

    return 0


if __name__ == "__main__":
    sys.exit(main())