"""Core messages → Cloud API message objects (CHANNELS_DESIGN §4.2).

Each returned dict is the body of ``POST /{phone-number-id}/messages`` minus
``messaging_product``, ``recipient_type`` and ``to`` (the client adds them).
``validate`` enforces WhatsApp's limits; the fake adapter runs it on every
message so a renderer bug fails a test, not a send.
"""
from __future__ import annotations

from typing import Any

from gaming.src.channels.core.capabilities import WHATSAPP as CAPS
from gaming.src.channels.core.messages import MENU_ID, Choice, LinkButton, MediaRequest, Out, Text
from gaming.src.channels.core.render import fit, plan_choice


class LimitViolation(AssertionError):
    pass


def _split(body: str, limit: int) -> list[str]:
    body = body or " "
    out = []
    while len(body) > limit:
        cut = body.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        out.append(body[:cut])
        body = body[cut:].lstrip("\n")
    out.append(body)
    return out


def _text(body: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"body": part, "preview_url": False}} for part in _split(body, CAPS.text_max)]


def _interactive_body(body: str) -> tuple[list[dict[str, Any]], str]:
    """Long bodies go out as text first; the interactive gets a short prompt."""
    if len(body) <= CAPS.interactive_body_max:
        return [], body
    return _text(body), "Choose one:"


def render(out: Out) -> list[dict[str, Any]]:
    if isinstance(out, Text):
        return _text(out.body)
    if isinstance(out, MediaRequest):
        return _text(out.body)
    if isinstance(out, LinkButton):
        pre, body = _interactive_body(out.body)
        return pre + [{
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body},
                "action": {
                    "name": "cta_url",
                    "parameters": {"display_text": fit(out.label, CAPS.button_title_max), "url": out.url},
                },
            },
        }]
    if isinstance(out, Choice):
        plan = plan_choice(out, CAPS)
        if plan.kind == "numbered":
            return _text(plan.numbered_text)
        pre, body = _interactive_body(out.body)
        if plan.kind == "buttons":
            return pre + [{
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {"buttons": [
                        {"type": "reply", "reply": {"id": o.id, "title": o.label}} for o in plan.options
                    ]},
                },
            }]
        return pre + [{
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": fit(out.button_label or "Choose", CAPS.list_button_max),
                    "sections": [{
                        "title": fit("Options", 24),
                        "rows": [
                            {"id": o.id, "title": o.label, **({"description": o.description} if o.description else {})}
                            for o in plan.options
                        ],
                    }],
                },
            },
        }]
    raise TypeError(f"cannot render {type(out).__name__}")


def render_all(outs: list[Out]) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    for o in outs:
        msgs.extend(render(o))
    return msgs


# ── limits ───────────────────────────────────────────────────────────────────


def _need(cond: bool, what: str) -> None:
    if not cond:
        raise LimitViolation(what)


def validate(msg: dict[str, Any]) -> None:
    t = msg.get("type")
    if t == "text":
        body = msg["text"]["body"]
        _need(0 < len(body) <= CAPS.text_max, f"text length {len(body)}")
        _need("<b>" not in body and "<code>" not in body and "</" not in body, "HTML in WhatsApp text")
        return
    if t == "template":
        _need(bool(msg["template"].get("name")), "template name")
        return
    _need(t == "interactive", f"unknown type {t}")
    it = msg["interactive"]
    body = it["body"]["text"]
    _need(0 < len(body) <= CAPS.interactive_body_max, f"interactive body length {len(body)}")
    _need("</" not in body, "HTML in WhatsApp body")
    kind = it["type"]
    if kind == "button":
        btns = it["action"]["buttons"]
        _need(1 <= len(btns) <= CAPS.max_buttons, f"{len(btns)} reply buttons")
        ids = [b["reply"]["id"] for b in btns]
        _need(len(set(ids)) == len(ids), "duplicate button ids")
        for b in btns:
            _need(len(b["reply"]["title"]) <= CAPS.button_title_max, f"button title {b['reply']['title']!r}")
            _need(0 < len(b["reply"]["id"]) <= CAPS.button_id_max, "button id length")
    elif kind == "list":
        act = it["action"]
        _need(len(act["button"]) <= CAPS.list_button_max, "list button label")
        sections = act["sections"]
        _need(1 <= len(sections) <= CAPS.max_list_sections, f"{len(sections)} sections")
        rows = [r for s in sections for r in s["rows"]]
        _need(1 <= len(rows) <= CAPS.max_list_rows, f"{len(rows)} list rows")
        _need(len({r['id'] for r in rows}) == len(rows), "duplicate row ids")
        for r in rows:
            _need(len(r["title"]) <= CAPS.list_row_title_max, f"row title {r['title']!r}")
            _need(len(r.get("description", "")) <= CAPS.list_row_desc_max, "row description")
            _need(0 < len(r["id"]) <= 200, "row id length")
    elif kind == "cta_url":
        p = it["action"]["parameters"]
        _need(len(p["display_text"]) <= CAPS.button_title_max, "cta label")
        _need(str(p["url"]).startswith("https://"), "cta url must be https")
    else:
        raise LimitViolation(f"interactive type {kind}")


def menu_id() -> str:
    return MENU_ID
