"""Watch & bet: a link to the website arena, never betting in the chat.

Spectator betting stays on the web on WhatsApp (founder decision; Meta
policy and the IP geo check apply there). Telegram keeps its own entry points.
"""
from __future__ import annotations

from gaming.src.channels import config

NAME = "watch"
KEYWORDS = ("watch", "bet", "bets", "arena", "spectate")


def arena_url() -> str:
    return f"{config.site_url()}/arena"


async def start(ctx) -> None:
    ctx.st.clear()
    ctx.link(
        "*Watch & bet*\nLive matches and spectator bets are on the Boardman website. "
        "Bets are placed and confirmed there, not in this chat.",
        arena_url(),
        "Open the arena",
    )


async def on_button(ctx, act: str, arg: str) -> None:
    await start(ctx)
