#!/usr/bin/env python3
"""
Replay on-chain settlement for matches that settled locally but are still
LOCKED on the escrow contract (funds stuck). Refunds both players on draws
(cancelMatch), pays the winner otherwise (resolveMatch).

DRY-RUN by default — pass --apply to broadcast transactions.

Usage:
  PYTHONPATH=. python3 scripts/settle_stuck_matches.py            # dry run
  PYTHONPATH=. python3 scripts/settle_stuck_matches.py --apply    # broadcast
  PYTHONPATH=. python3 scripts/settle_stuck_matches.py --match agm_xxx --apply

Requires a valid BOARDMAN_RESOLVER_KEY (private key of the contract resolver).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Local .env load (safe, no prints of values)
_env_path = Path.cwd() / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _s = _line.strip()
        if _s and not _s.startswith("#") and "=" in _s:
            _k, _v = _s.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from gaming.src.stack.agentic.store import load_json  # noqa: E402
from gaming.src.stack.agentic.disbursement import (  # noqa: E402
    authorize_replay_settlement,
    winner_wallet_for_match,
)
from gaming.src.stack.agentic.onchain import (  # noqa: E402
    _chain_config,
    _contracts,
    _w3,
    match_id_to_bytes32,
    resolve_onchain,
)

STATUS_NAMES = {0: "OPEN", 1: "LOCKED", 2: "DISPUTED", 3: "RESOLVED", 4: "CANCELLED"}
ZERO = "0x0000000000000000000000000000000000000000"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually broadcast (default is dry run)")
    ap.add_argument("--match", help="Only settle this match id")
    ap.add_argument("--chain", default="arc")
    args = ap.parse_args()

    cfg = _chain_config(args.chain)
    try:
        w3 = _w3(cfg)
    except Exception as exc:
        print(f"RPC not reachable: {exc}")
        return 1
    _, escrow = _contracts(w3, cfg)

    data = load_json("matches.json", {"matches": {}})
    matches = data.get("matches", {})
    if args.match:
        matches = {k: v for k, v in matches.items() if k == args.match}
        if not matches:
            print(f"match {args.match} not found")
            return 1

    stuck = []
    for mid, m in matches.items():
        if m.get("status") != "settled":
            continue
        if not (m.get("settlement_mode") == "onchain" or m.get("onchain")):
            continue
        m32 = match_id_to_bytes32(mid)
        try:
            r = escrow.functions.matches(m32).call()
            on_status = int(r[3])
        except Exception as exc:
            print(f"{mid}: contract read failed: {exc}")
            continue
        if on_status in (3, 4):  # already RESOLVED / CANCELLED
            continue
        if on_status != 1:  # only replay LOCKED matches
            print(f"{mid}: on-chain {STATUS_NAMES.get(on_status, on_status)} — skip")
            continue
        p1 = r[0] if str(r[0]).lower() != ZERO.lower() else None
        p2 = r[1] if str(r[1]).lower() != ZERO.lower() else None
        stuck.append((mid, m, on_status, p1, p2))

    if not stuck:
        print("No stuck matches found — all settled matches are resolved on-chain.")
        return 0

    print(f"{len(stuck)} match(es) settled locally but still LOCKED on-chain:")
    for mid, m, _, p1, p2 in stuck:
        print(
            f"  {mid} result={m.get('result')} winner={m.get('winner_agent_id')} "
            f"p1={str(p1)[:10]} p2={str(p2)[:10]}"
        )

    if not args.apply:
        print("\nDRY RUN — pass --apply to broadcast settlement.")
        return 0

    errors = 0
    for mid, m, _, p1, p2 in stuck:
        try:
            auth = authorize_replay_settlement(m)
            draw = auth.action == "cancel"
            if draw:
                res = resolve_onchain(
                    mid, p1, chain_id=args.chain, draw=True, authorization=auth
                )
                print(f"✓ {mid}: cancelMatch (draw refund) tx={res.get('tx_hash')}")
            else:
                winner_addr = auth.winner_wallet or winner_wallet_for_match(m)
                if not winner_addr:
                    print(f"✗ {mid}: cannot determine winner address from match record")
                    errors += 1
                    continue
                # Never assume player1 == agent_a (white creates the match).
                res = resolve_onchain(
                    mid, winner_addr, chain_id=args.chain, authorization=auth
                )
                print(f"✓ {mid}: resolveMatch -> {winner_addr} tx={res.get('tx_hash')}")
        except Exception as exc:
            print(f"✗ {mid}: settlement failed: {exc}")
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
