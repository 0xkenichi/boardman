#!/usr/bin/env python3
"""Raja challenges Nero on Lichess (two BOT accounts).

Boardman House pairing is separate — this only hits Lichess so the public
can watch. Requires LICHESS_API_TOKEN (Raja) and a Nero BOT already online.

  python3 builders/lichess_bots/challenge.py
  python3 builders/lichess_bots/challenge.py --to keniichii --minutes 3 --inc 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
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


def main() -> int:
    env = {**_load_dotenv(), **os.environ}
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", default=env.get("NERO_LICHESS_USER") or "keniichii")
    parser.add_argument("--minutes", type=int, default=3)
    parser.add_argument("--inc", type=int, default=2)
    parser.add_argument("--rated", action="store_true")
    args = parser.parse_args()

    token = (
        env.get("LICHESS_RAJA_API_TOKEN")
        or env.get("LICHESS_BOT_TOKEN")
        or env.get("LICHESS_API_TOKEN")
        or ""
    ).strip()
    if not token:
        print("missing LICHESS_API_TOKEN (Raja)", file=sys.stderr)
        return 1

    body = urllib.parse.urlencode(
        {
            "rated": "true" if args.rated else "false",
            "clock.limit": str(args.minutes * 60),
            "clock.increment": str(args.inc),
            "color": "random",
            "variant": "standard",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://lichess.org/api/challenge/{args.to}",
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
        print(exc.read().decode()[:400], file=sys.stderr)
        return 1
    ch = data.get("challenge") or data
    cid = ch.get("id")
    print(f"challenged {args.to} → https://lichess.org/{cid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
