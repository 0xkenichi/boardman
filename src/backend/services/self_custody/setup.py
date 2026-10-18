"""Wallet setup: link a new passkey smart account to a Boardman profile.

The page ``/app/wallet/setup`` is opened either from a chat link
(``?t=<token>``, a ``channel_tokens`` row with purpose ``sc_setup``: single
use, short TTL, bound to the profile) or by a signed-in web session (the BFF
forwards the session profile as the caller). The browser creates the passkey
and computes the counterfactual address; we store the address and the public
credential id only.
"""
from __future__ import annotations

from typing import Optional

from gaming.src.backend.services.self_custody import config, wallets
from gaming.src.backend.services.self_custody.intents import SETUP_PURPOSE, IntentRefused, setup_url


def _links():
    from gaming.src.channels.core import withdraw_links

    return withdraw_links


def issue_link(profile_id: str, *, channel: str, external_id: str) -> tuple[str, int]:
    """(url, expires_at_ms) for the chat."""
    if not config.enabled():
        raise IntentRefused("off", "Not available.")
    wl = _links()
    try:
        link = wl.issue_purpose(SETUP_PURPOSE, str(profile_id), channel=channel, external_id=str(external_id or ""),
                                payload={}, rate_bucket=f"sc_setup:{profile_id}", path="wallet/setup")
    except wl.LinkRefused as exc:
        raise IntentRefused(exc.kind, exc.message) from exc
    return setup_url(link.token), link.expires_at_ms


def _resolve(token: Optional[str], caller: Optional[str], now: Optional[int]) -> tuple[str, Optional[dict]]:
    """(profile_id, token row or None). A token wins; else a web session."""
    wl = _links()
    if token:
        from gaming.src.channels.core import store as ch_store

        try:
            row = wl.check_open(wl.load(token), now if now is not None else ch_store.now_ms(), caller,
                                purposes=(SETUP_PURPOSE,))
        except wl.LinkRefused as exc:
            raise IntentRefused(exc.kind, exc.message) from exc
        return str(row["profile_id"]), row
    if caller:
        return str(caller), None
    raise IntentRefused("not_found", "Open this page from the link in your chat, or sign in first.")


def _username(profile_id: str) -> str:
    try:
        from gaming.src.channels.core.identity.repo import get_repo

        tag = (get_repo().get_profile(profile_id) or {}).get("gaming_tag") or ""
    except Exception:
        tag = ""
    return f"Boardman @{tag}" if tag else f"Boardman {profile_id[:8]}"


def view(token: Optional[str], *, caller: Optional[str] = None, now_ms: Optional[int] = None) -> dict:
    if not config.enabled():
        raise IntentRefused("off", "Not available.")
    pid, row = _resolve(token, caller, now_ms)
    s = config.chain_settings()
    w = wallets.get(pid)
    return {
        "ok": True,
        "username": _username(pid),
        "wallet": {"address": w["address"], "credential_id": w["credential_id"]} if w else None,
        "chain": {k: s[k] for k in ("chain", "label", "evm_chain_id", "rpc_url", "modular_path")},
        "via": "link" if row else "session",
    }


def register(token: Optional[str], *, address: str, credential_id: str, caller: Optional[str] = None,
             now_ms: Optional[int] = None) -> dict:
    """Store the account. Sync: call off the event loop. Returns the reply
    and whether a chat notice should go out (``created``)."""
    if not config.enabled():
        raise IntentRefused("off", "Not available.")
    wl = _links()
    pid, row = _resolve(token, caller, now_ms)
    if row is not None and not wl.set_status(row["token_hash"], "claimed"):
        raise IntentRefused("used", "This link was already used. Start again in the chat.")
    try:
        w, created = wallets.register(pid, address, credential_id)
    except wallets.WalletRefused as exc:
        if row is not None:
            wl.set_status(row["token_hash"], "failed", {"error": exc.kind}, only_if="claimed")
        raise IntentRefused(exc.kind, exc.message) from exc
    if row is not None:
        wl.set_status(row["token_hash"], "done", {"address": w["address"]}, only_if="claimed")
    return {"ok": True, "address": w["address"], "created": created, "profile_id": pid,
            "message": "Your passkey wallet is linked. You hold the keys; Boardman can't move your money."}
