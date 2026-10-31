#!/usr/bin/env python3
"""
Run one real Boardman agent match on Avalanche Fuji and record every tx.

Lock -> play -> settle through Boardman's own code, not a side script:
  1. the ops faucet (onchain.fund_agent_from_key) sends test USDC to the two
     demo agents, Raja and Nero, whose spend keys live in the sealed keystore;
  2. MatchService.demo_raja_vs_nero opens the match on the arena chain
     (BOARDMAN_ARENA_CHAIN=avalanche); lock_both approves USDC and calls
     BoardmanEscrow v2 createMatch (with the resolver's EIP-712 permit) and
     joinMatch from the agents' own wallets;
  3. the Stack chess engine plays the game move by move;
  4. settle authorizes the payout and the resolver calls resolveMatch, which
     pays the winner the pot minus the on-chain platform fee.

TESTNET ONLY. Wallets come from .fuji/wallets.json (git-ignored), made by
scripts/avalanche/new_testnet_wallets.mjs. Keys are never printed. Arena data
and the agent keystore go to .fuji/arena/, never the repo's data/.

  .venv/bin/python scripts/avalanche/fuji_proof.py            # Fuji
  .venv/bin/python scripts/avalanche/fuji_proof.py --rpc http://127.0.0.1:8545   # local Fuji fork

Writes docs/avalanche/fuji_proof_run.json and docs/avalanche/FUJI_PROOF.md
(public addresses and tx hashes only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FUJI_CHAIN_ID = 43113
FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
SNOWTRACE = "https://testnet.snowtrace.io"
GAS_TOPUP_WEI = 5 * 10**15  # 0.005 AVAX; a Fuji tx costs well under 1e-9 AVAX at today's base fee

OWNABLE_ABI = [
    {"name": "pendingOwner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"name": "owner", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"name": "acceptOwnership", "type": "function", "stateMutability": "nonpayable", "inputs": [], "outputs": []},
]


def _bootstrap_imports() -> None:
    """`gaming.*` must resolve to this checkout (same alias the tests use)."""
    import types

    sys.path.insert(0, str(ROOT))
    for name, target in (("gaming", ROOT), ("backend", ROOT / "src" / "backend")):
        if (ROOT / name).exists() or name in sys.modules:
            continue
        mod = types.ModuleType(name)
        mod.__path__ = [str(target)]  # type: ignore[attr-defined]
        sys.modules[name] = mod


def _set_env(wallets: dict, deployment: dict, data_dir: Path, rpc: str) -> None:
    """Point the Stack at Fuji and at this run's sandbox. Set before any import."""
    w = wallets["wallets"]
    c = deployment["contracts"]
    os.environ.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "BOARDMAN_AGENTIC_DATA": str(data_dir),
        "BOARDMAN_KEYSTORE_DIR": str(data_dir / "keystore"),
        "BOARDMAN_KEYSTORE_SECRET": wallets["keystore_secret"],
        "BOARDMAN_DATABASE_URL": f"sqlite:///{data_dir / 'boardman.sqlite3'}",
        # Avalanche build: Fuji is the only live chain and the arena chain.
        "CLAW_ENABLED_CHAINS": "avalanche",
        "CLAW_DEFAULT_CHAIN": "avalanche",
        "BOARDMAN_ARENA_CHAIN": "avalanche",
        "AVALANCHE_FUJI_RPC_URL": rpc,
        "CLAW_ESCROW_ADDRESS_AVALANCHE": c["BoardmanEscrow"],
        "SPECTATOR_ESCROW_ADDRESS_AVALANCHE": c.get("SpectatorPool", ""),
        "BOARDMAN_HOUSE_WALLET": deployment["config"]["feeRecipient"],
        # Real locks, no silent fallback to the book-entry ledger.
        "BOARDMAN_AGENTIC_ONCHAIN": "1",
        "BOARDMAN_ALLOW_LEDGER_FALLBACK": "0",
        "BOARDMAN_RESOLVER_KEY": w["resolver"]["private_key"],
        "BOARDMAN_FUNDER_KEY": w["funder_deployer"]["private_key"],
        "BOARDMAN_AGENT_THINK_MS": "50",
        "BOARDMAN_SF_THINK_MS": "50",
    })
    # Arc-only overrides from the caller's shell must not leak into this run.
    for name in ("ARC_RPC_URL", "ARC_USDC_ADDRESS", "BOARDMAN_ESCROW_ADDRESS_ARC", "CLAW_ESCROW_ADDRESS_ARC",
                 "SPECTATOR_ESCROW_ADDRESS", "DATABASE_URL", "SPECTATOR_ONCHAIN"):
        os.environ.pop(name, None)


