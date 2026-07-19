"""Stub handler for photo proof-of-play uploads."""
from __future__ import annotations

import logging

from aiogram import F, Router, types

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.photo | F.document)
async def cmd_proof_photo(message: types.Message) -> None:
    """Persist a photo file_id with a placeholder status.

    Match screenshots for score AI use caption ``/submit_score …`` and are
    handled by submit_score — skip those here.
    """
    caption = message.caption or ""
    if "/submit_score" in caption.lower():
        return  # submit_score media handler owns this

    # Don't eat bare images — submit_score already hints; only store if caption present
    if not caption.strip():
        return
    if not message.photo and not (
        message.document and (message.document.mime_type or "").startswith("image/")
    ):
        return

    file_id = message.photo[-1].file_id
    challenge_id = caption.split()[0] if caption else None

    sb = get_supabase()
    try:
        sb.schema("gaming").table("proof_of_play_receipts").insert(
            {
                "tx_hash": f"telegram:{file_id}",
                "chain": "telegram",
                "verification_data": {
                    "file_id": file_id,
                    "challenge_id": challenge_id,
                    "caption": caption,
                    "status": "pending_review",
                },
            }
        ).execute()
    except Exception as exc:
        logger.exception("[Proof] Failed to persist photo %s", file_id)
        await message.answer(f"❌ Could not save proof: {exc}")
        return

    await message.answer("📸 Proof received and queued for review.")
