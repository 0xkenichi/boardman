"""Wallet / balance (Telegram flow 3)."""
from __future__ import annotations

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


async def start(ctx) -> None:
    ctx.st.clear()
    snap = await wallet.snapshot(ctx.profile_id)
    opts = []
    if ctx.enabled("deposit"):
        opts.append(Option(ids.encode("deposit", "start"), "Add money"))
    if ctx.enabled("withdraw"):
        opts.append(Option(ids.encode("withdraw", "start"), "Withdraw"))
    opts.append(ctx.menu_option())
    ctx.choose(render(snap), opts)


async def on_button(ctx, act: str, arg: str) -> None:
    await start(ctx)
