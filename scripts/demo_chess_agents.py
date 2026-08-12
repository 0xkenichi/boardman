#!/usr/bin/env python3
"""
Boardman Agent Arena — Raja (KIA / Alekhine) vs Nero (Sicilian / French).

Each agent has:
  - identity contract address (deterministic CREATE2-style)
  - USDC wallet (deterministic EOA)
  - dual-lock stake → live chess → settle

Usage (from repo root):
  export PYTHONPATH=$PWD
  # optional monorepo shims:
  #   mkdir -p gaming && ln -sfn ../src gaming/src
  python scripts/demo_chess_agents.py
  python scripts/demo_chess_agents.py --white nero --stake 10 --delay 0.1
  python scripts/demo_chess_agents.py --seed 42 --quiet
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    # PYTHONPATH
    sys.path.insert(0, str(root))
    # gaming.src → src shim
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
    parser = argparse.ArgumentParser(description="Boardman chess agent demo")
    parser.add_argument("--white", choices=("raja", "nero"), default="raja")
    parser.add_argument("--stake", type=float, default=5.0)
    parser.add_argument("--delay", type=float, default=0.12, help="seconds between moves")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--quiet", action="store_true", help="less board printing")
    parser.add_argument("--json-out", type=str, default="", help="write full match JSON")
    args = parser.parse_args()

    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.chess.personas import get_persona
    from gaming.src.stack.agentic import ledger

    reg = get_registry()
    agents = reg.ensure_demo_agents()
    print("=" * 60)
    print("BOARDMAN AGENT ARENA — Chess")
    print("=" * 60)
    for a in agents:
        p = get_persona(a["agent_id"])
        mind = (p or {}).get("mind") or a.get("mind") or {}
        print(f"\n◆ {a['name']}  ({a['agent_id']})")
        print(f"  openings : {', '.join(a.get('openings') or p.get('openings') or [])}")
        print(f"  wallet   : {a['wallet_address']}")
        print(f"  contract : {a['identity_contract']}")
        print(f"  chain    : {a.get('chain_id', 'arc')}")
        print(f"  balance  : {ledger.balance(a['wallet_address'])} USDC (after faucet on match)")
        if mind.get("blurb"):
            print(f"  mind     : {mind['blurb'][:100]}…")

    print("\n" + "-" * 60)
    print(f"Match: stake ${args.stake} USDC · White = {args.white.title()} · live play")
    print("-" * 60 + "\n")

    def on_move(ev) -> None:
        if args.quiet:
            check = "+" if ev.is_check else ""
            cap = "x" if ev.is_capture else ""
            print(f"{ev.move_number:>3}. {ev.side[0].upper()} {ev.san}{check}{cap}")
            return
        tag = "♔" if ev.side == "white" else "♚"
        flags = []
        if ev.is_capture:
            flags.append("capture")
        if ev.is_check:
            flags.append("check")
        flag_s = f" ({', '.join(flags)})" if flags else ""
        print(f"\n{tag} Move {ev.move_number} · {ev.side.upper()} · {ev.agent_id}")
        print(f"   {ev.san}{flag_s}")
        print(ev.board_unicode)
        print(f"   FEN: {ev.fen}")

    svc = get_match_service()
    match = svc.demo_raja_vs_nero(
        stake_usdc=args.stake,
        white=args.white,
        move_delay_sec=args.delay,
        seed=args.seed,
        on_move=on_move,
    )

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"  match_id     : {match['match_id']}")
    print(f"  result       : {match.get('result')}")
    print(f"  termination  : {match.get('termination')}")
    print(f"  winner       : {match.get('winner_agent_id')}")
    print(f"  plies        : {(match.get('play') or {}).get('plies')}")
    esc = match.get("escrow") or {}
    print(f"  escrow       : {esc.get('status')}  payout={esc.get('payout')}  fee={esc.get('fee')}")
    print(f"  white wallet : {match.get('agent_a_wallet') if match.get('white_agent_id')==match.get('agent_a_id') else match.get('agent_b_wallet')}")
    for a in agents:
        print(f"  bal {a['name']:5} : {ledger.balance(a['wallet_address'])} USDC")
    print("\nPGN:")
    print(match.get("pgn") or "")

    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(match, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
