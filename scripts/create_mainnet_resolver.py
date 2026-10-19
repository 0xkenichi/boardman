#!/usr/bin/env python3
"""Create the real-money escrow resolver key IN the server keystore.

NOT run by CI or agents. The founder runs it once on the production VM,
before deploying BoardmanEscrow v2 to Arc mainnet. The key is 32 random bytes
generated here, sealed with BOARDMAN_KEYSTORE_SECRET (AES-256-GCM, see
src/stack/agentic/keystore.py) into the data volume. Only the ADDRESS is
printed: pass it to the deploy as V2_RESOLVER. Then set, in ~/boardman/.env:

    BOARDMAN_RESOLVER_KEY_MAINNET=resolver_arc_mainnet

That value is the keystore entry NAME, never a key. The backend refuses a
plaintext private key there and refuses to reuse the testnet resolver.

    docker compose run --rm --no-deps boardman-api \
      python scripts/create_mainnet_resolver.py            # dry run
    ... --apply

Rotation: ``--rotate`` stages a new key (pending slot) and prints its address;
the Safe calls setResolver(<new address>) on the escrow, then
``--promote`` makes it the active key. Never delete the old entry while a
match it permitted is still open.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# `gaming.*` / `backend.*` import aliases for a plain checkout (no files written).
import types  # noqa: E402

for _name, _target in (("gaming", ROOT), ("backend", ROOT / "src" / "backend")):
    if _name not in sys.modules and not (ROOT / _name).exists():
        _m = types.ModuleType(_name)
        _m.__path__ = [str(_target)]  # type: ignore[attr-defined]
        sys.modules[_name] = _m

DEFAULT_NAME = "resolver_arc_mainnet"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create the mainnet resolver key in the keystore")
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--apply", action="store_true")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--rotate", action="store_true", help="stage a new key in the pending slot")
    g.add_argument("--promote", action="store_true", help="make the staged key active")
    args = ap.parse_args(argv)

    from gaming.src.stack.agentic.keystore import KeystoreError, get_keystore, keystore_unlocked

    if not keystore_unlocked():
        print("BOARDMAN_KEYSTORE_SECRET is missing or too short; nothing done.", file=sys.stderr)
        return 2
    ks = get_keystore()
    active = ks.address(args.name)
    print(f"keystore entry: {args.name}")
    print(f"active address: {active or '(none)'}")
    if not args.apply:
        action = "promote pending" if args.promote else "stage a rotation" if args.rotate else (
            "nothing (already exists)" if active else "create")
        print(f"DRY RUN: would {action}. Rerun with --apply.")
        return 0
    try:
        if args.promote:
            addr = ks.promote(args.name)
            print(f"promoted; active resolver is now {addr}")
        elif args.rotate:
            addr = ks.stage(args.name)
            print(f"staged {addr}. The Safe must call setResolver({addr}) on the escrow, then rerun --promote.")
        elif active:
            print("already exists; not replaced.")
        else:
            addr = ks.create(args.name)
            print(f"created. Resolver address: {addr}")
            print(f"Use it as V2_RESOLVER for the deploy, and set BOARDMAN_RESOLVER_KEY_MAINNET={args.name}")
            print("Fund it with ~5 USDC on Arc mainnet (it pays gas for resolve/cancel/dispute).")
    except KeystoreError as exc:
        print(f"keystore refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
