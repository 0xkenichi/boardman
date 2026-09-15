#!/usr/bin/env python3
"""Raja vs Nero 24/7 on Lichess: re-challenge whenever neither is in a game.

Boardman House pairing (scripts/run_house_session.py) is the money path and
runs independently of Lichess. This loop only keeps the public gym pairing
alive: it polls Raja's account, and when neither bot has an active game it
sends a fresh challenge to Nero.

  python3 builders/lichess_bots/challenge_loop.py                 # every 90s
  python3 builders/lichess_bots/challenge_loop.py --interval 120
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    p = ROOT / ".env"
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _raja_token(env: dict[str, str]) -> str:
    return (
        env.get("LICHESS_RAJA_API_TOKEN")
        or env.get("LICHESS_BOT_TOKEN")
        or env.get("LICHESS_API_TOKEN")
        or ""
    ).strip()


def _nero_user(env: dict[str, str]) -> str:
    return env.get("NERO_LICHESS_USER") or "keniichii"


def _get_json(url: str, token: str | None = None) -> dict | None:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=20
        ) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _has_active_game(token: str) -> bool:
    data = _get_json("https://lichess.org/api/account/playing", token)
    if data is None:
        return True  # unknown → be conservative, don't double-challenge
    return bool(data.get("nowPlaying"))


def _challenge(env: dict[str, str], to: str, minutes: int, inc: int, rated: bool) -> bool:
    token = _raja_token(env)
    body = urllib.parse.urlencode(
        {
            "rated": "true" if rated else "false",
            "clock.limit": str(minutes * 60),
            "clock.increment": str(inc),
            "color": "random",
            "variant": "standard",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://lichess.org/api/challenge/{to}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"  challenge rejected: {exc.read().decode()[:200]}", flush=True)
        return False
    except Exception as exc:
        print(f"  challenge failed: {exc}", flush=True)
        return False
    ch = data.get("challenge") or data
    cid = ch.get("id")
    print(f"  challenged {to} → https://lichess.org/{cid}", flush=True)
    return bool(cid)


def main() -> int:
    env = {**_load_dotenv(), **os.environ}
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=90, help="seconds between checks")
    parser.add_argument("--minutes", type=int, default=3)
    parser.add_argument("--inc", type=int, default=2)
    parser.add_argument("--rated", action="store_true")
    args = parser.parse_args()

    token = _raja_token(env)
    if not token:
        print("missing LICHESS_RAJA_API_TOKEN in .env", file=sys.stderr)
        return 1
    to = _nero_user(env)

    print(f"challenge loop: Raja ({token[:6]}…) will keep challenging {to} every {args.interval}s", flush=True)
    while True:
        try:
            if _has_active_game(token):
                print("  game in progress — waiting", flush=True)
            elif _challenge(env, to, args.minutes, args.inc, args.rated):
                print("  challenge sent — waiting for the next game to finish", flush=True)
        except Exception as exc:
            print(f"  loop error: {exc}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())