"""
Match cancel rules for Rematch.

- open / accepted (no on-chain locks): free cancel by participant
- creator_locked (creator has on-chain lock): cancel_match() refunds
- locked / playing: mutual cancel only (propose → confirm)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge
from gaming.src.backend.services.clawstation_escrow import EscrowError, cancel_match
from gaming.src.backend.services.match_codes import display_code
from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _sb():
    return get_supabase()


def _load(challenge_id: str) -> Optional[dict]:
    r = (
        _sb()
        .schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .limit(1)
        .execute()
    )
    row = (r.data or [None])[0]
    return normalize_challenge(row) if row else None


def _update(challenge_id: str, data: dict) -> None:
    _sb().schema("gaming").table("challenges").update(denormalize_challenge(data)).eq(
        "id", challenge_id
    ).execute()


def _has_onchain_lock(ch: dict) -> bool:
    return bool(ch.get("creator_lock_tx_id") or ch.get("opponent_lock_tx_id") or ch.get("creator_lock_tx_hash"))


def can_cancel(profile_id: str, ch: dict) -> dict[str, Any]:
    """Return {mode, ok, reason}."""
    status = (ch.get("status") or "").lower()
    is_creator = profile_id == ch.get("creator_id")
    is_opp = profile_id == ch.get("opponent_id")
    if not is_creator and not is_opp:
        return {"ok": False, "mode": "none", "reason": "Not your match."}

    if status in ("resolved", "cancelled", "expired", "declined"):
        return {"ok": False, "mode": "none", "reason": f"Match already {status}."}

    if status in ("open", "accepted") and not _has_onchain_lock(ch):
        return {"ok": True, "mode": "free", "reason": "Cancel without refund needed."}

    if status == "creator_locked" or (
        _has_onchain_lock(ch) and not ch.get("opponent_lock_tx_id") and status != "locked"
    ):
        if is_creator or is_opp:
            return {
                "ok": True,
                "mode": "refund",
                "reason": "Cancel and refund locked stake(s) on-chain.",
            }

    if status in ("locked", "playing", "submitted", "disputed"):
        proposed = (ch.get("admin_resolution_note") or "") or ""
        if proposed.startswith("cancel_proposed:"):
            proposer = proposed.split(":", 2)[1] if ":" in proposed else ""
            if proposer and proposer != profile_id:
                return {
                    "ok": True,
                    "mode": "confirm",
                    "reason": "Other player proposed cancel — confirm to refund both.",
                    "proposer_id": proposer,
                }
            if proposer == profile_id:
                return {
                    "ok": False,
                    "mode": "waiting",
                    "reason": "Waiting for opponent to confirm cancel.",
                }
        return {
            "ok": True,
            "mode": "propose",
            "reason": "Both must agree after funds are locked.",
        }

    return {"ok": False, "mode": "none", "reason": "Cannot cancel in this state."}


async def execute_cancel(profile_id: str, challenge_id: str) -> dict[str, Any]:
    ch = _load(challenge_id)
    if not ch:
        raise ValueError("Match not found")

    info = can_cancel(profile_id, ch)
    if not info.get("ok") and info.get("mode") not in ("propose", "confirm"):
        if info.get("mode") == "waiting":
            return {"success": False, **info}
        raise ValueError(info.get("reason") or "Cannot cancel")

    mode = info["mode"]
    code = display_code(ch)

    if mode == "free":
        _update(challenge_id, {"status": "cancelled"})
        return {
            "success": True,
            "mode": "free",
            "code": code,
            "message": f"Match {code} cancelled. No funds were locked.",
        }

    if mode == "refund":
        if not _has_onchain_lock(ch):
            _update(challenge_id, {"status": "cancelled"})
            return {
                "success": True,
                "mode": "free",
                "code": code,
                "message": f"Match {code} cancelled.",
            }
        try:
            result = await cancel_match(challenge_id)
            return {
                "success": True,
                "mode": "refund",
                "code": code,
                "tx_hash": result.get("tx_hash"),
                "message": f"Match {code} cancelled. Locked USDC refunded on-chain.",
            }
        except EscrowError as exc:
            # Never mark cancelled in DB if funds may still be locked on-chain
            logger.exception("[Cancel] on-chain refund failed for %s", challenge_id)
            raise ValueError(
                f"Refund failed: {exc}\n"
                "Funds stay locked until the resolver wallet cancels on-chain. "
                "Ops: set a real ADMIN_PRIVATE_KEY (escrow resolver) with Arc gas/USDC."
            ) from exc

    if mode == "propose":
        note = f"cancel_proposed:{profile_id}:{datetime.now(timezone.utc).isoformat()}"
        try:
            _update(challenge_id, {"admin_resolution_note": note})
        except Exception as exc:
            logger.warning("[Cancel] propose note failed: %s", exc)
            raise ValueError("Could not store cancel proposal — try again") from exc
        return {
            "success": True,
            "mode": "propose",
            "code": code,
            "message": (
                f"Cancel proposed on {code}. Opponent must confirm.\n"
                f"If they refuse, the match continues."
            ),
        }

    if mode == "confirm":
        try:
            result = await cancel_match(challenge_id)
            try:
                _update(challenge_id, {"admin_resolution_note": "cancel_mutual_ok"})
            except Exception:
                pass
            return {
                "success": True,
                "mode": "confirm",
                "code": code,
                "tx_hash": result.get("tx_hash"),
                "message": f"Mutual cancel confirmed. Match {code} refunded.",
            }
        except EscrowError as exc:
            # Import/config failures should not leave users stuck if refund is impossible
            err = str(exc)
            logger.exception("[Cancel] mutual refund failed: %s", exc)
            if "ADMIN_PRIVATE_KEY" in err or "import" in err.lower() or "not configured" in err.lower():
                raise ValueError(
                    f"Refund failed: {exc}. "
                    "Ops: set ADMIN_PRIVATE_KEY (resolver) funded on Arc, "
                    "then retry Confirm cancel."
                ) from exc
            raise ValueError(f"Refund failed: {exc}") from exc

    raise ValueError(info.get("reason") or "Cannot cancel")
