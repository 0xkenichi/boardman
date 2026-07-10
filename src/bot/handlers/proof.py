"""Stub handler for photo proof-of-play uploads."""
from __future__ import annotations

import logging

from aiogram import F, Router, types

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.photo)
async def cmd_proof_photo(message: types.Message) -> None:
    """Persist a photo file_id with a placeholder status.

    Full AI verification is out of scope; the file_id is stored in
    ``gaming.proof_of_play_receipts`` so it can be reviewed later.
    """
    if not message.photo:
        return

    file_id = message.photo[-1].file_id
    caption = message.caption or ""
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
