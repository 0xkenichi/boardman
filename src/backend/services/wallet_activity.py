"""
Detect on-chain USDC deposits / outflows and notify players.

Circle webhooks are ideal in production; this balance-watch poller works for
local polling mode and as a backup when webhooks are delayed.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from gaming.src.backend.services.chains import get_chain, list_chains

logger = logging.getLogger(__name__)

# Ignore dust / RPC noise
MIN_DELTA = Decimal(os.getenv("WALLET_WATCH_MIN_DELTA", "0.01"))
# Skip outflow alerts if bot withdraw already logged within this window
RECENT_DEBIT_SECONDS = int(os.getenv("WALLET_WATCH_DEBIT_SKIP_SEC", "600"))

_SNAPSHOT_PATH = Path(
    os.getenv(
        "WALLET_WATCH_SNAPSHOT_PATH",
        str(Path(__file__).resolve().parents[3] / "data" / "wallet_watch_snapshots.json"),
    )
)

# In-process: user_id → chain_id → Decimal balance (also persisted to disk)
_snapshots: dict[str, dict[str, str]] = {}
_loaded = False


def _load_snapshots() -> None:
    global _loaded, _snapshots
    if _loaded:
        return
    _loaded = True
    try:
        if _SNAPSHOT_PATH.exists():
            raw = json.loads(_SNAPSHOT_PATH.read_text())
            if isinstance(raw, dict):
                _snapshots = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
                logger.info("[WalletWatch] Loaded %s snapshot users", len(_snapshots))
    except Exception:
        logger.exception("[WalletWatch] Failed to load snapshots")
        _snapshots = {}


def _save_snapshots() -> None:
    try:
        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SNAPSHOT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(_snapshots, indent=2, sort_keys=True))
        tmp.replace(_SNAPSHOT_PATH)
    except Exception:
        logger.exception("[WalletWatch] Failed to save snapshots")


def get_snapshot(user_id: str, chain_id: str) -> Optional[Decimal]:
    _load_snapshots()
    val = (_snapshots.get(user_id) or {}).get(chain_id)
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def set_snapshot(user_id: str, chain_id: str, balance: Decimal) -> None:
    _load_snapshots()
    _snapshots.setdefault(user_id, {})[chain_id] = f"{balance:.6f}"
    _save_snapshots()


def _sb():
    from backend.supabase_client import get_supabase

    return get_supabase()


def log_credit(
    user_id: str,
    amount: Decimal,
    chain_id: str,
    *,
    tx_hash: Optional[str] = None,
    source: str = "balance_watch",
) -> None:
    """Append a credit audit row (idempotent-ish via unique tx_hash)."""
    h = tx_hash or f"{source}:{chain_id}:{user_id[:8]}:{int(time.time())}:{amount}:{uuid.uuid4().hex[:8]}"
    try:
        _sb().schema("gaming").table("wallet_credit_audit").insert(
            {
                "user_id": user_id,
                "tx_hash": h[:200],
                "amount_usdc": float(amount),
                "status": "credited",
            }
        ).execute()
    except Exception as exc:
        # Duplicate or missing column — non-fatal
        logger.warning("[WalletWatch] credit audit skip: %s", exc)


def log_debit(
    user_id: str,
    amount: Decimal,
    chain_id: str,
    *,
    recipient_address: Optional[str] = None,
    recipient_id: Optional[str] = None,
    circle_transaction_id: Optional[str] = None,
    tx_hash: Optional[str] = None,
    status: str = "pending",
    source: str = "balance_watch",
) -> None:
    row: dict[str, Any] = {
        "sender_id": user_id,
        "recipient_id": recipient_id,
        "recipient_address": (recipient_address or f"{source}:{chain_id}")[:80],
        "amount_usdc": float(amount),
        "circle_transaction_id": circle_transaction_id,
        "tx_hash": tx_hash,
        "status": status,
    }
    try:
        _sb().schema("gaming").table("wallet_debit_audit").insert(row).execute()
    except Exception as exc:
        logger.warning("[WalletWatch] debit audit skip: %s", exc)


def recent_bot_debit(user_id: str, amount: Decimal, window_sec: int = RECENT_DEBIT_SECONDS) -> bool:
    """True if a bot withdrawal of ~amount was recorded recently (avoid double DM)."""
    try:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_sec)).isoformat()
        r = (
            _sb()
            .schema("gaming")
            .table("wallet_debit_audit")
            .select("amount_usdc,created_at,status")
            .eq("sender_id", user_id)
            .gte("created_at", cutoff)
            .limit(20)
            .execute()
        )
        for row in r.data or []:
            try:
                a = Decimal(str(row.get("amount_usdc") or 0))
            except Exception:
                continue
            if abs(a - amount) <= MIN_DELTA:
                return True
    except Exception as exc:
        logger.warning("[WalletWatch] recent debit check failed: %s", exc)
    return False


def format_deposit_message(
    amount: Decimal,
    new_balance: Decimal,
    chain_id: str,
    *,
    tx_hash: Optional[str] = None,
) -> str:
    label = get_chain(chain_id).get("label", chain_id)
    tx_line = f"\nTx: <code>{tx_hash}</code>" if tx_hash else ""
    return (
        f"📥 <b>Deposit received</b>\n\n"
        f"Amount: <b>+${amount:,.2f} USDC</b>\n"
        f"Network: <b>{label}</b>\n"
        f"New balance: <b>${new_balance:,.2f} USDC</b>"
        f"{tx_line}\n\n"
        f"Tap 💰 Wallet to see all networks."
    )


def format_withdraw_message(
    amount: Decimal,
    new_balance: Decimal,
    chain_id: str,
    *,
    destination: Optional[str] = None,
    tx_hash: Optional[str] = None,
    status: str = "submitted",
) -> str:
    label = get_chain(chain_id).get("label", chain_id)
    dest = f"\nTo: {destination}" if destination else ""
    tx_line = f"\nTx: <code>{tx_hash}</code>" if tx_hash else ""
    return (
        f"📤 <b>Withdrawal {status}</b>\n\n"
        f"Amount: <b>−${amount:,.2f} USDC</b>\n"
        f"Network: <b>{label}</b>"
        f"{dest}\n"
        f"New balance: <b>${new_balance:,.2f} USDC</b>"
        f"{tx_line}"
    )


def format_outflow_message(amount: Decimal, new_balance: Decimal, chain_id: str) -> str:
    label = get_chain(chain_id).get("label", chain_id)
    return (
        f"📤 <b>USDC left your wallet</b>\n\n"
        f"Amount: <b>−${amount:,.2f} USDC</b>\n"
        f"Network: <b>{label}</b>\n"
        f"New balance: <b>${new_balance:,.2f} USDC</b>\n\n"
        f"(Could be a withdrawal, stake lock, or external send.)"
    )


async def notify_deposit(
    user_id: str,
    amount: Decimal,
    new_balance: Decimal,
    chain_id: str,
    *,
    tx_hash: Optional[str] = None,
    log: bool = True,
) -> bool:
    from gaming.src.bot.keyboards import wallet_menu
    from gaming.src.bot.utils.notify import notify_user

    if log:
        log_credit(user_id, amount, chain_id, tx_hash=tx_hash)
    text = format_deposit_message(amount, new_balance, chain_id, tx_hash=tx_hash)
    return await notify_user(user_id, text, buttons=wallet_menu())


async def notify_withdrawal(
    user_id: str,
    amount: Decimal,
    new_balance: Decimal,
    chain_id: str,
    *,
    destination: Optional[str] = None,
    tx_hash: Optional[str] = None,
    status: str = "submitted",
) -> bool:
    from gaming.src.bot.keyboards import wallet_menu
    from gaming.src.bot.utils.notify import notify_user

    text = format_withdraw_message(
        amount, new_balance, chain_id, destination=destination, tx_hash=tx_hash, status=status
    )
    return await notify_user(user_id, text, buttons=wallet_menu())


def list_watch_profiles() -> list[dict]:
    """Profiles that can receive wallet DMs (have Telegram + deposit address).

    Prefer recently active users when the list grows (free-tier friendly).
    """
    try:
        r = (
            _sb()
            .table("profiles")
            .select(
                "id,gaming_tag,gaming_telegram_chat_id,gaming_deposit_address,"
                "circle_wallet_id,last_active_at,updated_at"
            )
            .not_.is_("gaming_telegram_chat_id", "null")
            .not_.is_("gaming_deposit_address", "null")
            .limit(200)
            .execute()
        )
        rows = list(r.data or [])
    except Exception:
        try:
            r = (
                _sb()
                .table("profiles")
                .select(
                    "id,gaming_tag,gaming_telegram_chat_id,gaming_deposit_address,circle_wallet_id"
                )
                .not_.is_("gaming_telegram_chat_id", "null")
                .not_.is_("gaming_deposit_address", "null")
                .limit(200)
                .execute()
            )
            rows = list(r.data or [])
        except Exception:
            logger.exception("[WalletWatch] list profiles failed")
            return []

    # Cap concurrent watchers for free hosts (CPU/RPC)
    max_watch = int(os.getenv("WALLET_WATCH_MAX_USERS", "50"))
    if len(rows) <= max_watch:
        return rows

    def _score(p: dict) -> str:
        return str(p.get("last_active_at") or p.get("updated_at") or "")

    rows.sort(key=_score, reverse=True)
    return rows[:max_watch]


async def process_balance_change(
    user_id: str,
    chain_id: str,
    old: Optional[Decimal],
    new: Decimal,
) -> Optional[str]:
    """
    Compare old vs new balance. Returns action: deposit|outflow|baseline|none.
    First observation (old is None) only baselines — no spam on restart.
    """
    set_snapshot(user_id, chain_id, new)

    if old is None:
        return "baseline"

    delta = new - old
    if abs(delta) < MIN_DELTA:
        return "none"

    if delta > 0:
        await notify_deposit(user_id, delta, new, chain_id)
        logger.info(
            "[WalletWatch] deposit user=%s chain=%s +%s → %s",
            user_id[:8],
            chain_id,
            delta,
            new,
        )
        return "deposit"

    amount = abs(delta)
    if recent_bot_debit(user_id, amount):
        logger.info(
            "[WalletWatch] outflow skipped (bot withdraw) user=%s chain=%s -%s",
            user_id[:8],
            chain_id,
            amount,
        )
        return "outflow_skipped"

    # Unexplained outflow — still log + soft notify
    log_debit(user_id, amount, chain_id, status="detected", source="balance_watch")
    from gaming.src.bot.keyboards import wallet_menu
    from gaming.src.bot.utils.notify import notify_user

    await notify_user(
        user_id,
        format_outflow_message(amount, new, chain_id),
        buttons=wallet_menu(),
    )
    logger.info(
        "[WalletWatch] outflow user=%s chain=%s -%s → %s",
        user_id[:8],
        chain_id,
        amount,
        new,
    )
    return "outflow"


def _watch_chain_ids() -> list[str]:
    """Only poll chains with Circle + USDC (skip MiniPay/Celo host shells)."""
    out: list[str] = []
    for c in list_chains():
        if c.get("circle_blockchain") and c.get("usdc_address"):
            out.append(c["id"])
    return out or ["arc"]


async def watch_user_balances(user_id: str) -> dict[str, str]:
    """Poll settlement chains for one user. Returns chain → action.

    Uses strict balance (RPC error ≠ $0) so we never fake a deposit/outflow
    when the node is flaky or the play address just rotated.
    """
    import asyncio

    from gaming.src.backend.services.clawstation_circle import get_usdc_balance_strict

    actions: dict[str, str] = {}
    chains = _watch_chain_ids()

    async def _one(cid: str) -> tuple[str, Optional[Decimal], Optional[str]]:
        try:
            bal, err = await asyncio.wait_for(
                get_usdc_balance_strict(user_id, chain_id=cid), timeout=10
            )
            if err:
                logger.warning(
                    "[WalletWatch] balance fail %s %s: %s", user_id[:8], cid, err
                )
                return cid, None, err
            return cid, bal, None
        except Exception as exc:
            logger.warning("[WalletWatch] balance fail %s %s: %s", user_id[:8], cid, exc)
            return cid, None, str(exc)

    results = await asyncio.gather(*[_one(c) for c in chains])
    for cid, bal, err in results:
        if bal is None:
            actions[cid] = "error"
            continue
        old = get_snapshot(user_id, cid)
        actions[cid] = await process_balance_change(user_id, cid, old, bal) or "none"
    return actions


async def watch_all_wallets() -> dict[str, Any]:
    """One scheduler tick: poll Telegram-linked wallets (bounded concurrency)."""
    import asyncio
    import os

    profiles = list_watch_profiles()
    summary = {"users": 0, "deposits": 0, "outflows": 0, "baselines": 0, "errors": 0}
    conc = max(1, min(4, int(os.getenv("WALLET_WATCH_CONCURRENCY", "2"))))
    sem = asyncio.Semaphore(conc)

    async def _user(p: dict) -> None:
        uid = p["id"]
        summary["users"] += 1
        async with sem:
            try:
                actions = await watch_user_balances(uid)
                for a in actions.values():
                    if a == "deposit":
                        summary["deposits"] += 1
                    elif a == "outflow":
                        summary["outflows"] += 1
                    elif a == "baseline":
                        summary["baselines"] += 1
                    elif a == "error":
                        summary["errors"] += 1
            except Exception:
                logger.exception("[WalletWatch] user %s failed", uid[:8])
                summary["errors"] += 1

    await asyncio.gather(*[_user(p) for p in profiles])

    if summary["deposits"] or summary["outflows"] or summary["errors"]:
        logger.info("[WalletWatch] tick %s", summary)
    return summary