#!/usr/bin/env python3
"""Set up Circle's LIVE (mainnet) entity for the humans realm, on the server.

NOT run by CI or agents. The founder runs it once on the production VM after
creating the mainnet API key (stored blind as CIRCLE_API_KEY_LIVE). Default is
a DRY RUN: it checks preconditions and prints the plan, with no network call
and no file change. ``--apply`` does the work.

Steps (each skipped when its result already exists, so a rerun is safe):

1. Entity secret: 32 random bytes generated HERE, written straight into the
   env file as CIRCLE_ENTITY_SECRET_LIVE (0600). Never printed, never logged.
2. Register it with Circle: fetch the entity public key
   (GET /v1/w3s/config/entity/publicKey), RSA-OAEP-SHA256-encrypt the secret,
   POST the ciphertext to /v1/w3s/config/entity/entitySecret and save the
   returned recovery file to --recovery-dir (0600). That endpoint is what
   Circle's SDK ``registerEntitySecretCiphertext`` calls but is NOT in Circle's
   public API reference (checked 2026-10-19). If it is refused, use
   ``--console``: the ciphertext is written to a 0600 file for pasting into
   console.circle.com > Wallets > Dev Controlled > Configurator > Entity
   Secret, and the Console gives you the recovery file instead.
3. Wallet set: POST /v1/w3s/developer/walletSets (name boardman-humans-mainnet)
   -> CIRCLE_WALLET_SET_ID_LIVE.
4. Relayer wallets (pay CCTP mint gas): one on ARC (Arc mainnet) and one on
   BASE (Base mainnet) -> PAYCREST_ARC_RELAYER_WALLET_ID /
   PAYCREST_BASE_RELAYER_WALLET_ID.
5. Prints ONLY wallet addresses, ids and funding instructions.

Idempotency keys are derived (uuid5) from the step name, so Circle de-dupes a
retried request. Values already present in the env file are never replaced.

Run (VM, from ~/boardman; the image has requests + pycryptodome):

  mkdir -p ~/boardman-secrets && chmod 700 ~/boardman-secrets
  docker compose run --rm --no-deps \
    -v "$PWD/.env:/run/boardman.env" -v "$HOME/boardman-secrets:/out" \
    boardman-api python scripts/circle_mainnet_setup.py \
      --env-file /run/boardman.env --recovery-dir /out            # dry run
  ... same command ... --apply

Then download the recovery file and delete it from the VM:
  scp ubuntu@<vm>:boardman-secrets/circle_entity_recovery_*.dat .   (store offline, 2 copies)
  ssh ubuntu@<vm> 'shred -u ~/boardman-secrets/circle_entity_recovery_*.dat'
"""
from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

API = "https://api.circle.com/v1"
LIVE_PREFIX = "LIVE_API_KEY:"
WALLET_SET_NAME = "boardman-humans-mainnet"
KEY_ENV = "CIRCLE_API_KEY_LIVE"
SECRET_ENV = "CIRCLE_ENTITY_SECRET_LIVE"
SET_ENV = "CIRCLE_WALLET_SET_ID_LIVE"
RELAYERS = (
    # (env var, Circle blockchain, account type, what to fund it with)
    ("PAYCREST_ARC_RELAYER_WALLET_ID", "ARC", "EOA",
     "~20 USDC on Arc mainnet (Arc gas is paid in USDC; it pays CCTP mint gas)"),
    ("PAYCREST_BASE_RELAYER_WALLET_ID", "BASE", "SCA",
     "nothing if the Gas Station policy for Base mainnet covers it, else ~0.001 ETH on Base"),
)


class SetupError(RuntimeError):
    pass


