"""Per-channel limits the renderers must respect (CHANNELS_DESIGN §3.2).

WhatsApp numbers are from Meta's Cloud API docs as remembered [?]: 3 reply
buttons (title ≤20, id ≤256), one list of ≤10 rows in ≤10 sections (row
title ≤24, description ≤72, button ≤20), one ``cta_url`` (label ≤20),
interactive body ≤1024, text ≤4096. Check before launch.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capabilities:
    name: str
    max_buttons: int
    button_title_max: int
    button_id_max: int
    max_list_rows: int  # 0: no list primitive
    max_list_sections: int
    list_row_title_max: int
    list_row_desc_max: int
    list_button_max: int
    max_url_buttons: int
    text_max: int
    interactive_body_max: int
    markup: str  # html | wa | plain
    can_edit: bool
    proactive: str  # any | window | customer_only


TELEGRAM = Capabilities(
    name="telegram",
    max_buttons=12,
    button_title_max=64,
    button_id_max=64,  # callback_data bytes
    max_list_rows=0,
    max_list_sections=0,
    list_row_title_max=0,
    list_row_desc_max=0,
    list_button_max=0,
    max_url_buttons=8,
    text_max=4096,
    interactive_body_max=4096,
    markup="html",
    can_edit=True,
    proactive="any",
)

WHATSAPP = Capabilities(
    name="whatsapp",
    max_buttons=3,
    button_title_max=20,
    button_id_max=256,
    max_list_rows=10,
    max_list_sections=10,
    list_row_title_max=24,
    list_row_desc_max=72,
    list_button_max=20,
    max_url_buttons=1,
    text_max=4096,
    interactive_body_max=1024,
    markup="wa",
    can_edit=False,
    proactive="window",
)

SMS = Capabilities(
    name="sms",
    max_buttons=0,
    button_title_max=0,
    button_id_max=0,
    max_list_rows=0,
    max_list_sections=0,
    list_row_title_max=0,
    list_row_desc_max=0,
    list_button_max=0,
    max_url_buttons=0,
    text_max=1600,
    interactive_body_max=1600,
    markup="plain",
    can_edit=False,
    proactive="any",
)

BY_NAME = {c.name: c for c in (TELEGRAM, WHATSAPP, SMS)}
