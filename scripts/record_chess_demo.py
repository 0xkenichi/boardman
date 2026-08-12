#!/usr/bin/env python3
"""
Boardman Agent Arena — RECORD MODE

Screen-record this terminal. Clean pacing, big labels, wallets, live Stockfish moves.

  export PYTHONPATH=$PWD
  python3 scripts/record_chess_demo.py
  python3 scripts/record_chess_demo.py --delay 1.4 --white raja
  python3 scripts/record_chess_demo.py --fast          # quicker takes
  python3 scripts/record_chess_demo.py --no-stockfish  # offline local only

Providers: chess-api.com (primary) · stockfish.online (fallback)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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


CLEAR = "\033[2J\033[H"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"
RED = "\033[91m"


def banner(title: str) -> None:
    print(CLEAR, end="")
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}  {BOLD}{WHITE}BOARDMAN AGENT ARENA{RESET}  ·  skill 1v1 · USDC escrow on Arc  {CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════╝{RESET}")
    print(f"  {DIM}{title}{RESET}\n")


def pause(sec: float) -> None:
    if sec > 0:
        time.sleep(sec)


def main() -> int:
    _bootstrap()
    ap = argparse.ArgumentParser()
    ap.add_argument("--white", choices=("raja", "nero"), default="raja")
    ap.add_argument("--stake", type=float, default=5.0)
    ap.add_argument("--delay", type=float, default=1.25, help="seconds between moves (record pace)")
    ap.add_argument("--seed", type=int, default=20260812)
    ap.add_argument("--fast", action="store_true", help="delay=0.35, less intro")
    ap.add_argument("--no-stockfish", action="store_true")
    ap.add_argument("--onchain", action="store_true", help="dual-lock BoardmanEscrow on Arc")
    ap.add_argument("--max-plies", type=int, default=100)
    ap.add_argument("--json-out", type=str, default="data/agentic/last_record_match.json")
    args = ap.parse_args()

    if args.fast:
        args.delay = 0.35
    if args.no_stockfish:
        os.environ["BOARDMAN_USE_STOCKFISH"] = "0"
    else:
        os.environ.setdefault("BOARDMAN_USE_STOCKFISH", "1")
        os.environ.setdefault("BOARDMAN_SF_DEPTH", "11")
        os.environ.setdefault("BOARDMAN_SF_THINK_MS", "70")
    if args.onchain:
        os.environ["BOARDMAN_AGENTIC_ONCHAIN"] = "1"

    os.environ["BOARDMAN_MAX_PLIES"] = str(args.max_plies)

    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.chess.personas import get_persona
    from gaming.src.stack.agentic import ledger

    reg = get_registry()
    agents = reg.ensure_demo_agents()
    by_name = {a["name"].lower(): a for a in agents}
    for a in agents:
        p = get_persona(a["agent_id"])
        if p:
            a["mind"] = p["mind"]
            a["openings"] = p["openings"]

    raja = by_name["raja"]
    nero = by_name["nero"]

    # ── Intro cards ────────────────────────────────────────────────────────
    banner("Preparing agents…")
    pause(0.8 if not args.fast else 0.2)

    def card(a: dict, color: str) -> None:
        p = get_persona(a["agent_id"]) or {}
        mind = p.get("mind") or {}
        print(f"{color}{BOLD}◆ {a['name'].upper()}{RESET}")
        print(f"  Strategy : {', '.join(a.get('openings') or [])}")
        print(f"  Wallet   : {a['wallet_address']}")
        print(f"  Contract : {a['identity_contract']}")
        print(f"  Chain    : Arc  ·  USDC escrow")
        blurb = (mind.get("blurb") or "")[:110]
        if blurb:
            print(f"  Mind     : {DIM}{blurb}…{RESET}")
        print()

    card(raja, MAGENTA)
    card(nero, YELLOW)
    print(f"{DIM}Engines: opening book → chess-api.com / stockfish.online → local fallback{RESET}")
    pause(2.2 if not args.fast else 0.4)

    # ── Lock sequence ──────────────────────────────────────────────────────
    from gaming.src.stack.agentic.onchain import onchain_enabled

    banner("Dual-lock USDC escrow")
    mode = "ON-CHAIN Arc BoardmanEscrow" if onchain_enabled() else "demo ledger (set --onchain + keys for live)"
    print(f"  Mode      : {BOLD}{mode}{RESET}")
    print(f"  Stake     : {BOLD}${args.stake:.2f} USDC{RESET} each")
    print(f"  Pot       : {BOLD}${args.stake * 2:.2f} USDC{RESET}")
    print(f"  White     : {BOLD}{args.white.title()}{RESET}")
    print(f"  Fee       : 3% BoardmanEscrow V1 (from pot on settle)")
    print(f"  Escrow    : 0x3cD57447490c81598Bd8CaCBe3843b24E5735A77")
    pause(1.0 if not args.fast else 0.2)

    svc = get_match_service()
    # create + lock with drama
    white_id = raja["agent_id"] if args.white == "raja" else nero["agent_id"]
    other_id = nero["agent_id"] if args.white == "raja" else raja["agent_id"]
    m = svc.create_match(
        agent_a_id=white_id,
        agent_b_id=other_id,
        stake_usdc=args.stake,
        white_agent_id=white_id,
    )
    print(f"\n  Match ID  : {m['match_id']}")
    print(f"  bytes32   : {m.get('match_id_bytes32')}")
    print(f"  mode      : {m.get('settlement_mode')}")
    print(f"  {GREEN}✓{RESET} Escrow open")
    pause(0.6 if not args.fast else 0.1)
    print(f"  {DIM}Locking (approve + createMatch + joinMatch if on-chain)…{RESET}")
    m = svc.lock_both(m["match_id"])
    print(f"  {GREEN}✓{RESET} {args.white.title()} locked ${args.stake:.2f}")
    pause(0.5 if not args.fast else 0.1)
    print(f"  {GREEN}✓{RESET} Opponent locked ${args.stake:.2f}")
    oc = (m.get("escrow") or {}).get("onchain") or m.get("onchain") or {}
    if oc.get("explorer_create"):
        print(f"  create tx : {oc.get('create_tx_hash')}")
        print(f"  {DIM}{oc.get('explorer_create')}{RESET}")
    if oc.get("explorer_join"):
        print(f"  join tx   : {oc.get('join_tx_hash')}")
        print(f"  {DIM}{oc.get('explorer_join')}{RESET}")
    if m.get("onchain_error"):
        print(f"  {YELLOW}on-chain fallback:{RESET} {str(m.get('onchain_error'))[:140]}")
    print(f"  {BOLD}{GREEN}LOCKED — play begins{RESET}")
    pause(1.4 if not args.fast else 0.3)

    # ── Live play ──────────────────────────────────────────────────────────
    move_log: list[str] = []

    def on_move(ev) -> None:
        banner(f"Live · move {ev.move_number} · {ev.side.upper()}")
        name = ev.agent_name
        flags = []
        if ev.is_capture:
            flags.append("capture")
        if ev.is_check:
            flags.append("CHECK")
        flag_s = f"  {RED}{' · '.join(flags)}{RESET}" if flags else ""
        src = ev.engine_source or "?"
        eval_s = f"  eval {ev.eval_pawns:+.2f}" if ev.eval_pawns is not None else ""
        print(f"  {BOLD}{name}{RESET} plays {BOLD}{CYAN}{ev.san}{RESET}{flag_s}")
        print(f"  {DIM}engine: {src}{eval_s}{RESET}\n")
        print(ev.board_unicode)
        print()
        # compact move list
        if ev.side == "white":
            move_log.append(f"{ev.move_number}. {ev.san}")
        else:
            if move_log:
                move_log[-1] += f"  {ev.san}"
            else:
                move_log.append(f"{ev.move_number}… {ev.san}")
        # show last few moves
        tail = move_log[-6:]
        print(f"  {DIM}{'  ·  '.join(tail)}{RESET}")
        print(
            f"\n  {DIM}Raja {raja['wallet_address'][:10]}…{RESET}"
            f"    {DIM}Nero {nero['wallet_address'][:10]}…{RESET}"
        )

    print(f"\n{DIM}Thinking with Stockfish… first moves may take ~1s each.{RESET}\n")
    pause(0.5 if not args.fast else 0)

    match = svc.run_chess(
        m["match_id"],
        move_delay_sec=args.delay,
        seed=args.seed,
        on_move=on_move,
    )

    # ── Result ─────────────────────────────────────────────────────────────
    banner("Settlement")
    result = match.get("result")
    winner = match.get("winner_agent_id")
    esc = match.get("escrow") or {}
    print(f"  Result      : {BOLD}{result}{RESET}  ({match.get('termination')})")
    print(f"  Winner      : {BOLD}{winner or 'draw'}{RESET}")
    print(f"  Plies       : {(match.get('play') or {}).get('plies')}")
    print(f"  Mode        : {match.get('settlement_mode')}")
    print(f"  Escrow      : {esc.get('status')}")
    if esc.get("payout") and esc.get("payout") != "0":
        print(f"  Payout      : {GREEN}{BOLD}{esc.get('payout')} USDC{RESET}  (fee {esc.get('fee')})")
    else:
        print(f"  Payout      : refund / draw")
    settle_oc = (esc.get("onchain_settle") or match.get("onchain_settle") or {})
    if settle_oc.get("explorer"):
        print(f"  settle tx   : {settle_oc.get('tx_hash')}")
        print(f"  {DIM}{settle_oc.get('explorer')}{RESET}")
    if match.get("onchain_settle_error"):
        print(f"  {YELLOW}settle fallback:{RESET} {str(match.get('onchain_settle_error'))[:140]}")
    print()
    print(f"  Raja balance : {ledger.balance(raja['wallet_address'])} USDC  (demo ledger)")
    print(f"  Nero balance : {ledger.balance(nero['wallet_address'])} USDC  (demo ledger)")
    print()
    print(f"{DIM}── PGN ──{RESET}")
    print(match.get("pgn") or "")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # slim moves for file size (drop unicode boards)
    slim = dict(match)
    slim_moves = []
    for mv in match.get("moves") or []:
        slim_moves.append(
            {
                k: mv[k]
                for k in (
                    "ply",
                    "move_number",
                    "side",
                    "agent_id",
                    "agent_name",
                    "san",
                    "uci",
                    "fen",
                    "is_check",
                    "is_capture",
                    "engine_source",
                    "eval_pawns",
                )
                if k in mv
            }
        )
    slim["moves"] = slim_moves
    out.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    print(f"\n{GREEN}Saved{RESET} {out}")
    print(f"{DIM}Also open frontend/public/agentic/arena.html for the web board replay.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
