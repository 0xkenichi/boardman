#!/usr/bin/env python3
"""
Fund Raja + Nero agent wallets with Arc testnet USDC for live dual-lock demos.

Requires a funder key that already holds Arc testnet USDC:
  export BOARDMAN_FUNDER_KEY=0x...   # or BOARDMAN_RESOLVER_KEY

Usage:
  export PYTHONPATH=$PWD
  export BOARDMAN_AGENTIC_ONCHAIN=1
  python3 scripts/fund_agent_wallets.py
  python3 scripts/fund_agent_wallets.py --amount 25
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
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


def main() -> int:
    _bootstrap()
    ap = argparse.ArgumentParser()
    ap.add_argument("--amount", type=float, default=20.0, help="USDC per agent")
    args = ap.parse_args()

    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.onchain import fund_agent_from_key, usdc_balance

    reg = get_registry()
    agents = reg.ensure_demo_agents()
    amount = Decimal(str(args.amount))

    print("Funding Boardman agents on Arc testnet")
    print(f"  amount each: {amount} USDC\n")

    for a in agents:
        addr = a["wallet_address"]
        before = usdc_balance(addr)
        print(f"◆ {a['name']}")
        print(f"  wallet : {addr}")
        print(f"  before : {before} USDC")
        if before >= amount:
            print("  skip   : already funded\n")
            continue
        need = amount - before
        try:
            res = fund_agent_from_key(addr, need)
            print(f"  tx     : {res['tx_hash']}")
            print(f"  link   : {res['explorer']}")
            print(f"  after  : {usdc_balance(addr)} USDC\n")
        except Exception as exc:
            print(f"  ERROR  : {exc}\n")
            return 1

    print("Done. Run demo with:")
    print("  export BOARDMAN_AGENTIC_ONCHAIN=1")
    print("  export BOARDMAN_RESOLVER_KEY=0x...")
    print("  python3 scripts/record_chess_demo.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
