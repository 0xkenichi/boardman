"""Degrade rule for a ``Choice`` (CHANNELS_DESIGN §3.2).

n ≤ max_buttons → buttons; else the channel has lists → a list (paged with a
"More…" row past the row limit); else numbered text ("Reply 1–n"). Numbered
text also works on every channel: typing ``2`` picks option 2.
"""
from __future__ import annotations

from dataclasses import dataclass

from gaming.src.channels.core import ids
from gaming.src.channels.core.capabilities import Capabilities
from gaming.src.channels.core.messages import Choice, Option

MORE_LABEL = "More…"


def fit(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def more_id(page: int) -> str:
    return ids.encode("nav", "more", str(page))


@dataclass
class ChoicePlan:
    kind: str  # buttons | list | numbered
    options: list[Option]
    numbered_text: str = ""
    page: int = 0
    has_more: bool = False


def numbered(choice: Choice) -> str:
    lines = [choice.body, ""]
    for i, o in enumerate(choice.options, 1):
        extra = f" ({o.description})" if o.description else ""
        lines.append(f"{i}. {o.label}{extra}")
    lines.append("")
    lines.append(f"Reply with a number (1-{len(choice.options)}).")
    return "\n".join(lines)


def plan_choice(choice: Choice, caps: Capabilities) -> ChoicePlan:
    opts = choice.options
    n = len(opts)
    if 0 < n <= caps.max_buttons:
        fitted = [Option(o.id, fit(o.label, caps.button_title_max), "") for o in opts]
        return ChoicePlan("buttons", fitted)
    if caps.max_list_rows > 0 and n > 0:
        per_page = caps.max_list_rows if n <= caps.max_list_rows else caps.max_list_rows - 1
        pages = max(1, -(-n // per_page))
        page = min(max(choice.page, 0), pages - 1)
        chunk = opts[page * per_page:(page + 1) * per_page]
        rows = [
            Option(o.id, fit(o.label, caps.list_row_title_max), fit(o.description, caps.list_row_desc_max))
            for o in chunk
        ]
        has_more = page < pages - 1
        if has_more:
            rows.append(Option(more_id(page + 1), MORE_LABEL, f"Page {page + 2} of {pages}"))
        return ChoicePlan("list", rows, page=page, has_more=has_more)
    return ChoicePlan("numbered", list(opts), numbered_text=numbered(choice))
