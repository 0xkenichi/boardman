#!/usr/bin/env python3
"""
Rotate agent wallets off the old seed-derived keys onto random keystore keys.

Until this rotation, every agent key was keccak("boardman.agent.wallet.v1:" +
seed) with a public seed, so anyone could recompute it. Treat every legacy
address as compromised.

Default is a DRY RUN. It never touches a chain:
  1. stages a fresh random key per agent in the keystore (pending slot;
     re-running reuses it, so the plan is stable),
  2. prints  agent → old address → new address  (addresses only, never keys),
  3. prints the sweep plan.

--execute (a human runs this, after reviewing the dry run):
  for each agent, sweep the USDC balance old → new (leaving a small gas
  reserve), then promote the pending key to active, point agents.json at the
  new address, and seal any legacy plaintext secrets_<agent>.json.

Settle or cancel every open escrow match first: BoardmanEscrow pays the
address that locked, so a payout landing after rotation goes to the old
(compromised) address.

Usage:
  export PYTHONPATH=$PWD
  export BOARDMAN_KEYSTORE_SECRET=...        # >= 32 chars, from your secret store
  python3 scripts/rotate_agent_wallets.py                  # dry run
  python3 scripts/rotate_agent_wallets.py --agents agent_raja_kia_alekhine
  python3 scripts/rotate_agent_wallets.py --execute        # moves funds
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

# Old manifest seeds (public in git history). Needed only to sign the sweep
# out of the compromised legacy addresses. Never used to create a key.
LEGACY_MANIFEST_SEEDS = {
    "agent_boardman_house": "boardman.agent.house.v1",
    "agent_raja_kia_alekhine": "boardman.agent.raja.kia_alekhine.v3",
    "agent_nero_sicilian_french": "boardman.agent.nero.sicilian_french.v2",
    "agent_sheila_anaconda": "boardman.agent.sheila.anaconda.v1",
    "agent_aoashi_demo": "boardman.agent.afm.aoashi.v1",
    "agent_matchslice_demo": "boardman.agent.afm.matchslice.v1",
    "agent_bluelock_demo": "boardman.agent.afm.bluelock.v1",
}
_SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _bootstrap() -> None:
    root = Path(__file__).resolve().parents[1]
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


def _legacy_seed_key(seed: str) -> str:
    """The retired derivation — reproduced here only to sweep old wallets."""
    from eth_hash.auto import keccak

    digest = keccak(f"boardman.agent.wallet.v1:{seed}".encode("utf-8"))
    n = int.from_bytes(digest, "big")
    if n == 0 or n >= _SECP256K1_N:
        digest = keccak(digest + b"\x01")
    return "0x" + digest.hex()


def _legacy_candidates(agent_id: str) -> list[tuple[str, str]]:
    """(source label, key) pairs that the old code could have used."""
    from gaming.src.stack.agentic.store import load_json

    out: list[tuple[str, str]] = []
    try:
        plain = load_json(f"secrets_{agent_id}.json", {})
    except Exception:
        plain = {}
    pk = plain.get("private_key") if isinstance(plain, dict) else None
    if pk:
        out.append(("legacy-plaintext", pk if str(pk).startswith("0x") else "0x" + str(pk)))
    seeds = [
        LEGACY_MANIFEST_SEEDS.get(agent_id),
        f"boardman.agent.afm.{agent_id}",
        f"boardman.agent.{agent_id}",
        agent_id,
    ]
    for s in seeds:
        if s:
            out.append(("legacy-seed", _legacy_seed_key(s)))
    return out


def resolve_old_key(
    agent_id: str, old_address: str, *, want_key: bool = False
) -> tuple[str, Optional[str]]:
    """Find the key that controls ``old_address``. Returns (source, key|None).

    Keystore keys are only unsealed when ``want_key`` (i.e. during --execute).
    """
    from eth_account import Account
    from gaming.src.stack.agentic.keystore import get_keystore

    target = (old_address or "").lower()
    ks = get_keystore()
    if target and (ks.address(agent_id) or "").lower() == target:
        return "keystore", ks.private_key(agent_id) if want_key else None
    for label, pk in _legacy_candidates(agent_id):
        if Account.from_key(pk).address.lower() == target:
            return label, pk
    return "no-key", None


def build_plan(
    agent_ids: Optional[list[str]] = None, *, include_keystore: bool = False
) -> list[dict[str, Any]]:
    """Stage pending keys and describe the rotation. Touches no chain."""
    from gaming.src.stack.agentic.keystore import get_keystore
    from gaming.src.stack.agentic.store import load_json

    ks = get_keystore()
    agents = load_json("agents.json", {"agents": {}}).get("agents", {})
    wanted = set(agent_ids or agents.keys())
    plan = []
    for agent_id in sorted(wanted):
        rec = agents.get(agent_id)
        if not rec:
            plan.append({"agent_id": agent_id, "action": "skip", "reason": "not registered"})
            continue
        if rec.get("role") == "house":
            plan.append({
                "agent_id": agent_id, "name": rec.get("name"), "action": "skip",
                "reason": "house has no spend key (fee recipient only)",
            })
            continue
        old = str(rec.get("wallet_address") or "")
        source, _ = resolve_old_key(agent_id, old)
        if source == "keystore" and not include_keystore:
            plan.append({
                "agent_id": agent_id, "name": rec.get("name"), "action": "skip",
                "reason": "already on a random keystore key",
            })
            continue
        new = ks.stage(agent_id)
        plan.append({
            "agent_id": agent_id,
            "name": rec.get("name"),
            "action": "rotate",
            "old_address": old,
            "new_address": new,
            "old_key_source": source,
            "sweep": source != "no-key",
        })
    return plan


def print_plan(plan: list[dict[str, Any]], gas_reserve: Decimal) -> None:
    print("Agent wallet rotation plan (addresses only — no keys are printed)\n")
    for row in plan:
        if row["action"] != "rotate":
            print(f"  - {row['agent_id']}: skip ({row['reason']})")
            continue
        print(f"  * {row['agent_id']} ({row.get('name') or '-'})")
        print(f"      old {row['old_address']}  [{row['old_key_source']}]")
        print(f"      new {row['new_address']}  [keystore, pending]")
    print("\nSweep plan (runs only with --execute):")
    print("  0. Settle/cancel open escrow matches for these agents first.")
    print(f"  1. Per agent: transfer USDC balance old → new, leaving {gas_reserve} USDC for gas.")
    print("     Agents marked [no-key] have no recoverable old key; nothing to sweep.")
    print("  2. Promote the pending key to active (previous active entry is retired, not deleted).")
    print("  3. Point agents.json wallet_address at the new address.")
    print("  4. Seal any legacy plaintext secrets_<agent>.json.")


def _sweep(old_pk: str, new_address: str, gas_reserve: Decimal, chain_id: str) -> dict[str, Any]:
    from gaming.src.stack.agentic import onchain

    cfg = onchain._chain_config(chain_id)
    w3 = onchain._w3(cfg)
    usdc, _ = onchain._contracts(w3, cfg)
    acct = onchain._account(old_pk)
    bal = int(usdc.functions.balanceOf(acct.address).call())
    amount = bal - onchain.usdc_to_raw(gas_reserve)
    if amount <= 0:
        return {"swept_usdc": "0", "tx_hash": None}
    tx = usdc.functions.transfer(
        w3.to_checksum_address(new_address), amount
    ).build_transaction({"from": acct.address})
    h = onchain._send(w3, acct, tx, "rotate_sweep")
    return {
        "swept_usdc": str(Decimal(amount) / Decimal(10**onchain.USDC_DECIMALS)),
        "tx_hash": h,
        "explorer": onchain._explorer(cfg, h),
    }


def finalize(agent_id: str, old_address: str) -> str:
    """Promote pending → active, repoint the registry, seal legacy plaintext."""
    from gaming.src.stack.agentic.keystore import get_keystore
    from gaming.src.stack.agentic.store import load_json, save_json

    new = get_keystore().promote(agent_id)
    data = load_json("agents.json", {"agents": {}})
    rec = data.get("agents", {}).get(agent_id)
    if rec is not None:
        rec["previous_wallet_address"] = old_address
        rec["wallet_address"] = new
        rec["key_custody"] = "keystore"
        rec["wallet_rotated_at"] = datetime.now(timezone.utc).isoformat()
        save_json("agents.json", data)
    if load_json(f"secrets_{agent_id}.json", None) is not None:
        save_json(
            f"secrets_{agent_id}.json",
            {"private_key": None, "sealed": True, "migrated_to": "keystore"},
        )
    return new


def execute(plan: list[dict[str, Any]], gas_reserve: Decimal, chain_id: str) -> int:
    failures = 0
    for row in plan:
        if row["action"] != "rotate":
            continue
        agent_id = row["agent_id"]
        try:
            if row["sweep"]:
                _, old_pk = resolve_old_key(agent_id, row["old_address"], want_key=True)
                if not old_pk:
                    raise RuntimeError("old key no longer resolvable")
                res = _sweep(old_pk, row["new_address"], gas_reserve, chain_id)
                print(f"  {agent_id}: swept {res['swept_usdc']} USDC {res.get('explorer') or ''}")
            new = finalize(agent_id, row["old_address"])
            print(f"  {agent_id}: active wallet is now {new}")
        except Exception as exc:  # keep going; pending key stays staged
            failures += 1
            print(f"  {agent_id}: FAILED — {exc}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: Optional[list[str]] = None) -> int:
    _bootstrap()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", default="", help="comma-separated agent ids (default: all)")
    ap.add_argument("--execute", action="store_true", help="actually sweep funds and promote keys")
    ap.add_argument("--yes", action="store_true", help="skip the interactive confirmation for --execute")
    ap.add_argument("--include-keystore", action="store_true",
                    help="also rotate agents already on keystore keys")
    ap.add_argument("--chain", default="arc")
    ap.add_argument("--gas-reserve", default="0.05", help="USDC left behind for gas (Arc pays gas in USDC)")
    args = ap.parse_args(argv)

    from gaming.src.stack.agentic.keystore import KeystoreError

    agent_ids = [a.strip() for a in args.agents.split(",") if a.strip()] or None
    gas_reserve = Decimal(args.gas_reserve)
    try:
        plan = build_plan(agent_ids, include_keystore=args.include_keystore)
    except KeystoreError as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 2
    print_plan(plan, gas_reserve)

    if not args.execute:
        print("\nDry run only. Re-run with --execute to sweep funds and promote keys.")
        return 0
    if not args.yes:
        answer = input("\nType ROTATE to sweep funds on-chain and promote keys: ").strip()
        if answer != "ROTATE":
            print("aborted")
            return 1
    print("\nExecuting rotation")
    return execute(plan, gas_reserve, args.chain)


if __name__ == "__main__":
    raise SystemExit(main())
