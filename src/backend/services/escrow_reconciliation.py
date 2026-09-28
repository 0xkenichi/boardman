"""
Escrow reconciliation — the periodic "did we lose or miscount funds?" check.

Gate item from docs/MAINNET_GOLIVE_CHECKLIST.md:

    sum(locked stakes in DB)  ==  escrow contract USDC balance

Drift means someone's stake is misaccounted: a lock that never landed on
chain, a payout that fired twice, a refund that didn't, a deposit credited
but never escrowed. This job NEVER mutates balances — it only reports.
Humans (via the incident runbook) decide what to do.

Run by the bot scheduler (``clawstation_escrow_reconciliation``) and safe to
call manually: ``await reconcile_escrow()``.
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Anything that could (or did) hold funds in escrow. Expected-held is computed
# from lock tx ids, so extra statuses here are harmless — they just widen the
# net against status-enum drift.
_DB_ACTIVE_STATUSES = (
    "accepted",
    "creator_locked",
    "locked",
    "playing",
    "submitted",
    "disputed",
)

# On-chain match states that hold funds (ClawEscrow MATCH_STATUS mapping)
_ONCHAIN_HOLDING = {"OPEN": 1, "LOCKED": 2, "DISPUTED": 2}

_TOLERANCE = Decimal("0.01")  # one cent — float noise only


def _expected_locked_from_row(row: dict) -> Decimal:
    """USDC expected to be in escrow for one challenge, per its audit trail.

    A side counts only if its lock actually reached Circle/chain (tx id
    recorded) — this is the ground truth of what was sent, independent of
    status-enum semantics.
    """
    stake = Decimal(str(row.get("stake_amount") or 0))
    held = Decimal("0")
    if row.get("creator_lock_tx_id"):
        held += stake
    if row.get("opponent_lock_tx_id"):
        held += stake
    return held


def _fetch_active_challenges(sb) -> list[dict]:
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select(
            "id, stake_amount, status, settlement_chain, "
            "creator_lock_tx_id, opponent_lock_tx_id"
        )
        .in_("status", list(_DB_ACTIVE_STATUSES))
        .limit(2000)
        .execute()
    )
    return result.data or []


def _onchain_held_usdc(status: str, stake_per_player: float) -> Decimal:
    sides = _ONCHAIN_HOLDING.get((status or "").upper(), 0)
    return Decimal(str(stake_per_player)) * Decimal(sides)


async def reconcile_escrow(
    chain_ids: Optional[list[str]] = None,
    *,
    sb=None,
    notify=None,
) -> dict:
    """Compare DB locked stakes vs on-chain escrow for every live chain.

    Returns a report dict; ``report["ok"]`` is False on ANY drift, missing
    data, or RPC failure. Fail-loud: a reconciliation that cannot run must
    never report healthy.
    """
    if sb is None:
        from gaming.src.backend.supabase_client import get_supabase

        sb = get_supabase()

    from gaming.src.backend.services.chains import (
        chain_has_escrow,
        default_chain_id,
        is_chain_enabled,
        list_chains,
        normalize_chain_id,
    )

    # ── DB side ──────────────────────────────────────────────────────────
    try:
        rows = _fetch_active_challenges(sb)
    except Exception as exc:
        logger.exception("[Reconcile] DB query failed — reporting unhealthy")
        return {"ok": False, "error": f"db_query_failed: {exc}", "chains": {}}

    by_chain: dict[str, list[dict]] = {}
    for row in rows:
        cid = normalize_chain_id(row.get("settlement_chain") or default_chain_id())
        by_chain.setdefault(cid, []).append(row)

    # ── Which chains to check ────────────────────────────────────────────
    if chain_ids:
        targets = [normalize_chain_id(c) for c in chain_ids]
    else:
        targets = [
            c["id"]
            for c in list_chains(include_disabled=True)
            if is_chain_enabled(c["id"]) and chain_has_escrow(c["id"])
        ]

    from backend.blockchain_layer import get_blockchain_layer_for_chain

    report: dict[str, Any] = {"ok": True, "chains": {}, "checked": 0}
    alerts: list[str] = []

    for cid in targets:
        chain_rows = by_chain.get(cid, [])
        db_total = sum(
            (_expected_locked_from_row(r) for r in chain_rows), Decimal("0")
        )
        entry: dict[str, Any] = {
            "db_expected_usdc": float(db_total),
            "challenges_checked": len(chain_rows),
            "drift": [],
        }

        try:
            bl = get_blockchain_layer_for_chain(cid)
        except Exception as exc:
            entry["error"] = f"blockchain_layer_init_failed: {exc}"
            entry["ok"] = False
            report["chains"][cid] = entry
            report["ok"] = False
            alerts.append(f"{cid}: BL init failed: {exc}")
            continue

        # ── Per-challenge: DB expectation vs on-chain match state ────────
        onchain_total = Decimal("0")
        for row in chain_rows:
            ch_id = row["id"]
            expected = _expected_locked_from_row(row)
            try:
                st = bl.get_match_status(ch_id)
            except Exception as exc:
                entry["drift"].append(
                    {"challenge": ch_id, "kind": "onchain_status_error", "error": str(exc)}
                )
                continue
            held = _onchain_held_usdc(st.get("status"), float(st.get("stake_per_player") or 0))
            onchain_total += held
            if abs(held - expected) > _TOLERANCE:
                entry["drift"].append(
                    {
                        "challenge": ch_id,
                        "kind": "held_mismatch",
                        "db_expected_usdc": float(expected),
                        "onchain_held_usdc": float(held),
                        "onchain_status": st.get("status"),
                    }
                )

        # ── Headline: contract balance vs DB total ───────────────────────
        try:
            contract_balance = Decimal(str(bl.get_contract_usdc_balance()))
        except Exception as exc:
            entry["error"] = f"contract_balance_failed: {exc}"
            entry["ok"] = False
            report["chains"][cid] = entry
            report["ok"] = False
            alerts.append(f"{cid}: contract balance read failed: {exc}")
            continue

        entry["onchain_active_usdc"] = float(onchain_total)
        entry["contract_balance_usdc"] = float(contract_balance)
        entry["balance_ok"] = abs(db_total - contract_balance) <= _TOLERANCE
        entry["ok"] = bool(entry["balance_ok"] and not entry["drift"])
        if not entry["ok"]:
            alerts.append(
                f"{cid}: DRIFT db={db_total} onchain_active={onchain_total} "
                f"contract={contract_balance} drifts={len(entry['drift'])}"
            )

        report["chains"][cid] = entry
        report["checked"] += len(chain_rows)
        if not entry["ok"]:
            report["ok"] = False

    report["skipped_chains_with_rows"] = sorted(
        set(by_chain) - set(targets)
    )
    report["alerts"] = alerts

    if not report["ok"]:
        logger.critical(
            "[Reconcile] ESCROW DRIFT DETECTED — %s",
            "; ".join(alerts) or "unknown",
        )
        if notify is not None:
            try:
                await notify("🚨 Escrow reconciliation FAILED:\n" + "\n".join(alerts))
            except Exception:
                logger.exception("[Reconcile] ops notify failed")
        else:
            ops_id = (os.getenv("BOARDMAN_OPS_TELEGRAM_ID") or "").strip()
            if ops_id:
                try:
                    from gaming.src.bot.utils.notify import notify_user

                    await notify_user(
                        ops_id, "🚨 Escrow reconciliation FAILED:\n" + "\n".join(alerts)
                    )
                except Exception:
                    logger.exception("[Reconcile] ops notify failed")
    else:
        logger.info(
            "[Reconcile] OK — %s chain(s), %s challenge(s), no drift",
            len(targets),
            report["checked"],
        )

    return report
