"""One-off repair for agm_91dadd7c75f5 (2026-10-05).

A phantom draw-settlement at 18:13:22 (before the real 18:15:15 result)
corrupted three stores:
  1. ledger escrow  — draw-refunded both agents ($20 each back)
  2. spectator book — settled as draw_hits with an empty bettor payout list
  3. match record   — snapshots the two above

Truth: Nero (side a) lost on time -> Sheila (side b) won the skill escrow
and every side-a fan bet (including the user's $10 on Nero) loses.

Repair (money-math, pot = 40 skill + 12 fan pool):
  - spectator book: re-settle winner_take_side "b" via SpectatorBook.settle
      pot 12, 9% fee 1.08 -> treasury, creator pool 260bps 0.312 -> 0.156 each
      creator_spectator_fee (ledger credits, book was on-chain but these JSON
      creator fees were never credited), winning-side payout list = empty
      (the only side-b "bettor" is Sheila's 1.0 seed, paid via draw-underwrite
      agent_split 0.9528 each), side-a bets (user's $10) lose as placed.
  - ledger escrow: restore to locked, then settle(result="win", Sheila):
      debit Nero 20.0 (undo the improper refund), credit Sheila 38.8,
      treasury +1.2.
  - match record (archive): escrow snapshot + spectator_book snapshot.
  - audit txs appended for every corrective move. Backups first.

Run:  PYTHONPATH=. .venv/bin/python scripts/repair_agm_91dadd7c75f5.py
"""

from __future__ import annotations

import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaming.src.stack.agentic import ledger  # noqa: E402
from gaming.src.stack.agentic.economy.spectator import SpectatorBook  # noqa: E402
from gaming.src.stack.agentic.economy.fees import platform_fee_for_pot  # noqa: E402

MID = "agm_91dadd7c75f5"
DATA = ROOT / "data" / "agentic"
LEDGER_FILE = DATA / "ledger.json"
BOOKS_FILE = DATA / "spectator_books.json"
ARCHIVE_FILE = DATA / "matches_archive.json"
TREASURY = "0xboardman_agentic_treasury"
NERO_WALLET = "0xe430c73cf2bed38abe83df8309763191624373e1"
SHEILA_WALLET = "0x368f716574ffe34fe2b3e32510bc5c4e1f689ba3"
NOW = "2026-10-05T12:30:00+00:00"  # repair timestamp (UTC), overwritten below
import datetime  # noqa: E402

NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()


def audit(ledger_data: dict, wallet: str, amount: Decimal, reason: str) -> None:
    ledger_data["txs"].append(
        {
            "ts": NOW,
            "type": "repair",
            "wallet": wallet,
            "amount": str(amount),
            "reason": reason,
            "ref": MID,
            "note": "settlement-integrity repair: phantom draw corrected to real result (Sheila win)",
        }
    )