def _tx_link(h: str) -> str:
    h = h if h.startswith("0x") else "0x" + h
    return f"{SNOWTRACE}/tx/{h}"


def _send_native(w3, pk: str, to: str, value: int) -> str:
    from eth_account import Account

    acct = Account.from_key(pk)
    tx = {
        "to": w3.to_checksum_address(to),
        "value": value,
        "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": int(w3.eth.chain_id),
        "gas": 21000,
        "maxFeePerGas": max(int(w3.eth.gas_price) * 4, 10**9),
        "maxPriorityFeePerGas": int(w3.eth.max_priority_fee or 1),
    }
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(h, timeout=120)
    return w3.to_hex(h)


def _accept_ownership(w3, pk: str, address: str) -> str | None:
    from eth_account import Account

    acct = Account.from_key(pk)
    c = w3.eth.contract(address=w3.to_checksum_address(address), abi=OWNABLE_ABI)
    if c.functions.owner().call().lower() == acct.address.lower():
        return None
    if c.functions.pendingOwner().call().lower() != acct.address.lower():
        raise SystemExit(f"{address}: pendingOwner is not the owner wallet; stop and check the deployment")
    tx = c.functions.acceptOwnership().build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": int(w3.eth.chain_id),
    })
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    if r.status != 1:
        raise SystemExit(f"acceptOwnership reverted on {address}")
    return w3.to_hex(h)


def _addr_link(a: str) -> str:
    return f"[`{a}`]({SNOWTRACE}/address/{a})"


