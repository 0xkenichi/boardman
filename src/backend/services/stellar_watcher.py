"""
Stellar Horizon watcher — detect USDC deposits to ops account by memo.

When a payment memo matches a Boardman top-up ref (BM + RMXXXX or RM-XXXX),
mark the top-up as rail_paid and notify admins + player.

Does NOT auto-send Arc USDC (still needs float / ops /credit_topup) unless
STELLAR_AUTO_MARK_ONLY=0 and future float credit is wired.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Circle USDC on Stellar (public network issuer — well known)
# Testnet may use a different issuer; override with STELLAR_USDC_ISSUER
DEFAULT_USDC_ISSUER_PUBLIC = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"


def _state_path() -> Path:
    raw = os.getenv("STELLAR_WATCH_STATE_FILE") or os.path.expanduser(
        "~/.rematch/stellar_watch_state.json"
    )
    return Path(raw)


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"seen_tx": [], "cursor": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_tx": [], "cursor": None}


def _save_state(state: dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Cap seen list
    seen = list(state.get("seen_tx") or [])[-500:]
    state["seen_tx"] = seen
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def stellar_configured() -> bool:
    from gaming.src.backend.services.funding_rails import ops_deposit_address

    return bool(ops_deposit_address("stellar"))


def _horizon_get(path: str, params: Optional[dict] = None) -> dict[str, Any]:
    from gaming.src.backend.services.funding_rails import stellar_horizon_url

    base = stellar_horizon_url().rstrip("/")
    q = urllib.parse.urlencode(params or {})
    url = f"{base}{path}" + (f"?{q}" if q else "")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Boardman/1.0 (+https://boardman.playingsidequest.fun)",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _memo_to_ref(memo: str) -> Optional[str]:
    """Map Stellar memo → RM-XXXX top-up ref."""
    raw = (memo or "").strip().upper()
    if not raw:
        return None
    # BM + RMXXXX or BMRMXXXX or RM-XXXX
    raw = raw.replace(" ", "")
    m = re.search(r"(RM-?[A-Z0-9]{4,12})", raw)
    if m:
        ref = m.group(1)
        if not ref.startswith("RM-"):
            ref = "RM-" + ref[2:] if ref.startswith("RM") else f"RM-{ref}"
        if ref.startswith("RM") and not ref.startswith("RM-"):
            ref = "RM-" + ref[2:]
        return ref
    # Prefix BM + body without RM-
    prefix = (os.getenv("BOARDMAN_STELLAR_MEMO_PREFIX") or "BM").strip().upper()
    if raw.startswith(prefix) and len(raw) > len(prefix):
        body = raw[len(prefix) :]
        if body.startswith("RM"):
            body = body[2:].lstrip("-")
        return f"RM-{body}" if body else None
    return None


def _payment_amount_usdc(p: dict[str, Any]) -> Optional[Decimal]:
    """Extract USDC amount from a Horizon payment record."""
    asset_type = (p.get("asset_type") or "").lower()
    asset_code = (p.get("asset_code") or "").upper()
    if asset_type == "native":
        return None  # XLM — ignore
    if asset_code and asset_code not in ("USDC", "USDCX"):
        # Still accept if env says so
        if os.getenv("STELLAR_ACCEPT_ANY_ASSET", "").lower() not in ("1", "true", "yes"):
            return None
    try:
        return Decimal(str(p.get("amount") or "0"))
    except Exception:
        return None


def fetch_recent_payments_to_ops(limit: int = 50) -> list[dict[str, Any]]:
    from gaming.src.backend.services.funding_rails import ops_deposit_address

    account = ops_deposit_address("stellar")
    if not account:
        return []
    data = _horizon_get(
        f"/accounts/{urllib.parse.quote(account)}/payments",
        {"order": "desc", "limit": str(limit)},
    )
    records = (data.get("_embedded") or {}).get("records") or []
    return records


def process_stellar_payments() -> dict[str, Any]:
    """
    Poll Horizon, match memos to open top-ups, mark rail_paid.

    Returns stats for logging.
    """
    if not stellar_configured():
        return {"skipped": True, "reason": "no BOARDMAN_OPS_USDC_STELLAR"}

    from gaming.src.backend.services.fiat_topup import get_topup, update_topup

    state = _load_state()
    seen = set(state.get("seen_tx") or [])
    found = 0
    matched = 0
    errors = 0

    try:
        payments = fetch_recent_payments_to_ops(40)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        logger.warning("[StellarWatch] Horizon HTTP %s: %s", exc.code, body)
        return {"error": f"horizon_{exc.code}"}
    except Exception as exc:
        logger.warning("[StellarWatch] fetch failed: %s", exc)
        return {"error": str(exc)[:120]}

    for p in payments:
        # Only inbound to our account
        if (p.get("type") or "") not in ("payment", "path_payment_strict_receive", "path_payment_strict_send"):
            continue
        tx_hash = p.get("transaction_hash") or p.get("id") or ""
        if not tx_hash or tx_hash in seen:
            continue
        seen.add(tx_hash)
        found += 1

        # Memo is on the transaction, not always on payment — fetch tx if needed
        memo = ""
        try:
            if p.get("transaction_hash"):
                tx = _horizon_get(f"/transactions/{p['transaction_hash']}")
                memo = (tx.get("memo") or "") if tx.get("memo_type") in ("text", "id", None) else ""
                if tx.get("memo_type") == "id" and tx.get("memo"):
                    memo = str(tx.get("memo"))
        except Exception:
            logger.debug("[StellarWatch] tx fetch failed", exc_info=True)

        ref = _memo_to_ref(memo)
        amount = _payment_amount_usdc(p)
        if not ref:
            continue
        row = get_topup(ref)
        if not row:
            logger.info("[StellarWatch] payment memo=%s no topup ref=%s", memo, ref)
            continue
        if row.get("status") in ("credited", "rejected", "cancelled", "rail_paid", "paystack_paid"):
            continue
        if (row.get("provider") or "").lower() not in ("stellar", "bank", "paystack", ""):
            # Allow stellar-only or any awaiting
            if (row.get("provider") or "").lower() != "stellar":
                pass

        amt_f = float(amount) if amount is not None else 0.0
        update_topup(
            ref,
            status="rail_paid",
            provider="stellar",
            proof_text=f"stellar_tx={tx_hash} amount={amt_f} memo={memo}",
            credit_usdc=amt_f if amt_f > 0 else row.get("credit_usdc"),
            gross_usd=amt_f if amt_f > 0 else row.get("gross_usd"),
            usdc_tx=tx_hash,
        )
        matched += 1
        logger.info(
            "[StellarWatch] matched ref=%s amount=%s tx=%s",
            ref,
            amt_f,
            tx_hash[:16],
        )
        # Fire-and-forget notifications via sync helper stored for async job
        try:
            _notify_rail_paid(ref, amt_f, tx_hash, "stellar")
        except Exception:
            errors += 1
            logger.exception("[StellarWatch] notify failed ref=%s", ref)

    state["seen_tx"] = list(seen)
    state["last_poll"] = time.time()
    _save_state(state)
    return {"found": found, "matched": matched, "errors": errors}


def _notify_rail_paid(ref: str, amount: float, tx_hash: str, rail: str) -> None:
    """Best-effort admin + user notify (sync path uses asyncio if loop running)."""
    import asyncio

    async def _go() -> None:
        from gaming.src.backend.services.fiat_topup import get_topup
        from gaming.src.backend.services.safety import admin_telegram_ids
        from gaming.src.bot.utils.notify import notify_user

        row = get_topup(ref) or {}
        tid = int(row.get("telegram_id") or 0)
        play = row.get("play_address") or "—"
        admin_msg = (
            f"⭐ <b>{rail.title()} deposit detected</b>\n"
            f"Ref <code>{ref}</code>\n"
            f"Amount ~${amount:,.2f} USDC\n"
            f"Tx <code>{tx_hash[:20]}…</code>\n"
            f"Play: <code>{play}</code>\n\n"
            f"Send USDC to play address on Arc, then:\n"
            f"<code>/credit_topup {ref}</code>"
        )
        for aid in admin_telegram_ids():
            try:
                await notify_user(aid, admin_msg)
            except Exception:
                pass
        if tid:
            try:
                await notify_user(
                    tid,
                    f"✅ We saw your USDC deposit for <code>{ref}</code> "
                    f"(~${amount:,.2f}).\n"
                    f"Play balance credit is next — usually within ops window.\n"
                    f"You'll get another ping when it's ready.",
                )
            except Exception:
                pass

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_go())
        else:
            loop.run_until_complete(_go())
    except RuntimeError:
        asyncio.run(_go())


async def watch_stellar_deposits() -> dict[str, Any]:
    """Async job entrypoint for the scheduler."""
    if os.getenv("STELLAR_WATCH_ENABLED", "1").lower() in ("0", "false", "no", "off"):
        return {"skipped": True}
    if not stellar_configured():
        return {"skipped": True, "reason": "not_configured"}
    return await asyncio_to_thread(process_stellar_payments)


async def asyncio_to_thread(fn, *args, **kwargs):
    import asyncio

    return await asyncio.to_thread(fn, *args, **kwargs)
