"""Wallet / balance (Telegram flow 3)."""
from __future__ import annotations

import asyncio

from gaming.src.channels.core import ids
from gaming.src.channels.core.actions import wallet
from gaming.src.channels.core.messages import Option

NAME = "balance"
KEYWORDS = ("balance", "wallet", "bal")


def render(snap: wallet.WalletSnapshot) -> str:
    lines = ["*Wallet*", "", f"*Play balance: ${snap.spendable:,.2f}*", "Ready to stake. Every match uses this balance."]
    if snap.error and snap.spendable < 0.01:
        lines.append("Could not refresh the play balance right now.")
    if snap.address:
        lines += ["", "Play address:", f"`{snap.address}`"]
    if snap.other > 0.009 and snap.other_address:
        lines += ["", f"*${snap.other:,.2f} on another address*", f"`{snap.other_address}`",
                  "Not stakeable yet: send it to your play address above."]
    total = snap.spendable + snap.other
    if snap.ledger > 0.009 and snap.ledger > total + 0.009:
        lines += ["", f"Old account credit: ${snap.ledger:,.2f} (legacy ledger, not on-chain)"]
    if total < 0.01 and not snap.error:
        lines += ["", "Empty. Tap *Add money*: Naira or USDC both credit the same play balance."]
    streak = f"{snap.streak}" if snap.streak else "0"
    lines += ["", f"PLAY: *{snap.play_points:,}* · streak *{streak}* (best {snap.best_streak})",
              f"Tier: *{snap.tier}*"]
    return "\n".join(lines)


def _passkey_lines(profile_id: str) -> tuple[list[str], bool]:
    """Self-custody section (sync). ([], False) while the flag is off."""
    from gaming.src.backend.services.self_custody import config, routing

    if not config.enabled():
        return [], False
    acct = routing.account(profile_id)
    if not acct:
        return ["", "*Passkey wallet*: not set up. Hold your own money: approve every stake and "
                    "withdrawal with Face ID or fingerprint."], True
    from gaming.src.backend.services.self_custody import calls, chain

    try:
        bal = f"${calls.from_raw(chain.get_reader().usdc_balance(config.chain_settings()['usdc'], acct)):,.2f}"
    except Exception:
        bal = "unavailable right now"
    return ["", f"*Your passkey wallet: {bal}*", "You hold the keys; Boardman can't move your money.",
            f"`{acct}`"], False


async def start(ctx) -> None:
    ctx.st.clear()
    snap = await wallet.snapshot(ctx.profile_id)
    extra, offer_setup = await asyncio.to_thread(_passkey_lines, str(ctx.profile_id))
    opts = []
    if offer_setup:
        opts.append(Option(ids.encode(NAME, "setup"), "Set up passkey wallet"))
    if ctx.enabled("deposit"):
        opts.append(Option(ids.encode("deposit", "start"), "Add money"))
    if ctx.enabled("withdraw"):
        opts.append(Option(ids.encode("withdraw", "start"), "Withdraw"))
    opts.append(ctx.menu_option())
    ctx.choose(render(snap) + "\n".join([""] + extra if extra else []), opts)


async def on_button(ctx, act: str, arg: str) -> None:
    if act == "setup":
        from gaming.src.backend.services.self_custody import intents, setup

        try:
            url, _ = await asyncio.to_thread(setup.issue_link, str(ctx.profile_id), channel=ctx.channel,
                                             external_id=ctx.principal.external_id)
        except intents.IntentRefused as exc:
            ctx.choose(exc.message, [ctx.menu_option()])
            return
        ctx.link("*Set up your passkey wallet*\nOpen the secure page in your phone's browser and create a "
                 "passkey. Boardman never sees your keys. The link works once.", url, "Set up wallet")
        return
    await start(ctx)