def write_markdown(proof: dict, path: Path) -> None:
    m = proof["match"]
    c = proof["contracts"]
    gas = proof.get("gas_spent_avax")
    lines = [
        "# Boardman on Avalanche Fuji: live proof",
        "",
        f"Recorded {proof['recorded_at']} on {proof['network']} (chain {proof['chain_id']}) by",
        "[`scripts/avalanche/fuji_proof.py`](../../scripts/avalanche/fuji_proof.py), which drives",
        "Boardman's own match service, sealed agent keystore, ops faucet and resolver.",
        "Every stake is Circle test USDC with no cash value.",
        "",
        "## Contracts",
        "",
        "| Contract | Address |",
        "|----------|---------|",
        *(f"| {name} | {_addr_link(addr)} |" for name, addr in c.items()),
        f"| USDC (Circle, Fuji) | {_addr_link(proof['usdc'])} |",
        "",
        "## Roles (testnet-only keys, all different)",
        "",
        "| Role | Address |",
        "|------|---------|",
        *(f"| {role} | {_addr_link(addr)} |" for role, addr in proof["roles"].items()),
        *(f"| agent {name} | {_addr_link(addr)} |" for name, addr in proof["agents"].items()),
        "",
        "## The match",
        "",
        f"- Match `{m['match_id']}` (escrow id `{m['match_id_bytes32']}`), {m['game']}",
        f"- Stake: {m['stake_usdc_each']} USDC each; white: `{m['white']}`",
        f"- Result: **{m['result']}** by {m['termination']} after {m['plies']} plies; winner `{m['winner']}`",
        f"- Boardman status `{m['status']}`, settlement `{m['settlement_mode']}`; escrow status on-chain: **{m['onchain_status_after']}**",
        *([f"- Gas for every transaction below: {gas} AVAX in total"] if gas else []),
        "",
        "| Agent | USDC before | USDC after |",
        "|-------|------------:|-----------:|",
        *(f"| {name} | {proof['usdc_balances']['before'][name]} | {after} |"
          for name, after in proof["usdc_balances"]["after"].items()),
        "",
        "## Transactions, in order",
        "",
        "| # | Step | Snowtrace |",
        "|--:|------|-----------|",
        *(f"| {i} | {r['step']} | [{r['tx'][:10]}…]({r['link']}) |" for i, r in enumerate(proof["steps"], 1)),
        "",
    ]
    if proof.get("deploy_txs"):
        lines += ["## Deployment", "", "| Step | Snowtrace |", "|------|-----------|",
                  *(f"| {k} | [{v[:10]}…]({_tx_link(v)}) |" for k, v in proof["deploy_txs"].items()), ""]
    if m.get("pgn"):
        lines += ["## Game record (PGN)", "", "```", m["pgn"].strip(), "```", ""]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--wallets", default=str(ROOT / ".fuji" / "wallets.json"))
    ap.add_argument("--deployment", default=str(ROOT / "contracts" / "deployments" / "boardman_v2_avalancheFuji.json"))
    ap.add_argument("--data", default=str(ROOT / ".fuji" / "arena"))
    ap.add_argument("--rpc", default=os.getenv("AVALANCHE_FUJI_RPC_URL") or FUJI_RPC)
    ap.add_argument("--stake", type=float, default=2.0, help="USDC per agent (contract minimum is 2)")
    ap.add_argument("--bankroll", type=float, default=3.5,
                    help="USDC each agent holds before the match; the budget keeps a 20%% reserve "
                         "plus spectator seeds, so a $2 stake needs about $3")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "docs" / "avalanche" / "fuji_proof_run.json"))
    ap.add_argument("--markdown", default=str(ROOT / "docs" / "avalanche" / "FUJI_PROOF.md"))
    args = ap.parse_args()

    wallets = json.loads(Path(args.wallets).read_text())
    deployment = json.loads(Path(args.deployment).read_text())
    if int(deployment.get("chainId") or 0) != FUJI_CHAIN_ID:
        raise SystemExit("deployment file is not for Fuji (43113)")
    data_dir = Path(args.data)
    data_dir.mkdir(parents=True, exist_ok=True)
    _set_env(wallets, deployment, data_dir, args.rpc)
    _bootstrap_imports()

    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 60}))
    if int(w3.eth.chain_id) != FUJI_CHAIN_ID:
        raise SystemExit(f"RPC {args.rpc} is chain {w3.eth.chain_id}, not Fuji")

    from gaming.src.backend.services.chains import reload_chains_config

    reload_chains_config()
    from gaming.src.stack.agentic import onchain
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    cfg = onchain._chain_config()
    assert cfg["chain_id"] == "avalanche" and cfg["evm_chain_id"] == FUJI_CHAIN_ID, cfg
    w = wallets["wallets"]
    funder_pk = w["funder_deployer"]["private_key"]
    proof: dict = {
        "network": "Avalanche Fuji C-Chain",
        "chain_id": FUJI_CHAIN_ID,
        "explorer": SNOWTRACE,
        "contracts": deployment["contracts"],
        "usdc": cfg["usdc"],
        "roles": {k: v["address"] for k, v in w.items()},
        "steps": [],
    }

    def step(label: str, tx_hash: str | None, **extra) -> None:
        if not tx_hash:
            return
        row = {"step": label, "tx": tx_hash, "link": _tx_link(tx_hash), **extra}
        proof["steps"].append(row)
        print(f"  {label:<34} {row['link']}")

    print(f"Fuji escrow {cfg['escrow']} · USDC {cfg['usdc']} · RPC {args.rpc}")

    # 1. Owner accepts ownership (Ownable2Step), paid with a little faucet AVAX.
    owner = w["owner"]["address"]
    if w3.eth.get_balance(owner) < GAS_TOPUP_WEI // 5:
        step("gas top-up: owner", _send_native(w3, funder_pk, owner, GAS_TOPUP_WEI))
    for name, addr in deployment["contracts"].items():
        step(f"acceptOwnership: {name}", _accept_ownership(w3, w["owner"]["private_key"], addr))

    # 2. Agents: Raja + Nero, keys sealed in this run's keystore.
    agents = {a["name"].lower(): a for a in get_registry().ensure_demo_agents()}
    raja, nero = agents["raja"], agents["nero"]
    proof["agents"] = {a["name"]: a["wallet_address"] for a in (raja, nero)}

    # 3. Gas for the signers, then the ops faucet sends each agent its stake.
    resolver = w["resolver"]["address"]
    for label, addr in (("resolver", resolver), ("Raja", raja["wallet_address"]), ("Nero", nero["wallet_address"])):
        if w3.eth.get_balance(addr) < GAS_TOPUP_WEI // 5:
            step(f"gas top-up: {label}", _send_native(w3, funder_pk, addr, GAS_TOPUP_WEI))
    stake = Decimal(str(args.stake))
    bankroll = max(Decimal(str(args.bankroll)), stake)
    for a in (raja, nero):
        have = onchain.usdc_balance(a["wallet_address"])
        if have < bankroll:
            r = onchain.fund_agent_from_key(a["wallet_address"], bankroll - have, funder_key=funder_pk)
            step(f"faucet USDC -> {a['name']}", r["tx_hash"], amount_usdc=str(bankroll - have))
            time.sleep(2)
    before = {a["name"]: str(onchain.usdc_balance(a["wallet_address"])) for a in (raja, nero)}

    # 4. Lock -> play -> settle with the real match service.
    print("Playing Raja vs Nero (chess) on Fuji escrow...")
    plies = []

    def on_move(ev) -> None:
        plies.append(ev.san)

    m = get_match_service().demo_raja_vs_nero(stake_usdc=float(stake), move_delay_sec=0, seed=args.seed, on_move=on_move)
    on = m.get("onchain") or {}
    for t in on.get("txs") or []:
        step(f"lock: {t.get('label') or t.get('step') or 'tx'}", t.get("tx_hash") or t.get("hash"))
    if not on.get("txs"):
        step("lock: createMatch (player1)", on.get("create_tx_hash"))
        step("lock: joinMatch (player2)", on.get("join_tx_hash"))
    settle = m.get("onchain_settle") or {}
    step(f"settle: resolveMatch ({settle.get('result') or m.get('result')})", settle.get("tx_hash"))

    final = onchain.read_onchain_match(m["match_id"])
    after = {a["name"]: str(onchain.usdc_balance(a["wallet_address"])) for a in (raja, nero)}
    proof["match"] = {
        "match_id": m["match_id"],
        "match_id_bytes32": m.get("match_id_bytes32"),
        "game": m.get("game_id"),
        "stake_usdc_each": m.get("stake_usdc"),
        "white": m.get("white_agent_id"),
        "result": m.get("result"),
        "termination": m.get("termination"),
        "winner": m.get("winner_agent_id"),
        "plies": len(plies) or (m.get("play") or {}).get("plies"),
        "pgn": m.get("pgn"),
        "status": m.get("status"),
        "settlement_mode": m.get("settlement_mode"),
        "onchain_status_after": final.get("status_name") or final.get("status"),
    }
    proof["usdc_balances"] = {"before": before, "after": after}
    proof["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    spent = 0
    for row in proof["steps"]:
        r = w3.eth.get_transaction_receipt(row["tx"])
        spent += int(r["gasUsed"]) * int(r.get("effectiveGasPrice") or 0)
    proof["gas_spent_avax"] = format(Decimal(spent) / Decimal(10**18), "f")
    deploy_txs = deployment.get("txs") or {}
    if deploy_txs:
        proof["deploy_txs"] = deploy_txs

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, indent=2, default=str) + "\n")
    write_markdown(proof, Path(args.markdown))
    print(json.dumps(proof["match"], indent=2, default=str))
    print(f"balances before {before}\nbalances after  {after}")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    ok = m.get("status") == "settled" and m.get("settlement_mode") == "onchain" and settle.get("tx_hash")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