def main() -> None:
    # ---- 1. backups -------------------------------------------------------
    stamp = "20261005_repair"
    for f in (LEDGER_FILE, BOOKS_FILE, ARCHIVE_FILE):
        dst = f.with_name(f"{f.stem}.{stamp}.bak{f.suffix}")
        shutil.copy2(f, dst)
        print(f"backup: {dst.name}")

    led = json.loads(LEDGER_FILE.read_text())
    books_doc = json.loads(BOOKS_FILE.read_text())
    arch = json.loads(ARCHIVE_FILE.read_text())
    m = arch["matches"][MID]

    esc = led["escrows"][MID]
    book = books_doc["books"][MID]
    assert esc["status"] == "settled" and esc.get("result") == "draw", esc
    assert book["status"] == "settled" and (book.get("payouts") or {}).get("mode") == "draw_hits", book
    print("pre-state checks OK (corrupt draw settlement present)")

    # stash the corrupt book payouts for the audit trail, then reset the
    # book to open so SpectatorBook.settle accepts the corrected result
    # (its new conflict guard refuses settled books with a different winner
    # — by design; the reset is the explicit, audited un-corruption).
    book["payouts_corrupted_draw"] = book.get("payouts")
    book["payouts_corrupted_draw"]["repaired_at"] = NOW
    book["status"] = "open"
    book["settled_at"] = None
    book["payouts"] = None

    # ---- 2. escrow: restore to locked, then settle correctly -------------
    esc["status"] = "locked"
    esc["settled_at"] = None
    esc["winner_wallet"] = None
    esc["payout"] = None
    esc["fee"] = None
    esc["result"] = None
    audit(led, NERO_WALLET, Decimal("0"), "escrow restored to locked before correct win settlement")
    # note: no balance change here — the improper +20 refunds are corrected
    # explicitly below so every money move has its own audit line.

    stake = Decimal("20")
    pot = stake * 2
    fee = platform_fee_for_pot(pot)          # flat tier: 1.200000
    payout = pot - fee                        # 38.800000
    # undo the improper draw refunds: Nero's 20 comes back to the pot.
    nero_bal = Decimal(led["balances"][NERO_WALLET])
    led["balances"][NERO_WALLET] = str(nero_bal - Decimal("20"))
    audit(led, NERO_WALLET, Decimal("-20"), "undo improper draw refund (Nero lost on time)")
    # pay Sheila pot minus fee
    sheila_bal = Decimal(led["balances"][SHEILA_WALLET])
    led["balances"][SHEILA_WALLET] = str(sheila_bal + payout)
    audit(led, SHEILA_WALLET, payout, "skill pot payout (winner, Nero lost on time)")
    led["balances"][TREASURY] = str(Decimal(led["balances"][TREASURY]) + fee)
    audit(led, TREASURY, fee, "platform fee (skill pot)")

    esc.update(
        {
            "status": "settled",
            "settled_at": NOW,
            "winner_wallet": SHEILA_WALLET,
            "payout": str(payout),
            "fee": str(fee),
            "result": "win",
            "repaired_from": "draw",
            "repaired_at": NOW,
        }
    )
    led["txs"].append({"ts": NOW, "type": "escrow_settle", "ref": MID})
    print(f"escrow: Sheila +{payout}, treasury +{fee}, Nero -20 (refund undone)")

    # ---- 3. spectator book: re-settle as Sheila win -----------------------
    sb = SpectatorBook()
    books_doc = sb._load()  # hot file view
    books_doc["books"][MID] = book  # keep our audit-stashed copy
    sb._save(books_doc)
    settled = sb.settle(MID, winner_side="b")
    print(
        "book: mode=%s winner_side=%s bettor_payouts=%d creators=%s"
        % (
            settled["payouts"]["mode"],
            settled["payouts"]["winner_side"],
            len(settled["payouts"]["bettors"]),
            [c["amount"] for c in settled["payouts"]["creators"]],
        )
    )
    # ledger credits matches.py would have made (book was on-chain, so only
    # JSON creator fees + draw-underwrite agent splits):
    for c in settled["payouts"]["creators"]:
        amt = Decimal(c["amount"])
        wallet = f"creator:{c['creator_id']}"
        led["balances"][wallet] = str(Decimal(led["balances"].get(wallet, "0")) + amt)
        audit(led, wallet, amt, "creator_spectator_fee (missed in corrupted settle)")
    for sp in (settled["payouts"]["draw_book"] or {}).get("agent_split") or []:
        w = sp.get("wallet")
        amt = Decimal(str(sp.get("amount") or "0"))
        if w and amt > 0:
            led["balances"][w] = str(Decimal(led["balances"].get(w, "0")) + amt)
            audit(led, w, amt, "draw-underwrite agent split (win side)")
    for sr in settled["payouts"].get("seed_refunds") or []:
        w = sr.get("wallet")
        amt = Decimal(str(sr.get("amount") or "0"))
        if w and amt > 0:
            led["balances"][w] = str(Decimal(led["balances"].get(w, "0")) + amt)
            audit(led, w, amt, "draw_seed_return (skipped by corrupt draw settle)")

    # ---- 4. match record snapshots (archive) ------------------------------
    m["escrow"] = dict(esc)
    m["spectator_book"] = {
        "status": settled["status"],
        "totals": settled.get("totals"),
        "payouts": settled.get("payouts"),
        "onchain": bool(settled.get("onchain")),
        "pool": settled.get("pool"),
        "open_tx_hash": settled.get("open_tx_hash"),
        "resolve_tx_hash": settled.get("resolve_tx_hash"),
    }
    m["settlement_repair"] = {
        "repaired_at": NOW,
        "reason": "phantom draw settlement at 2026-10-04T18:13:22Z preceded real result; corrected to Sheila win (black_win, time)",
        "user_bet": {
            "bettor_id": "62440a47-f4fc-4249-a627-46aaa2d039ef",
            "side": "a",
            "amount": "10.0",
            "outcome": "lost (Nero ran out of time)",
            "tx_hash": "0x86161bcd9f4fd5a72ef63c2e1fe631b9b30590b6c1da601985d62a5ee3c1bbe1",
        },
    }
    print("match archive record updated")

    # ---- 5. write everything ---------------------------------------------
    LEDGER_FILE.write_text(json.dumps(led, indent=1))
    sb._save(books_doc)
    ARCHIVE_FILE.write_text(json.dumps(arch, indent=1))
    print("WROTE ledger.json, spectator_books.json, matches_archive.json")

    print("\n== POST-STATE ==")
    for w in (NERO_WALLET, SHEILA_WALLET, TREASURY, "creator:creator_nero_forge", "creator:creator_sheila_lab"):
        print(" ", w, led["balances"].get(w))
    print("escrow:", {k: esc[k] for k in ("status", "result", "winner_wallet", "payout", "fee")})


if __name__ == "__main__":
    main()
