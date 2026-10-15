#!/usr/bin/env python3
"""AFM clock: open/resolve due season matchdays and cup rounds, roll seasons over.

Season open/tick routes are admin-only, so this loop is what keeps the football
league playing in production (the Mac keeper ran the same tick inline). Run
exactly ONE ticker per data dir — deploy/start_akash.py starts it under the
``afm`` role, which docker-compose gives to the house container only.

    python scripts/afm_ticker.py            # loop forever (AFM_TICK_SEC, default 30)
    python scripts/afm_ticker.py --once     # one tick, then exit
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_stop = False


def _on_signal(_sig, _frame) -> None:
    global _stop
    _stop = True


def tick_once() -> None:
    try:
        from gaming.src.stack.agentic.games.football_managers.season import tick as season_tick

        out = season_tick()
        # Log what happened, not the idle state.
        if out.get("opened") or out.get("resolved") or out.get("action") in ("auto_open", "auto_open_failed"):
            print(f"[afm] season tick → {out}", flush=True)
    except Exception as exc:  # never let the clock die on AFM state
        print(f"[afm] season tick failed: {exc!r}", flush=True)
    try:
        from gaming.src.stack.agentic.games.football_managers.cup import tick as cup_tick

        out = cup_tick()
        if out.get("opened") or out.get("resolved"):
            print(f"[afm] cup tick → {out}", flush=True)
    except Exception as exc:
        print(f"[afm] cup tick failed: {exc!r}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    if args.once:
        tick_once()
        return 0
    every = max(5.0, float(os.environ.get("AFM_TICK_SEC", "30")))
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    print(f"[afm] ticker started, every {every:.0f}s", flush=True)
    while not _stop:
        tick_once()
        slept = 0.0
        while slept < every and not _stop:
            time.sleep(1.0)
            slept += 1.0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
