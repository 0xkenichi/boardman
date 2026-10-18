"""Conversation engine: one inbound event in, a list of channel-free messages out.

The engine loads the persisted per-user state, routes the event (button id,
numbered reply, keyword, or the active flow's next step), saves the state with
optimistic concurrency and returns what to say. Adapters render and send.

Routing order (CHANNELS_DESIGN §3.2 ``router.py``):
  1. button id ``v1|flow|act|arg`` → that flow (if enabled on this channel)
  2. a bare number answering the last choice → that option
  3. keywords: menu/help/hi, cancel, stop/start, and each flow's own words
  4. the active flow's text/media step
  5. otherwise the menu
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from gaming.src.channels import config
from gaming.src.channels.core import ids, state
from gaming.src.channels.core.capabilities import BY_NAME, TELEGRAM, Capabilities
from gaming.src.channels.core.events import Inbound
from gaming.src.channels.core.messages import MENU_ID, Choice, LinkButton, MediaRequest, Option, Out, Text
from gaming.src.channels.core.principal import Principal
from gaming.src.channels.core.render import plan_choice

logger = logging.getLogger(__name__)


@dataclass
class PendingNotice:
    profile_id: str
    notice: Any
    all_channels: bool = False
    exclude: Optional[tuple[str, str]] = None


@dataclass
class Ctx:
    principal: Principal
    st: state.ConversationState
    caps: Capabilities
    event: Optional[Inbound] = None
    out: list[Out] = field(default_factory=list)
    notices: list[PendingNotice] = field(default_factory=list)

    @property
    def channel(self) -> str:
        return self.principal.channel

    @property
    def profile_id(self) -> Optional[str]:
        return self.principal.profile_id

    def enabled(self, flow: str) -> bool:
        return config.flow_enabled(self.channel, flow)

    def say(self, body: str) -> None:
        self.out.append(Text(body))

    def choose(self, body: str, options: list[Option], button_label: str = "Choose") -> None:
        self.out.append(Choice(body, list(options), button_label))

    def link(self, body: str, url: str, label: str) -> None:
        self.out.append(LinkButton(body, url, label))

    def ask_media(self, body: str, kind: str = "image") -> None:
        self.out.append(MediaRequest(body, kind))

    def notify(self, profile_id: str, notice: Any, *, all_channels: bool = False,
               exclude_self: bool = False) -> None:
        excl = (self.channel, self.principal.external_id) if exclude_self else None
        self.notices.append(PendingNotice(profile_id, notice, all_channels, excl))

    def menu_option(self, label: str = "Menu") -> Option:
        return Option(MENU_ID, label)


def _flows() -> dict[str, Any]:
    from gaming.src.channels.core.flows import (
        approve,
        balance,
        challenge,
        deposit,
        link,
        match,
        menu,
        naira,
        onboarding,
        report,
        watch,
        withdraw,
    )

    return {
        "menu": menu,
        "onboarding": onboarding,
        "balance": balance,
        "deposit": deposit,
        "link": link,
        "withdraw": withdraw,
        "challenge": challenge,
        "match": match,
        "report": report,
        "watch": watch,
        "ap": approve,  # approval answers; the approved action checks its own flag
        "naira": naira,  # gated by the Paycrest flags, not CHANNELS_CORE_FLOWS
    }


ALWAYS = {"menu", "onboarding", "ap"}
KEYWORD_FLOWS = ("balance", "deposit", "withdraw", "naira", "challenge", "match", "report", "watch")


class Engine:
    def __init__(self, notifier: Any = None) -> None:
        self._notifier = notifier

    @property
    def notifier(self):
        if self._notifier is None:
            from gaming.src.channels.core.notify import default_service

            self._notifier = default_service()
        return self._notifier

    async def handle(self, event: Inbound, principal: Principal) -> list[Out]:
        caps = BY_NAME.get(event.channel, TELEGRAM)
        st = await asyncio.to_thread(state.load, event.channel, event.external_id)
        ctx = Ctx(principal, st, caps, event)
        try:
            await self._dispatch(ctx, event)
        except Exception:
            logger.exception("[channels] flow failed channel=%s", event.channel)
            ctx.out = [Text("Something went wrong on our side. Nothing was charged. Please try again.")]
            st.clear()
        self._remember_choice(ctx)
        try:
            await asyncio.to_thread(state.save, st)
        except state.StaleState:
            logger.info("[channels] concurrent update for one conversation; asked to resend")
            return [Text("We got two messages at once. Please send that again.")]
        for p in ctx.notices:
            try:
                await self.notifier.notify(p.profile_id, p.notice, all_channels=p.all_channels,
                                           exclude=p.exclude)
            except Exception:
                logger.warning("[channels] notice failed kind=%s", getattr(p.notice, "kind", "?"),
                               exc_info=True)
        return ctx.out

    # -- routing --

    def _allowed(self, ctx: Ctx, flow: str) -> bool:
        return flow in ALWAYS or ctx.enabled(flow)

    async def _dispatch(self, ctx: Ctx, ev: Inbound) -> None:
        flows = _flows()
        if ev.kind == "button":
            await self._button(ctx, ev.button_id, flows)
            return
        if ev.kind == "text":
            await self._text(ctx, (ev.text or "").strip(), flows)
            return
        if ev.kind == "media":
            mod = flows.get(ctx.st.flow or "")
            if mod is not None and hasattr(mod, "on_media") and self._allowed(ctx, ctx.st.flow or ""):
                await mod.on_media(ctx, ev.media)
                return
            if not ctx.principal.known:
                await flows["onboarding"].start(ctx)
                return
            if ev.media is not None and self._allowed(ctx, "report"):
                await flows["report"].bare_photo(ctx, ev.media)
                return
            ctx.say("Thanks. Photos are used for match reports, which are coming to this chat soon.")
            return
        ctx.say("I can read text, buttons and photos. Send *menu* to see what I can do.")

    async def _button(self, ctx: Ctx, raw: str, flows: dict[str, Any]) -> None:
        if raw == MENU_ID:
            await self._menu(ctx, flows)
            return
        dec = ids.decode(raw)
        if dec is None:
            ctx.say("That button is no longer active.")
            await self._menu(ctx, flows)
            return
        flow, act, arg = dec
        if flow == "nav" and act == "more":
            self._repage(ctx, arg)
            return
        if not ctx.principal.known and flow not in ("onboarding", "link"):
            await flows["onboarding"].start(ctx)
            return
        mod = flows.get(flow)
        if mod is None or not self._allowed(ctx, flow):
            ctx.say("That option is not available here yet.")
            await self._menu(ctx, flows)
            return
        await mod.on_button(ctx, act, arg)

    async def _text(self, ctx: Ctx, text: str, flows: dict[str, Any]) -> None:
        picked = self._numbered_pick(ctx, text)
        if picked is not None:
            await self._button(ctx, picked, flows)
            return
        words = text.split()
        word = words[0].lower().strip("!.") if words else ""
        if word in ("stop", "unsubscribe"):
            await flows["menu"].stop(ctx)
            return
        if word in ("start", "unstop", "subscribe") and ctx.channel != "telegram":
            await flows["menu"].resubscribe(ctx)
            return
        if word == "cancel":
            ctx.st.clear()
            ctx.say("Cancelled.")
            await self._menu(ctx, flows)
            return
        if word == "link" and self._allowed(ctx, "link"):
            await flows["link"].keyword(ctx, " ".join(words[1:]))
            return
        if word == "join" and len(words) > 1 and self._allowed(ctx, "match"):
            # wa.me/<number>?text=JOIN <code>: the deep link to an invite
            code = "".join(words[1:3])
            if not ctx.principal.known:
                ctx.st.data["_join"] = code  # picked up once onboarding finishes
                await flows["onboarding"].start(ctx)
                return
            ctx.st.clear()
            await flows["match"].join(ctx, code)
            return
        if not ctx.principal.known:
            await flows["onboarding"].on_text(ctx, text)
            return
        if word in ("menu", "hi", "hello", "hey", "help", "start"):
            ctx.st.clear()
            await self._menu(ctx, flows)
            return
        for name in KEYWORD_FLOWS:
            mod = flows[name]
            if word in mod.KEYWORDS and self._allowed(ctx, name):
                ctx.st.clear()
                await mod.start(ctx)
                return
        active = flows.get(ctx.st.flow or "")
        if active is not None and hasattr(active, "on_text") and self._allowed(ctx, ctx.st.flow or ""):
            await active.on_text(ctx, text)
            return
        ctx.say("Sorry, I didn't get that.")
        await self._menu(ctx, flows)

    async def _menu(self, ctx: Ctx, flows: dict[str, Any]) -> None:
        if not ctx.principal.known:
            await flows["onboarding"].start(ctx)
            return
        await flows["menu"].start(ctx)

    # -- choice memory: numbered replies and paging --

    @staticmethod
    def _remember_choice(ctx: Ctx) -> None:
        last = next((o for o in reversed(ctx.out) if isinstance(o, Choice)), None)
        if last is not None:
            ctx.st.data["_last_choice"] = {
                "body": last.body,
                "button_label": last.button_label,
                "options": [[o.id, o.label, o.description] for o in last.options],
            }
        elif ctx.out:
            ctx.st.data.pop("_last_choice", None)

    @staticmethod
    def _last_choice(ctx: Ctx) -> Optional[Choice]:
        raw = ctx.st.data.get("_last_choice")
        if not isinstance(raw, dict):
            return None
        opts = [Option(*o) for o in raw.get("options") or []]
        return Choice(raw.get("body") or "", opts, raw.get("button_label") or "Choose")

    def _numbered_pick(self, ctx: Ctx, text: str) -> Optional[str]:
        if not text.isdigit():
            return None
        last = self._last_choice(ctx)
        if last is None:
            return None
        n = int(text)
        if 1 <= n <= len(last.options):
            return last.options[n - 1].id
        return None

    def _repage(self, ctx: Ctx, arg: str) -> None:
        last = self._last_choice(ctx)
        if last is None:
            ctx.say("That list has expired. Send *menu* to start again.")
            return
        try:
            last.page = int(arg)
        except ValueError:
            last.page = 0
        ctx.out.append(last)


_default: Optional[Engine] = None


def default_engine() -> Engine:
    global _default
    if _default is None:
        _default = Engine()
    return _default


def preview(choice: Choice, channel: str) -> str:
    """Debug helper: how a choice degrades on ``channel``."""
    plan = plan_choice(choice, BY_NAME[channel])
    return f"{plan.kind}:{len(plan.options)}"