# ── env file (values never printed) ──────────────────────────────────────────


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def append_env(path: Path, key: str, value: str, *, note: str) -> None:
    """Append KEY=value in place (works on a bind-mounted file); refuse to
    replace an existing key. Keeps the file 0600."""
    if key in read_env(path):
        raise SetupError(f"{key} already in {path}; refusing to replace it")
    if "\n" in value or not value:
        raise SetupError(f"bad value for {key}")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"\n# {note} ({datetime.now(timezone.utc):%Y-%m-%d})\n{key}={value}\n")
    os.chmod(path, 0o600)


def idem(step: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"boardman:circle-mainnet-setup:{step}"))


# ── Circle calls ─────────────────────────────────────────────────────────────


class Circle:
    def __init__(self, api_key: str, entity_secret_hex: Optional[str]) -> None:
        import requests

        self._rq = requests
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.secret_hex = entity_secret_hex

    def _call(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        r = self._rq.request(method, f"{API}{path}", headers=self.headers, json=body, timeout=30)
        if r.status_code not in (200, 201):
            # Circle error bodies hold no secrets; never echo our request.
            raise SetupError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json().get("data") or {}

    def ciphertext(self) -> str:
        """A fresh single-use entitySecretCiphertext (RSA-OAEP SHA-256)."""
        from Crypto.Cipher import PKCS1_OAEP
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA

        if not self.secret_hex:
            raise SetupError("no entity secret loaded")
        pem = self._call("GET", "/w3s/config/entity/publicKey")["publicKey"]
        cipher = PKCS1_OAEP.new(RSA.importKey(pem), hashAlgo=SHA256)
        return base64.b64encode(cipher.encrypt(bytes.fromhex(self.secret_hex))).decode()

    def register(self) -> dict:
        return self._call("POST", "/w3s/config/entity/entitySecret", {"entitySecretCiphertext": self.ciphertext()})

    def wallet_set(self) -> dict:
        return self._call("POST", "/w3s/developer/walletSets", {
            "idempotencyKey": idem("wallet-set"),
            "entitySecretCiphertext": self.ciphertext(),
            "name": WALLET_SET_NAME,
        })["walletSet"]

    def wallet(self, wallet_set_id: str, blockchain: str, account_type: str, step: str) -> dict:
        data = self._call("POST", "/w3s/developer/wallets", {
            "idempotencyKey": idem(step),
            "entitySecretCiphertext": self.ciphertext(),
            "walletSetId": wallet_set_id,
            "blockchains": [blockchain],
            "accountType": account_type,
            "count": 1,
            "metadata": [{"name": f"boardman-{step}"}],
        })
        return (data.get("wallets") or [{}])[0]

    def get_wallet(self, wallet_id: str) -> dict:
        return self._call("GET", f"/w3s/wallets/{wallet_id}").get("wallet") or {}


# ── plan / apply ─────────────────────────────────────────────────────────────


def preflight(env: dict[str, str], env_file: Path, recovery_dir: Path) -> list[str]:
    problems = []
    key = env.get(KEY_ENV) or os.getenv(KEY_ENV) or ""
    if not key:
        problems.append(f"{KEY_ENV} is not set (store it blind first)")
    elif not key.startswith(LIVE_PREFIX):
        problems.append(f"{KEY_ENV} is not a LIVE key (must start with {LIVE_PREFIX})")
    if env.get("CIRCLE_API_KEY", "").startswith(LIVE_PREFIX):
        problems.append("CIRCLE_API_KEY (the testnet realm) holds a LIVE key: fix that first")
    if not os.access(env_file, os.W_OK):
        problems.append(f"{env_file} is not writable")
    if not recovery_dir.is_dir() or not os.access(recovery_dir, os.W_OK):
        problems.append(f"{recovery_dir} is not a writable directory")
    return problems


def plan(env: dict[str, str]) -> list[str]:
    steps = []
    steps.append("keep existing entity secret" if env.get(SECRET_ENV)
                 else f"generate entity secret -> {SECRET_ENV} (never shown)")
    steps.append("register entity secret ciphertext with Circle, save recovery file"
                 if not env.get(SECRET_ENV) else "skip registration (secret already set; assumed registered)")
    steps.append("keep wallet set" if env.get(SET_ENV) else f"create wallet set '{WALLET_SET_NAME}' -> {SET_ENV}")
    for var, chain, acct, _fund in RELAYERS:
        steps.append(f"keep {var}" if env.get(var) else f"create {acct} relayer wallet on {chain} -> {var}")
    return steps


def apply(env_file: Path, recovery_dir: Path, *, console: bool) -> int:
    env = read_env(env_file)
    key = env.get(KEY_ENV) or os.getenv(KEY_ENV) or ""
    fresh_secret = not env.get(SECRET_ENV)
    if fresh_secret:
        append_env(env_file, SECRET_ENV, secrets.token_hex(32), note="Circle LIVE entity secret (generated in place)")
        env = read_env(env_file)
    circle = Circle(key, env[SECRET_ENV])

    if fresh_secret:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if console:
            out = recovery_dir / f"circle_entity_ciphertext_{stamp}.txt"
            out.write_text(circle.ciphertext() + "\n", encoding="utf-8")
            os.chmod(out, 0o600)
            print(f"Ciphertext written to {out} (0600). Paste it in the Circle Console > Entity Secret,")
            print("download the recovery file there, then rerun this script with --apply (no --console).")
            return 0
        data = circle.register()
        rec = data.get("recoveryFile") or ""
        if rec:
            out = recovery_dir / f"circle_entity_recovery_{stamp}.dat"
            out.write_text(rec, encoding="utf-8")
            os.chmod(out, 0o600)
            print(f"Entity secret registered. Recovery file: {out} (0600) — download it, store it offline, shred it here.")
        else:
            print("Entity secret registered; Circle returned no recovery file (check the Console).")

    if not env.get(SET_ENV):
        ws = circle.wallet_set()
        append_env(env_file, SET_ENV, str(ws["id"]), note="Circle LIVE wallet set (humans realm)")
        env = read_env(env_file)
        print(f"Wallet set: {ws['id']} ({WALLET_SET_NAME})")

    print("\nRelayer wallets (fund them before switching real money on):")
    for var, chain, acct, fund in RELAYERS:
        if env.get(var):
            w = circle.get_wallet(env[var])
            print(f"  {var}={env[var]}  {chain}  {w.get('address', '?')}  (existing)  fund: {fund}")
            continue
        w = circle.wallet(env[SET_ENV], chain, acct, f"relayer-{chain.lower()}")
        append_env(env_file, var, str(w["id"]), note=f"Circle LIVE {chain} relayer wallet")
        print(f"  {var}={w['id']}  {chain}  {w.get('address')}  ({acct})  fund: {fund}")
    print("\nNext: restart the API (docker compose up -d --force-recreate --no-deps boardman-api),")
    print("then continue docs/MAINNET_HUMANS_CUTOVER.md (USDC token ids, Gas Station policy).")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--env-file", default=".env", type=Path)
    ap.add_argument("--recovery-dir", default=str(Path.home() / "boardman-secrets"), type=Path)
    ap.add_argument("--apply", action="store_true", help="do it (default: dry run, no network, no writes)")
    ap.add_argument("--console", action="store_true",
                    help="register through the Circle Console: write the ciphertext to a 0600 file instead")
    args = ap.parse_args(argv)

    env = read_env(args.env_file)
    problems = preflight(env, args.env_file, args.recovery_dir)
    print("Circle LIVE setup for the humans realm" + ("" if args.apply else "  [DRY RUN: nothing will change]"))
    for i, step in enumerate(plan(env), 1):
        print(f"  {i}. {step}")
    if problems:
        print("\nCannot continue:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2
    if not args.apply:
        print("\nPreconditions OK. Rerun with --apply to do it.")
        return 0
    try:
        return apply(args.env_file, args.recovery_dir, console=args.console)
    except SetupError as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        print("Everything done so far is saved; rerunning continues from here.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
