"""Utility message templates for notices outside the 24 h window
(CHANNELS_DESIGN §4.3). Submit these exactly as written
(docs/channels/WHATSAPP_SETUP.md lists them; a test keeps the two in sync).

Rules: utility category, English (``en``) first, no promotion, no emoji
banter. ``{{n}}`` are body variables in the order of ``params``. Quick-reply
buttons are fixed at approval; their payloads are set per send [?].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

LANGUAGE = "en"


@dataclass(frozen=True)
class Template:
    name: str
    body: str
    params: tuple[str, ...]
    buttons: tuple[str, ...] = field(default_factory=tuple)
    category: str = "UTILITY"
    language: str = LANGUAGE


ACCOUNT_LINKED = Template(
    "account_linked",
    "Security notice: {{1}} was linked to your Boardman account. If this was not you, contact Boardman support right away.",
    ("identity",),
)
CHALLENGE_RECEIVED = Template(
    "challenge_received",
    "{{1}} challenged you to {{2}} for {{3}} USDC. The challenge expires in {{4}}.",
    ("challenger", "game", "stake", "expires_in"),
    ("Accept", "Decline"),
)
CHALLENGE_ANSWERED = Template(
    "challenge_answered",
    "{{1}} {{2}} your {{3}} challenge.",
    ("opponent", "answer", "game"),
    ("My match",),
)
STAKE_LOCKED = Template(
    "stake_locked",
    "Match {{1}}: {{2}}. Stakes are held in escrow until the result is in.",
    ("match_code", "what"),
    ("Lock my stake", "Report result"),
)
MATCH_READY = Template(
    "match_ready",
    "Match {{1}}: both stakes are locked. Play your {{2}} match, then report the result here.",
    ("match_code", "game"),
    ("Report result",),
)
REPORT_REMINDER = Template(
    "report_reminder",
    "Match {{1}} is waiting for your result. Please report it by {{2}}.",
    ("match_code", "deadline"),
    ("Report result",),
)
MATCH_RESULT = Template(
    "match_result",
    "Match {{1}} is settled: {{2}}. Amount: {{3}} USDC. Your balance is {{4}} USDC.",
    ("match_code", "outcome", "amount", "balance"),
    ("Wallet",),
)
MATCH_DISPUTED = Template(
    "match_disputed",
    "Match {{1}} is under review because the reported results differ. We will message you with the outcome.",
    ("match_code",),
    ("Match status",),
)
MATCH_REFUNDED = Template(
    "match_refunded",
    "Match {{1}} was {{2}}. {{3}} USDC was returned to your balance.",
    ("match_code", "reason", "amount"),
    ("Wallet",),
)
DEPOSIT_RECEIVED = Template(
    "deposit_received",
    "Deposit received: {{1}} USDC. Your balance is {{2}} USDC.",
    ("amount", "balance"),
    ("Wallet",),
)
WITHDRAWAL_UPDATE = Template(
    "withdrawal_update",
    "Your withdrawal of {{1}} USDC to {{2}} is {{3}}.",
    ("amount", "destination", "status"),
    ("Wallet",),
)
SECURITY_OUTFLOW = Template(
    "security_outflow",
    "Security notice: {{1}} USDC left your Boardman wallet to {{2}}. If this was not you, contact Boardman support right away.",
    ("amount", "destination"),
    ("Wallet", "Not me"),
)
SPEND_APPROVAL = Template(
    "spend_approval",
    "Approve a {{1}} of {{2}} USDC on Boardman? This request expires in {{3}}.",
    ("action", "amount", "expires_in"),
    ("Yes", "No", "Always"),
)
CUP_MATCH_READY = Template(
    "cup_match_ready",
    "Your {{1}} match against {{2}} is ready. Play it by {{3}}.",
    ("cup", "opponent", "deadline"),
    ("My match",),
)
CUP_RESULT = Template(
    "cup_result",
    "{{1}} has finished. You placed {{2}}. Prize: {{3}} USDC.",
    ("cup", "place", "prize"),
    ("Wallet",),
)

ALL: tuple[Template, ...] = (
    ACCOUNT_LINKED, CHALLENGE_RECEIVED, CHALLENGE_ANSWERED, STAKE_LOCKED, MATCH_READY, REPORT_REMINDER,
    MATCH_RESULT, MATCH_DISPUTED, MATCH_REFUNDED, DEPOSIT_RECEIVED, WITHDRAWAL_UPDATE,
    SECURITY_OUTFLOW, SPEND_APPROVAL, CUP_MATCH_READY, CUP_RESULT,
)
BY_KIND: dict[str, Template] = {t.name: t for t in ALL}


def for_kind(kind: str) -> Optional[Template]:
    return BY_KIND.get(kind)


class MissingParam(KeyError):
    pass


def components(tpl: Template, params: dict[str, Any], button_payloads: Optional[list[str]] = None) -> list[dict]:
    """Cloud API ``template.components`` for one send."""
    values = []
    for name in tpl.params:
        if name not in params or params[name] in (None, ""):
            raise MissingParam(f"{tpl.name}: missing {name}")
        # Template variables may not contain newlines or 4+ spaces [?].
        values.append({"type": "text", "text": " ".join(str(params[name]).split())[:1024]})
    comps: list[dict] = [{"type": "body", "parameters": values}] if values else []
    for i, payload in enumerate(button_payloads or []):
        if i >= len(tpl.buttons):
            break
        comps.append({
            "type": "button",
            "sub_type": "quick_reply",
            "index": str(i),
            "parameters": [{"type": "payload", "payload": payload}],
        })
    return comps


def message(tpl: Template, params: dict[str, Any], button_payloads: Optional[list[str]] = None) -> dict:
    return {
        "type": "template",
        "template": {
            "name": tpl.name,
            "language": {"code": tpl.language},
            "components": components(tpl, params, button_payloads),
        },
    }
