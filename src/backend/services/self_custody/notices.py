"""Chat messages after a passkey action is confirmed on chain (best effort).

Same wording and notices as the custodial lock (``flows/match.do_lock``), so
the other player sees nothing different.
"""
from __future__ import annotations

import asyncio
import logging

from gaming.src.backend.services.self_custody import calls as C
from gaming.src.backend.services.self_custody import store

logger = logging.getLogger(__name__)


async def _tell(profile_id: str, html: str, notice) -> None:
    from gaming.src.channels.core.flows import matchkit as mk

    await mk.notify_legacy(str(profile_id), html, notice)


def _plain(text: str):
    from gaming.src.channels.core.notify import Notice

    return Notice(kind="wallet_update", text=text)


async def confirmed(intent_id: str) -> None:
    try:
        await _confirmed(intent_id)
    except Exception:
        logger.warning("[self_custody] confirmation notice failed", exc_info=True)


async def _confirmed(intent_id: str) -> None:
    from gaming.src.channels.core import match_notices
    from gaming.src.channels.core.actions import matches as svc
    from gaming.src.channels.core.flows import matchkit as mk

    it = await asyncio.to_thread(store.get, intent_id)
    if not it:
        return
    amt = f"${C.from_raw(it['amount_micro']):,.2f}"
    if it["action"] == "withdraw":
        await _tell(it["profile_id"], f"✅ Sent <b>{amt} USDC</b> from your wallet to <code>{it['to_address']}</code>.",
                    _plain(f"Sent *{amt} USDC* from your wallet to `{it['to_address']}`."))
        return
    ch = await mk.load(str(it["challenge_id"]))
    if not ch:
        return
    code = svc.code_of(ch)
    if it["action"] == "lock_create":
        await _tell(it["profile_id"], f"🔐 Stake locked on <code>{code}</code> with your passkey. "
                                      "Waiting for your opponent to lock.",
                    _plain(f"Stake locked on `{code}` with your passkey. Waiting for your opponent to lock."))
        if ch.get("opponent_id"):
            await mk.notify_legacy(
                str(ch["opponent_id"]),
                f"🔐 Challenger locked their stake on <code>{code}</code>.\nYour turn: <b>Lock my stake</b>.",
                match_notices.opponent_locked(ch),
                tg_buttons=mk.tg_match_menu(ch, str(ch["opponent_id"])),
            )
        return
    for pid in (ch.get("creator_id"), ch.get("opponent_id")):
        if pid:
            await mk.notify_legacy(
                str(pid),
                "🎮 Both stakes locked!\n\nPlay the match, then <b>Submit result</b> with a photo.",
                match_notices.match_ready(ch),
                tg_buttons=mk.tg_match_menu(ch, str(pid)),
            )


async def wallet_linked(profile_id: str, address: str) -> None:
    try:
        await _tell(profile_id,
                    f"🔑 Your passkey wallet is linked: <code>{address}</code>\n"
                    "You hold the keys; Boardman can't move your money. "
                    "If this wasn't you, contact support now.",
                    _plain(f"Your passkey wallet is linked: `{address}`\nYou hold the keys; Boardman can't move "
                           "your money. If this wasn't you, contact support now."))
    except Exception:
        logger.warning("[self_custody] wallet-linked notice failed", exc_info=True)
