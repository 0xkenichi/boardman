"""Core messages → Telegram HTML + inline keyboards.

``render_dicts`` produces plain dicts (``{"text", "buttons": [{"label",
"callback"|"url"}]}``) that the fake adapter can inspect; ``to_aiogram``
turns one into what ``message.answer`` takes.
"""
from __future__ import annotations

import html
import re
from typing import Any, Optional

from gaming.src.channels.core.capabilities import TELEGRAM as CAPS
from gaming.src.channels.core.messages import MENU_ID, Choice, LinkButton, MediaRequest, Out, Text
from gaming.src.channels.core.render import plan_choice

LEGACY_MENU = "menu:main"  # today's main-menu callback in simple_ui

_MONO = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*([^*\n]+)\*")


class LimitViolation(AssertionError):
    pass


def to_html(body: str) -> str:
    s = html.escape(body or "", quote=False)
    s = _MONO.sub(r"<code>\1</code>", s)
    return _BOLD.sub(r"<b>\1</b>", s)


def _cb(option_id: str) -> str:
    return LEGACY_MENU if option_id == MENU_ID else option_id


def render(out: Out) -> list[dict[str, Any]]:
    if isinstance(out, (Text, MediaRequest)):
        return [{"text": to_html(out.body), "buttons": []}]
    if isinstance(out, LinkButton):
        return [{"text": to_html(out.body), "buttons": [{"label": out.label, "url": out.url}]}]
    if isinstance(out, Choice):
        plan = plan_choice(out, CAPS)
        if plan.kind == "numbered":
            return [{"text": to_html(plan.numbered_text), "buttons": []}]
        return [{"text": to_html(out.body),
                 "buttons": [{"label": o.label, "callback": _cb(o.id)} for o in plan.options]}]
    raise TypeError(f"cannot render {type(out).__name__}")


def render_dicts(outs: list[Out]) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    for o in outs:
        msgs.extend(render(o))
    return msgs


def validate(msg: dict[str, Any]) -> None:
    if not 0 < len(msg["text"]) <= CAPS.text_max:
        raise LimitViolation(f"text length {len(msg['text'])}")
    for b in msg["buttons"]:
        if "callback" in b and not 0 < len(b["callback"].encode("utf-8")) <= CAPS.button_id_max:
            raise LimitViolation(f"callback_data {b['callback']!r} over 64 bytes")
        if "url" in b and not str(b["url"]).startswith(("https://", "http://", "tg://")):
            raise LimitViolation("bad url button")


def to_aiogram(msg: dict[str, Any]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if not msg["buttons"]:
        return None
    rows = []
    for b in msg["buttons"]:
        if "url" in b:
            rows.append([InlineKeyboardButton(text=b["label"], url=b["url"])])
        else:
            rows.append([InlineKeyboardButton(text=b["label"], callback_data=b["callback"])])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_for_notify(outs: list[Out]) -> tuple[str, Optional[Any]]:
    """One DM for ``notify_user``: texts joined, the last keyboard kept."""
    msgs = render_dicts(outs)
    text = "\n\n".join(m["text"] for m in msgs)[: CAPS.text_max]
    markup = None
    for m in msgs:
        if m["buttons"]:
            markup = to_aiogram(m)
    return text, markup
