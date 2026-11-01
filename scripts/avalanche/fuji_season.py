#!/usr/bin/env python3
"""
Run a short chess season on Avalanche Fuji and record every tx.

Raja, Nero and Sheila (the arena's chess agents) play a double round robin:
every pairing twice, once with each colour. Each match runs the same path as
fuji_proof.py: the ops faucet tops the agents up, MatchService locks both
stakes in BoardmanEscrow v2 (approve, createMatch with the resolver's permit,
approve, joinMatch), the Stack engine plays the game, and the resolver settles
it. Afterwards Boardman's fee sweep (fee_sweep.sweep_escrow_fees) moves the
accrued platform fees to the treasury, and the escrow's books are checked:
balance == totalLocked + accruedFees + totalOwed.

TESTNET ONLY. Same wallets, sandbox and env as fuji_proof.py.

  .venv/bin/python scripts/avalanche/fuji_season.py

Writes docs/avalanche/fuji_season.json and docs/avalanche/FUJI_SEASON.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fuji_proof as fp  # noqa: E402  (shared env, wallets and helpers)

ROOT = fp.ROOT
PAIRINGS = [("raja", "nero"), ("nero", "sheila"), ("sheila", "raja"),
            ("nero", "raja"), ("sheila", "nero"), ("raja", "sheila")]
BOOKS_ABI = [
    {"name": n, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}
    for n in ("totalLocked", "accruedFees", "totalOwed", "totalFeesCollected")
]


def _usd(raw: int) -> str:
    return format(Decimal(raw) / Decimal(10**6), "f")


def write_markdown(season: dict, path: Path) -> None:
    rows = season["matches"]
    books = season["escrow_books_after"]
    sweep = season.get("fee_sweep") or {}
    link = fp._tx_link
    lines = [
        "# Boardman on Avalanche Fuji: chess season",
        "",
        f"Recorded {season['recorded_at']} on Avalanche Fuji (chain {fp.FUJI_CHAIN_ID}) by",
        "[`scripts/avalanche/fuji_season.py`](../../scripts/avalanche/fuji_season.py).",
        "",
        "Raja, Nero and Sheila (Boardman's chess agents) played a double round robin.",
        "Every match was locked in [`BoardmanEscrow` v2]"
        f"({fp.SNOWTRACE}/address/{season['escrow']}), played in Boardman's engine",
        "and settled on-chain by the resolver. Stakes are Circle test USDC with no cash value.",
        "",
        f"- Matches settled on-chain: **{sum(1 for r in rows if r.get('settle_tx'))}** of {len(rows)}",
        f"- USDC locked across the season: **{Decimal(season['usdc_locked_total']).normalize():f}**",
        f"- Platform fees earned: **{season['fees_earned_usdc']} USDC**, swept to the treasury by Boardman's fee sweep"
        + (f" ([tx]({link(sweep['withdrawFees'])}))" if sweep.get("withdrawFees") else ""),
        "- Escrow books after the season: balance "
        f"{books['balance']} = locked {books['totalLocked']} + fees {books['accruedFees']} + owed {books['totalOwed']}"
        f" → **{'balanced' if books['balanced'] else 'NOT balanced'}**",
        f"- Gas for all season transactions: {season['gas_spent_avax']} AVAX",
        "",
        "| # | White | Black | Result | Plies | createMatch | joinMatch | resolveMatch |",
        "|--:|-------|-------|--------|------:|-------------|-----------|--------------|",
    ]
    for i, r in enumerate(rows, 1):
        def cell(key: str) -> str:
            h = r.get(key)
            return f"[{h[:10]}…]({link(h)})" if h else "—"
        result = r.get("result") or r.get("error", "error")[:40]
        lines.append(f"| {i} | {r['white']} | {r['black']} | {result} | {r.get('plies') or '—'} | "
                     f"{cell('create_tx')} | {cell('join_tx')} | {cell('settle_tx')} |")
    tw = season["standings"]
    lines += ["", "## Standings", "",
              "Wallet balances include the ops faucet top-ups made before each match (listed in",
              "[`fuji_season.json`](./fuji_season.json)), so they are not net winnings.", "",
              "| Agent | W | D | L | USDC before | USDC after |", "|-------|--:|--:|--:|--:|--:|"]
    for name, s in tw.items():
        lines.append(f"| {name} | {s['w']} | {s['d']} | {s['l']} | {s['usdc_before']} | {s['usdc_after']} |")
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description="Chess season on Avalanche Fuji")
    ap.add_argument("--wallets", default=str(ROOT / ".fuji" / "wallets.json"))
    ap.add_argument("--deployment", default=str(ROOT / "contracts" / "deployments" / "boardman_v2_avalancheFuji.json"))
    ap.add_argument("--data", default=str(ROOT / ".fuji" / "arena"))
    ap.add_argument("--rpc", default=fp.FUJI_RPC)
    ap.add_argument("--stake", type=float, default=2.0)
    ap.add_argument("--bankroll", type=float, default=3.5)
    ap.add_argument("--out", default=str(ROOT / "docs" / "avalanche" / "fuji_season.json"))
    ap.add_argument("--markdown", default=str(ROOT / "docs" / "avalanche" / "FUJI_SEASON.md"))
    args = ap.parse_args()

    wallets = json.loads(Path(args.wallets).read_text())
    deployment = json.loads(Path(args.deployment).read_text())
    data_dir = Path(args.data)
    data_dir.mkdir(parents=True, exist_ok=True)
    fp._set_env(wallets, deployment, data_dir, args.rpc)
    fp._bootstrap_imports()

    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 60}))
    if int(w3.eth.chain_id) != fp.FUJI_CHAIN_ID:
        raise SystemExit(f"RPC {args.rpc} is chain {w3.eth.chain_id}, not Fuji")
    from gaming.src.backend.services.chains import reload_chains_config

    reload_chains_config()
    from gaming.src.stack.agentic import fee_sweep, onchain
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry

    cfg = onchain._chain_config()
    assert cfg["chain_id"] == "avalanche", cfg
    funder_pk = wallets["wallets"]["funder_deployer"]["private_key"]
    escrow = w3.eth.contract(address=w3.to_checksum_address(cfg["escrow"]), abi=BOOKS_ABI)
    fees_before = int(escrow.functions.totalFeesCollected().call())

    agents = {a["name"].lower(): a for a in get_registry().ensure_demo_agents()}
    players = {k: agents[k] for k in ("raja", "nero", "sheila")}
    stake, bankroll = Decimal(str(args.stake)), Decimal(str(max(args.bankroll, args.stake)))
    usdc_before = {a["name"]: str(onchain.usdc_balance(a["wallet_address"])) for a in players.values()}
    txs: list[str] = []
    season: dict = {"network": "Avalanche Fuji C-Chain", "chain_id": fp.FUJI_CHAIN_ID, "escrow": cfg["escrow"],
                    "agents": {a["name"]: a["wallet_address"] for a in players.values()}, "matches": [], "topups": []}
    out = Path(args.out)

    def top_up(a: dict) -> None:
        addr = a["wallet_address"]
        if w3.eth.get_balance(addr) < fp.GAS_TOPUP_WEI // 5:
            h = fp._send_native(w3, funder_pk, addr, fp.GAS_TOPUP_WEI)
            txs.append(h)
            season["topups"].append({"agent": a["name"], "kind": "gas", "tx": h})
        have = onchain.usdc_balance(addr)
        if have < bankroll:
            r = onchain.fund_agent_from_key(addr, bankroll - have, funder_key=funder_pk)
            txs.append(r["tx_hash"])
            season["topups"].append({"agent": a["name"], "kind": "usdc", "usdc": str(bankroll - have), "tx": r["tx_hash"]})
            time.sleep(2)

    svc = get_match_service()
    for white_k, black_k in PAIRINGS:
        white, black = players[white_k], players[black_k]
        row = {"white": white["name"], "black": black["name"]}
        print(f"{white['name']} (white) vs {black['name']} ...", flush=True)
        try:
            top_up(white)
            top_up(black)
            m = svc.create_match(agent_a_id=white["agent_id"], agent_b_id=black["agent_id"], stake_usdc=float(stake),
                                 white_agent_id=white["agent_id"], game_id="agentic.chess_standard")
            m = svc.run_match(m["match_id"], move_delay_sec=0)
            on, settle = m.get("onchain") or {}, m.get("onchain_settle") or {}
            row.update({
                "match_id": m["match_id"], "stake_usdc": m.get("stake_usdc"), "result": m.get("result"),
                "termination": m.get("termination"), "winner": m.get("winner_agent_id"),
                "plies": (m.get("play") or {}).get("plies") or len(m.get("moves") or []),
                "create_tx": on.get("create_tx_hash"), "join_tx": on.get("join_tx_hash"),
                "settle_tx": settle.get("tx_hash"), "status": m.get("status"),
                "lock_txs": [t.get("tx_hash") for t in on.get("txs") or []],
            })
            txs += [h for h in row["lock_txs"] + [row["settle_tx"]] if h]
            print(f"   {row['result']} by {row['termination']} in {row['plies']} plies; settle {row['settle_tx']}", flush=True)
        except Exception as exc:  # keep the season going; the row records what failed
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            print(f"   FAILED: {row['error']}", flush=True)
        season["matches"].append(row)
        out.write_text(json.dumps(season, indent=2, default=str) + "\n")

    # Boardman's own fee sweep: accrued platform fees -> treasury.
    sweep = fee_sweep.sweep_escrow_fees()
    season["fee_sweep"] = {k: sweep.get(k) for k in ("contract", "version", "accrued_raw", "withdrawFees")}
    if sweep.get("withdrawFees"):
        txs.append(sweep["withdrawFees"])
    usdc = w3.eth.contract(address=w3.to_checksum_address(cfg["usdc"]), abi=onchain.ERC20_ABI)
    bal = int(usdc.functions.balanceOf(w3.to_checksum_address(cfg["escrow"])).call())
    books = {n: int(getattr(escrow.functions, n)().call()) for n in ("totalLocked", "accruedFees", "totalOwed")}
    season["escrow_books_after"] = {"balance": _usd(bal), **{k: _usd(v) for k, v in books.items()},
                                    "balanced": bal == sum(books.values())}
    season["fees_earned_usdc"] = _usd(int(escrow.functions.totalFeesCollected().call()) - fees_before)
    season["usdc_locked_total"] = format(sum(Decimal(str(r.get("stake_usdc") or 0)) * 2 for r in season["matches"]
                                             if r.get("settle_tx")), "f")
    standings = {a["name"]: {"w": 0, "d": 0, "l": 0, "usdc_before": usdc_before[a["name"]],
                             "usdc_after": str(onchain.usdc_balance(a["wallet_address"]))} for a in players.values()}
    for r in season["matches"]:
        if not r.get("settle_tx"):
            continue
        if r.get("winner"):
            win = next(a["name"] for a in players.values() if a["agent_id"] == r["winner"])
            lose = r["black"] if win == r["white"] else r["white"]
            standings[win]["w"] += 1
            standings[lose]["l"] += 1
        else:
            standings[r["white"]]["d"] += 1
            standings[r["black"]]["d"] += 1
    season["standings"] = standings
    spent = 0
    for h in txs:
        rc = w3.eth.get_transaction_receipt(h)
        spent += int(rc["gasUsed"]) * int(rc.get("effectiveGasPrice") or 0)
    season["gas_spent_avax"] = format(Decimal(spent) / Decimal(10**18), "f")
    season["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out.write_text(json.dumps(season, indent=2, default=str) + "\n")
    write_markdown(season, Path(args.markdown))
    print(json.dumps({k: season[k] for k in ("fees_earned_usdc", "usdc_locked_total", "escrow_books_after",
                                             "gas_spent_avax", "standings")}, indent=2))
    return 0 if all(r.get("settle_tx") for r in season["matches"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
