#!/usr/bin/env python3
"""Register the free Stockfish agent (Pike) and print how to sit a table.

  PYTHONPATH=. python3 scripts/bring_free_agent.py

Starts :18763 if needed, registers agent_pike_stockfish, prints the fund address.
Does not start a match until that wallet has Arc testnet USDC.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _env() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    envf = root / ".env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _up(port: int) -> bool:
    s = socket.socket()
    try:
        s.settimeout(0.3)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def main() -> int:
    _env()
    root = Path(__file__).resolve().parents[1]
    port = 18763
    if not _up(port):
        print("starting Pike webhook :18763")
        subprocess.Popen(
            [sys.executable, str(root / "builders" / "free_stockfish_agent.py")],
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(20):
            time.sleep(0.15)
            if _up(port):
                break
        else:
            print("Pike did not bind :18763")
            return 1

    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    rec = reg.register_from_manifest(
        {
            "agent_id": "agent_pike_stockfish",
            "name": "Pike",
            "creator_id": "creator_pike_lab",
            "game_ids": ["agentic.chess_standard"],
            "webhook_url": "http://127.0.0.1:18763/move",
            "economy": {
                "bankroll_usdc": "50",
                "max_stake_usdc": "10",
                "min_stake_usdc": "1",
                "reserve_bps": 2000,
                "preferred_time_controls": ["blitz_3|2", "blitz_5|0"],
            },
            "runtime": {
                "engine": "webhook",
                "webhook_url": "http://127.0.0.1:18763/move",
            },
            "mind": {"directive": "Play solid Stockfish chess.", "blurb": "Free Stockfish agent"},
        }
    )
    # persist runtime like the API does
    from gaming.src.stack.agentic.store import load_json, save_json

    data = load_json("agents.json", {"agents": {}})
    if rec["agent_id"] in data["agents"]:
        data["agents"][rec["agent_id"]]["runtime"] = rec.get("runtime") or {
            "engine": "webhook",
            "webhook_url": "http://127.0.0.1:18763/move",
        }
        data["agents"][rec["agent_id"]]["webhook_url"] = "http://127.0.0.1:18763/move"
        save_json("agents.json", data)
        rec = data["agents"][rec["agent_id"]]

    addr = rec.get("wallet_address") or ""
    print("registered Pike")
    print("  agent_id", rec["agent_id"])
    print("  webhook  http://127.0.0.1:18763/move")
    print("  wallet  ", addr)
    print("Fund that address with Arc testnet USDC, then:")
    print(
        "  House rematch Pike vs Nero "
        "(agent_pike_stockfish vs agent_nero_sicilian_french)"
    )
    try:
        req = urllib.request.Request("http://127.0.0.1:18763/health")
        with urllib.request.urlopen(req, timeout=2) as r:
            print("  health  ", r.read().decode()[:160])
    except Exception as e:
        print("  health fail", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
