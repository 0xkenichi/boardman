"""Nonce-bound approval buttons for money actions (CHANNELS_DESIGN §2.6).

Telegram's "the tap itself is the consent" is not enough off Telegram:
WhatsApp buttons can be tapped long after they were sent, and a forwarded
prompt must not move anyone's money. So a money action (lock a stake) first
sends a prompt whose Yes/No ids carry a fresh 128-bit nonce, never a row id:

* only the SHA-256 of the nonce is stored (``channel_tokens``, purpose
  ``approve:<action>``) with the profile, channel and chat it was sent to;
* it expires (``CHANNELS_APPROVAL_TTL_SEC``, 300 s) and works once: the
  claim is one conditional UPDATE, so a double tap or a replayed webhook
  cannot approve twice; a newer prompt for the same action supersedes it;
* on WhatsApp the prompt's message id (wamid) is recorded after sending and
  the tap's ``context.id`` must equal it (a reply to any other message, e.g.
  a copy, is refused);
* the tapper must be the same profile on the same chat.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from typing import Any, Optional

from gaming.src.channels import config
from gaming.src.channels.core import store
from gaming.src.channels.core.principal import Principal

logger = logging.getLogger(__name__)

PURPOSE = "approve:"


class ApprovalRefused(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # unknown | used | expired | not_yours | stale_context
        self.message = message


def ttl_ms() -> int:
    return config.int_env("CHANNELS_APPROVAL_TTL_SEC", 300) * 1000


def _hash(nonce: str) -> str:
    return hashlib.sha256((nonce or "").encode("utf-8")).hexdigest()


def issue(principal: Principal, action: str, payload: dict, *, now_ms: Optional[int] = None) -> str:
    """A fresh nonce for one approval prompt (supersedes older open ones)."""
    now = now_ms if now_ms is not None else store.now_ms()
    nonce = secrets.token_urlsafe(16)  # 128 bits, 22 chars
    purpose = PURPOSE + action
    with store.db().transaction() as tx:
        tx.execute(
            "UPDATE channel_tokens SET status = 'superseded' "
            "WHERE profile_id = ? AND purpose = ? AND status = 'open'",
            (principal.profile_id, purpose),
        )
        tx.execute(
            "INSERT INTO channel_tokens (token_hash, purpose, profile_id, channel, external_id, "
            "amount_micro, payload, status, attempts, created_at_ms, expires_at_ms) "
            "VALUES (?, ?, ?, ?, ?, NULL, ?, 'open', 0, ?, ?)",
            (_hash(nonce), purpose, principal.profile_id, principal.channel, str(principal.external_id),
             tx.json(payload), now, now + ttl_ms()),
        )
    return nonce


def bind_message(nonce: str, message_id: str) -> None:
    """Record the provider id of the message that carried the prompt."""
    if not nonce or not message_id:
        return
    with store.db().transaction() as tx:
        tx.execute(
            "UPDATE channel_tokens SET result = ? WHERE token_hash = ? AND status = 'open'",
            (tx.json({"message_id": str(message_id)}), _hash(nonce)),
        )


def _row(nonce: str) -> Optional[dict]:
    d = store.db()
    with d.transaction(readonly=True) as tx:
        row = tx.one("SELECT * FROM channel_tokens WHERE token_hash = ?", (_hash(nonce),))
    if row is None or not str(row.get("purpose") or "").startswith(PURPOSE):
        return None
    row["payload"] = d.dialect.unjson(row["payload"]) or {}
    raw = row.get("result")
    row["result"] = (d.dialect.unjson(raw) if raw is not None else None) or {}
    if isinstance(row["result"], str):
        row["result"] = json.loads(row["result"])
    return row


def _check(row: Optional[dict], principal: Principal, context_id: str, now: int) -> dict:
    if row is None:
        raise ApprovalRefused("unknown", "That button is no longer active.")
    if (str(row["profile_id"]) != str(principal.profile_id) or row["channel"] != principal.channel
            or str(row["external_id"]) != str(principal.external_id)):
        logger.warning("[channels] approval tapped by someone else (channel=%s)", principal.channel)
        raise ApprovalRefused("not_yours", "That approval isn't yours.")
    if row["status"] != "open":
        raise ApprovalRefused("used", "That request was already answered.")
    if int(row["expires_at_ms"]) <= now:
        raise ApprovalRefused("expired", "That request expired. Start again.")
    bound = str((row.get("result") or {}).get("message_id") or "")
    if bound and principal.channel == "whatsapp" and context_id != bound:
        logger.warning("[channels] approval tapped from another message context")
        raise ApprovalRefused("stale_context", "Please use the latest prompt.")
    return row


def consume(principal: Principal, nonce: str, *, approve: bool, context_id: str = "",
            now_ms: Optional[int] = None) -> tuple[str, dict]:
    """Answer one prompt. Returns (action, payload); raises ``ApprovalRefused``."""
    now = now_ms if now_ms is not None else store.now_ms()
    row = _check(_row(nonce), principal, context_id, now)
    status = "approved" if approve else "declined"
    with store.db().transaction() as tx:
        n = tx.rowcount(
            "UPDATE channel_tokens SET status = ?, consumed_at_ms = ? "
            "WHERE token_hash = ? AND status = 'open' AND expires_at_ms > ?",
            (status, now, row["token_hash"], now),
        )
    if n != 1:
        raise ApprovalRefused("used", "That request was already answered.")
    return str(row["purpose"])[len(PURPOSE):], dict(row["payload"])


def status_of(nonce: str) -> Optional[str]:
    row = _row(nonce)
    return row["status"] if row else None


def payload_of(nonce: str) -> Any:
    row = _row(nonce)
    return row["payload"] if row else None
