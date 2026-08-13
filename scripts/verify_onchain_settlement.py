#!/usr/bin/env python3
"""
Verify on-chain settlement for Boardman agent matches.

Reads data/agentic/matches.json, queries the Arc escrow contract for each
match's on-chain status, and prints a diff:

  - matches locally marked `settled` but still LOCKED on-chain  → funds stuck
  - matches locally marked `onchain` but with no on-chain tx    → never locked
  - resolver key config problems (missing / invalid / wrong address)

Usage:
  PYTHONPATH=. python3 scripts/verify_onchain_settlement.py [--match MATCH_ID]

Exit code 0 = all on-chain matches settled correctly, 1 = problems found.
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
from gaming.src.stack.agentic.onchain import (  # noqa: E402
    _chain_config,
    _contracts,
    _w3,
    match_id_to_bytes32,
    load_resolver_key,
)

STATUS_NAMES = {0: "OPEN", 1: "LOCKED", 2: "DISPUTED", 3: "RESOLVED", 4: "CANCELLED"}
ZERO = "0x0000000000000000000000000000000000000000"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", help="Only check this match id")
    ap.add_argument("--chain", default="arc")
    args = ap.parse_args()

    cfg = _chain_config(args.chain)
    print(f"chain={args.chain} rpc={cfg['rpc_url']}")
    print(f"escrow={cfg['escrow']} usdc={cfg['usdc']}")

    # Resolver key config
    try:
        pk = load_resolver_key()
        from eth_account import Account

        acct = Account.from_key(pk)
        print(f"resolver key: configured, derives to {acct.address}")
    except RuntimeError as exc:
        print(f"resolver key: PROBLEM — {exc}")
        print("  → on-chain settlement will fail until this is fixed")

    problems = 0
    try:
        w3 = _w3(cfg)
        _, escrow = _contracts(w3, cfg)
        onchain_resolver = escrow.functions.resolver().call()
        print(f"contract resolver(): {onchain_resolver}")
        try:
            if onchain_resolver.lower() != acct.address.lower():
                print(
                    f"  ✗ MISMATCH: resolver key address {acct.address} != contract "
                    f"resolver {onchain_resolver} — resolveMatch will revert NotResolver"
                )
                problems += 1
            else:
                print("  ✓ resolver key matches contract resolver")
        except NameError:
            print("  (cannot compare — no valid resolver key)")
    except Exception as exc:
        print(f"RPC/contract read failed: {exc}")
        problems += 1
        return 1

    data = load_json("matches.json", {"matches": {}})
    matches = data.get("matches", {})
    if args.match:
        matches = {k: v for k, v in matches.items() if k == args.match}
        if not matches:
            print(f"match {args.match} not found")
            return 1

    print(f"\nchecking {len(matches)} matches")
    for mid, m in matches.items():
        mode = m.get("settlement_mode") or "demo_ledger"
        status = m.get("status")
        oc = m.get("onchain") or {}
        settle = m.get("onchain_settle") or {}
        m32 = match_id_to_bytes32(mid)
        try:
            r = escrow.functions.matches(m32).call()
            on_status = int(r[3])
            on_name = STATUS_NAMES.get(on_status, str(on_status))
            p1 = r[0] if str(r[0]).lower() != ZERO.lower() else "—"
            p2 = r[1] if str(r[1]).lower() != ZERO.lower() else "—"
            stake = int(r[2]) / 1e6 if int(r[2]) else 0.0
        except Exception as exc:
            print(f"{mid}: contract read failed: {exc}")
            problems += 1
            continue

        local = f"local={status}({mode})"
        chain = f"chain={on_name}"
        ok = True
        notes = []
        if mode == "onchain" and not oc.get("create_tx_hash"):
            ok = False
            notes.append("never locked on-chain (no create tx)")
        if status == "settled" and on_status not in (3, 4):  # RESOLVED / CANCELLED
            ok = False
            notes.append("FUNDS STUCK — settled locally but still on-chain " + on_name)
        if settle:
            notes.append(f"settle_tx={str(settle.get('tx_hash'))[:18]}…")
        err = m.get("onchain_settle_error")
        if err:
            notes.append(f"settle_error={str(err)[:80]}")
        flag = "✓" if ok else "✗"
        print(f"{flag} {mid} | {local} | {chain} | p1={str(p1)[:10]} p2={str(p2)[:10]} stake={stake}")
        for n in notes:
            print(f"    {n}")
        if not ok:
            problems += 1

    print("\n" + ("ALL GOOD — on-chain matches settled correctly" if problems == 0
                  else f"{problems} problem(s) found — see above"))
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
