"""Chat messages after a passkey action is confirmed on chain (best effort).

Same wording and notices as the custodial lock (``flows/match.do_lock``), so
the other player sees nothing different. Also the "Is this your wallet?"
prompt a proven wallet setup or change sends to every chat of the player.
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


FLOW = "scw"  # src/channels/core/flows/scw.py answers these buttons


def confirm_options(nonce: str) -> list:
    from gaming.src.channels.core import ids
    from gaming.src.channels.core.messages import Option

    return [Option(ids.encode(FLOW, "y", nonce), "Yes, it's mine"), Option(ids.encode(FLOW, "n", nonce), "No")]


def confirm_text(kind: str, address: str, previous: str | None = None) -> str:
    if kind == "change":
        head = (f"*Change your passkey wallet?*\nFrom `{previous}`\nto `{address}`\n\n"
                "If you say yes, the new wallet starts working in 24 hours. Until then your old wallet stays "
                "active and new top-ups go to your Boardman play wallet.")
    else:
        head = f"*Is this your new wallet?*\n`{address}`"
    return (head + "\n\nOnly tap *Yes* if you just created it on the Boardman page and this address matches "
            "what the page shows. If it wasn't you, tap *No*: nothing changes.")


async def confirm_prompt(profile_id: str, *, kind: str, address: str, nonce: str,
                         previous: str | None = None) -> bool:
    """Ask "Is this your wallet? Yes / No" on every chat the player has. True if
    at least one chat got it (otherwise they can find it under *wallet*)."""
    from gaming.src.channels.core import notify

    try:
        sent = await notify.notify(
            str(profile_id),
            notify.Notice(kind="wallet_confirm", params={"address": address},
                          text=confirm_text(kind, address, previous), options=confirm_options(nonce)),
            all_channels=True,
        )
    except Exception:
        logger.warning("[self_custody] wallet confirmation prompt failed", exc_info=True)
        return False
    return any(d.ok for d in sent)

