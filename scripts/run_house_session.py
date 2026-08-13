#!/usr/bin/env python3
"""Raja vs Nero rematch loop — House clerks each game (lock → play → settle).

Does not use the browser arena. Arena Auto play is a client show and does
not touch BoardmanEscrow. This script is the real money path.

  PYTHONPATH=. python3 scripts/run_house_session.py --games 3
  PYTHONPATH=. python3 scripts/run_house_session.py --games 0   # until Ctrl-C
  PYTHONPATH=. python3 scripts/run_house_session.py --stake 1 --delay 0.05
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    envf = root / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    gaming = root / "gaming"
    gaming.mkdir(exist_ok=True)
    src_link = gaming / "src"
    if not src_link.exists():
        try:
            src_link.symlink_to(Path("..") / "src")
        except OSError:
            pass
    init = gaming / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")


def _ensure_builder_webhooks() -> None:
    """Start Raja and Nero as two separate webhook processes (two builders)."""
    import socket
    import subprocess
    import time

    specs = [
        ("Raja", 18761, "gaming.src.stack.agentic.agents.raja.serve"),
        ("Nero", 18762, "gaming.src.stack.agentic.agents.nero.serve"),
    ]
    for name, port, mod in specs:
        s = socket.socket()
        try:
            s.settimeout(0.3)
            s.connect(("127.0.0.1", port))
            s.close()
            print(f"  {name} webhook already up on :{port}")
            continue
        except OSError:
            pass
        print(f"  starting {name} builder webhook :{port}")
        subprocess.Popen(
            [sys.executable, "-m", mod],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH") or str(Path(__file__).resolve().parents[1])},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            time.sleep(0.15)
            try:
                s = socket.socket()
                s.settimeout(0.3)
                s.connect(("127.0.0.1", port))
                s.close()
                break
            except OSError:
                continue
        else:
            print(f"  WARN {name} webhook did not bind — House will use in-process silo")


def main() -> int:
    _bootstrap()
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=3, help="0 = run until Ctrl-C")
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--delay", type=float, default=0.05, help="seconds between moves")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between games")
    ap.add_argument("--game-id", default="agentic.chess_standard")
    args = ap.parse_args()

    os.environ.setdefault("BOARDMAN_USE_STOCKFISH", "1")
    os.environ.setdefault("BOARDMAN_MAX_PLIES", "80")

    _ensure_builder_webhooks()

    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.onchain import onchain_enabled, usdc_balance

    reg = get_registry()
    agents = {a["name"].lower(): a for a in reg.ensure_demo_agents()}
    raja = agents["raja"]
    nero = agents["nero"]
    house = get_house()

    print("Boardman House session")
    print(f"  onchain = {onchain_enabled()}")
    print(f"  stake   = {args.stake} USDC  game={args.game_id}")
    print(f"  raja    = {raja['wallet_address']}  {usdc_balance(raja['wallet_address'])} USDC")
    print(f"  nero    = {nero['wallet_address']}  {usdc_balance(nero['wallet_address'])} USDC")

    n = 0
    try:
        while args.games <= 0 or n < args.games:
            n += 1
            white = raja if n % 2 else nero
            print(f"\n── game {n}  white={white['name']} ──")
            t0 = time.time()
            out = house.rematch(
                agent_a_id=raja["agent_id"],
                agent_b_id=nero["agent_id"],
                stake_usdc=args.stake,
                game_id=args.game_id,
                white_agent_id=white["agent_id"],
                move_delay_sec=args.delay,
            )
            m = out["match"]
            dt = time.time() - t0
            print(
                f"  {m.get('match_id')}  {m.get('status')}  result={m.get('result')}  "
                f"winner={m.get('winner_agent_id')}  mode={m.get('settlement_mode')}  "
                f"{dt:.1f}s  stale_cleared={out.get('released_stale')}"
            )
            if m.get("onchain_settle"):
                print(f"  settle_tx={m['onchain_settle'].get('tx_hash')}")
            if m.get("status") != "settled":
                print("  STOP — match did not settle; pair is reserved until this is resolved")
                return 1
            if args.pause > 0 and (args.games <= 0 or n < args.games):
                time.sleep(args.pause)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
