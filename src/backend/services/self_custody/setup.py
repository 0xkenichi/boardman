"""Wallet setup and change: link a passkey smart account to a Boardman profile.

The page ``/app/wallet/setup`` is opened either from a chat link
(``?t=<token>``, a ``channel_tokens`` row with purpose ``sc_setup``: single
use, short TTL, bound to the profile) or by a signed-in web session (the BFF
forwards the session profile as the caller and its sign-in time).

An address becomes the player's wallet only after three things (see
docs/payments/SELF_CUSTODY_WALLETS.md, "Setup proof"):

1. **Proof of control.** ``challenge`` issues a one-time EIP-191 message bound
   to the profile, the setup link (or session), the address, the EVM chain id
   and a 10-minute window; the page signs it with the passkey smart account;
   ``register`` verifies it on chain (ERC-1271 / ERC-6492, ``proof.py``).
   Reused, expired, wrong-profile, wrong-link, wrong-chain and forged proofs
   are refused, and a challenge can be tried once.
2. **The player's "Yes" in their chat.** A proven address waits in
   ``pending_confirm``; every chat the player has (Telegram, WhatsApp) gets
   "Is this your wallet? 0x…  Yes / No". Someone who completes setup from a
   stolen or forwarded link holds a valid proof for *their* wallet but not the
   player's chat, so it never becomes active.
3. **For a change only:** a web sign-in at most ``SELF_CUSTODY_REAUTH_SEC``
   old, then a cool-down (``SELF_CUSTODY_CHANGE_COOLDOWN_SEC``, 24 h) during
   which the old account stays active, top-ups go to the custodial play
   wallet and every chat can cancel the change.

The browser computes the counterfactual address; we store the address and
the public credential id only.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from typing import Any, Optional

from gaming.src.backend.services.self_custody import chain, config, proof, store, wallets
from gaming.src.backend.services.self_custody.intents import SETUP_PURPOSE, IntentRefused, setup_url

logger = logging.getLogger(__name__)

CHALLENGES_PER_HOUR = 20


def _links():
    from gaming.src.channels.core import withdraw_links

    return withdraw_links


def _now(now_ms: Optional[int]) -> int:
    return now_ms if now_ms is not None else store.now_ms()


def _hash(nonce: str) -> str:
    return hashlib.sha256((nonce or "").encode("utf-8")).hexdigest()


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


def _resolve(token: Optional[str], caller: Optional[str], now: int) -> tuple[str, Optional[dict]]:
    """(profile_id, token row or None). A token wins; else a web session."""
    wl = _links()
    if token:
        try:
            row = wl.check_open(wl.load(token), now, caller, purposes=(SETUP_PURPOSE,))
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


def _fresh_session(pid: str, caller: Optional[str], auth_iat_ms: Optional[int], now: int) -> bool:
    """A web session for this profile signed in at most SELF_CUSTODY_REAUTH_SEC ago."""
    if not caller or str(caller) != pid or not auth_iat_ms:
        return False
    return now - config.reauth_max_age_ms() <= int(auth_iat_ms) <= now + 60_000


def _has_chat(pid: str) -> bool:
    try:
        from gaming.src.channels.core.identity.repo import get_repo

        return bool(get_repo().for_profile(pid))
    except Exception:
        logger.warning("[self_custody] identity lookup failed", exc_info=True)
        return True  # do not block on a lookup error; the confirmation still has to arrive


def _pending_view(p: Optional[dict]) -> Optional[dict]:
    if not p:
        return None
    return {"address": p["address"], "kind": p["kind"], "status": p["status"],
            "active_at_ms": p.get("active_at_ms") if p["status"] == "cooling" else None}


def view(token: Optional[str], *, caller: Optional[str] = None, auth_iat_ms: Optional[int] = None,
         now_ms: Optional[int] = None) -> dict:
    if not config.enabled():
        raise IntentRefused("off", "Not available.")
    now = _now(now_ms)
    pid, row = _resolve(token, caller, now)
    s = config.chain_settings()
    w = wallets.get(pid)
    fresh = _fresh_session(pid, caller, auth_iat_ms, now)
    return {
        "ok": True,
        "username": _username(pid),
        "wallet": {"address": w["address"], "credential_id": w["credential_id"]} if w else None,
        "pending": _pending_view(wallets.pending(pid)),
        "can_change": bool(w) and fresh,
        "change_needs_signin": bool(w) and not fresh,
        "chain": {k: s[k] for k in ("chain", "label", "evm_chain_id", "rpc_url", "modular_path")},
        "via": "link" if row else "session",
    }


def challenge(token: Optional[str], *, address: str, caller: Optional[str] = None,
              auth_iat_ms: Optional[int] = None, now_ms: Optional[int] = None) -> dict:
    """A one-time message for the passkey account at ``address`` to sign."""
    if not config.enabled():
        raise IntentRefused("off", "Not available.")
    now = _now(now_ms)
    pid, row = _resolve(token, caller, now)
    try:
        addr = wallets.check_address(address)
    except wallets.WalletRefused as exc:
        raise IntentRefused(exc.kind, exc.message) from exc
    from gaming.src.channels.core import ratelimit

    if not ratelimit.hit(f"sc_challenge:{pid}", limit=CHALLENGES_PER_HOUR, window_sec=3600, now_ms=now):
        raise IntentRefused("rate_limited", "Too many attempts. Try again in an hour.")
    owner = wallets.owner_of(addr)
    if owner and str(owner) != pid:
        raise IntentRefused("taken", "This wallet is already linked to another Boardman account.")
    if not _has_chat(pid):
        raise IntentRefused("no_chat", "Link your Telegram or WhatsApp first: you confirm the wallet there.")
    cur = wallets.get(pid)
    kind = "change" if cur else "setup"
    if cur:
        if cur["address"].lower() == addr.lower():
            raise IntentRefused("exists", "This wallet is already linked to your account.")
        if not _fresh_session(pid, caller, auth_iat_ms, now):
            raise IntentRefused("reauth", "To change your wallet, sign in again on the website first.")
    s = config.chain_settings()
    if not s["evm_chain_id"]:
        raise IntentRefused("not_configured", "Passkey wallets are not set up on this network yet.")
    expires = now + config.ttl_ms()
    rid = f"scw_{uuid.uuid4().hex[:24]}"
    msg = proof.message_for(site=_site(), profile_id=pid, address=addr, evm_chain_id=s["evm_chain_id"],
                            kind=kind, nonce=secrets.token_hex(16), issued_ms=now, expires_ms=expires)
    store.create_request(request_id=rid, profile_id=pid, kind=kind, chain=s["chain"],
                         evm_chain_id=s["evm_chain_id"], address=addr,
                         previous_address=cur["address"] if cur else None,
                         token_hash=row["token_hash"] if row else None, message=msg,
                         created_at_ms=now, expires_at_ms=expires)
    return {"ok": True, "challenge_id": rid, "message": msg, "kind": kind, "expires_at_ms": expires,
            "evm_chain_id": s["evm_chain_id"]}


def _site() -> str:
    from gaming.src.channels import config as ch_config

    return ch_config.site_url()


def register(token: Optional[str], *, address: str, credential_id: str, challenge_id: str, signature: str,
             caller: Optional[str] = None, auth_iat_ms: Optional[int] = None,
             now_ms: Optional[int] = None) -> dict:
    """Verify the signed challenge; the address then waits for the chat "Yes".

    Sync: call off the event loop. The returned ``confirm_nonce`` and
    ``profile_id`` are for the chat prompt only; the API never sends them to
    the page."""
    if not config.enabled():
        raise IntentRefused("off", "Not available.")
    now = _now(now_ms)
    wl = _links()
    pid, row = _resolve(token, caller, now)
    try:
        addr = wallets.check_address(address)
    except wallets.WalletRefused as exc:
        raise IntentRefused(exc.kind, exc.message) from exc
    if not wallets.CRED_RE.match(credential_id or ""):
        raise IntentRefused("bad_request", "Passkey details missing.")
    req = store.get_request(challenge_id or "")
    if req is None or str(req["profile_id"]) != pid:
        raise IntentRefused("bad_proof", "This wallet check is not valid. Start again.")
    if req["status"] != "challenge":
        raise IntentRefused("used", "This wallet check was already used. Start again.")
    if int(req["expires_at_ms"]) <= now:
        store.move_request(req["id"], "expired", expect=("challenge",))
        raise IntentRefused("expired", "This wallet check expired. Start again.")
    if (row["token_hash"] if row else None) != req["token_hash"]:
        raise IntentRefused("bad_proof", "This wallet check belongs to a different link. Start again.")
    s = config.chain_settings()
    if req["chain"] != s["chain"] or int(req["evm_chain_id"]) != int(s["evm_chain_id"] or 0):
        raise IntentRefused("wrong_chain", "This wallet check was made for a different network. Start again.")
    if req["address"].lower() != addr.lower():
        raise IntentRefused("bad_proof", "This wallet check was made for a different wallet. Start again.")
    cur = wallets.get(pid)
    if req["kind"] == "change":
        if not cur or (req["previous_address"] or "").lower() != cur["address"].lower():
            raise IntentRefused("state", "Your wallet changed in the meantime. Start again.")
        if not _fresh_session(pid, caller, auth_iat_ms, now):
            raise IntentRefused("reauth", "To change your wallet, sign in again on the website first.")
    elif cur:
        raise IntentRefused("exists", "You already have a passkey wallet linked.")
    if not store.move_request(req["id"], "verifying", expect=("challenge",)):
        raise IntentRefused("used", "This wallet check was already used. Start again.")
    try:
        ok = proof.verify(chain.get_reader(), addr, req["message"], signature)
    except Exception as exc:
        logger.warning("[self_custody] setup proof check failed", exc_info=True)
        store.move_request(req["id"], "failed", expect=("verifying",))
        raise IntentRefused("not_configured", "Could not check your wallet right now. Try again.") from exc
    if not ok:
        store.move_request(req["id"], "failed", expect=("verifying",))
        if row is not None:  # a forged proof burns the link
            wl.set_status(row["token_hash"], "failed", {"error": "bad_proof"})
        logger.warning("[self_custody] setup proof rejected for profile %s", pid)
        raise IntentRefused("bad_proof", "Your passkey's signature did not check out. Nothing was linked.")
    owner = wallets.owner_of(addr)
    if owner and str(owner) != pid:
        store.move_request(req["id"], "failed", expect=("verifying",))
        raise IntentRefused("taken", "This wallet is already linked to another Boardman account.")
    if row is not None and not wl.set_status(row["token_hash"], "done", {"request_id": req["id"]}):
        store.move_request(req["id"], "failed", expect=("verifying",))
        raise IntentRefused("used", "This link was already used. Start again in the chat.")
    nonce = secrets.token_urlsafe(16)
    if not store.move_request(req["id"], "pending_confirm", expect=("verifying",), credential_id=credential_id,
                              confirm_hash=_hash(nonce), proved_at_ms=now,
                              expires_at_ms=now + config.confirm_ttl_ms()):
        raise IntentRefused("used", "This wallet check was already used. Start again.")
    store.supersede_pending(pid, keep=req["id"])
    return {"ok": True, "status": "pending_confirm", "address": addr, "kind": req["kind"],
            "message": "Almost done: confirm this wallet in your chat with Boardman.",
            "profile_id": pid, "confirm_nonce": nonce, "request_id": req["id"]}


# ── the chat side: "Is this your wallet?" ────────────────────────────────────


def answer(profile_id: Optional[str], nonce: str, *, approve: bool, now_ms: Optional[int] = None) -> dict[str, Any]:
    """The player's Yes / No from any of their chats.

    Returns ``{"result": active|cooling|declined|refused, "message", ...}``.
    Only the profile the request belongs to can answer; each prompt once."""
    now = _now(now_ms)
    req = store.request_by_confirm(_hash(nonce)) if nonce else None
    if req is None:
        return {"result": "refused", "message": "That button is no longer active."}
    if not profile_id or str(req["profile_id"]) != str(profile_id):
        logger.warning("[self_custody] wallet confirmation tapped by another profile")
        return {"result": "refused", "message": "That request isn't yours."}
    if req["status"] != "pending_confirm":
        return {"result": "refused", "message": "That request was already answered or replaced."}
    if int(req["expires_at_ms"]) <= now:
        store.move_request(req["id"], "expired", expect=("pending_confirm",))
        return {"result": "refused", "message": "That request expired. Nothing was linked. Start again."}
    base = {"address": req["address"], "kind": req["kind"], "profile_id": str(req["profile_id"])}
    if not approve:
        store.move_request(req["id"], "declined", expect=("pending_confirm",))
        logger.warning("[self_custody] player declined wallet %s (%s)", req["id"], req["kind"])
        return {**base, "result": "declined", "message": "OK, that wallet was NOT linked. Nothing changed."}
    if req["kind"] == "setup":
        ok, why = store.activate_setup(req["id"], wallet_key=config.wallet_key(req["chain"]),
                                       wallet_id=f"passkey:{req['credential_id']}",
                                       account_type=wallets.ACCOUNT_TYPE, now=now)
        if not ok:
            if why != "state":
                store.move_request(req["id"], "failed", expect=("pending_confirm",))
            return {"result": "refused", "message": "That wallet could not be linked. Start again."}
        return {**base, "result": "active", "message": "Your passkey wallet is linked."}
    cur = wallets.get(str(req["profile_id"]), req["chain"])
    if not cur or cur["address"].lower() != (req["previous_address"] or "").lower():
        store.move_request(req["id"], "failed", expect=("pending_confirm",))
        return {"result": "refused", "message": "Your wallet changed in the meantime. Start again."}
    active_at = now + config.change_cooldown_ms()
    if not store.move_request(req["id"], "cooling", expect=("pending_confirm",), confirmed_at_ms=now,
                              active_at_ms=active_at):
        return {"result": "refused", "message": "That request was already answered or replaced."}
    return {**base, "result": "cooling", "active_at_ms": active_at, "request_id": req["id"],
            "previous_address": req["previous_address"], "message": "Wallet change scheduled."}


def reissue_confirm(profile_id: str, now_ms: Optional[int] = None) -> Optional[tuple[dict, str]]:
    """A fresh Yes/No nonce for the newest waiting request (the chat's wallet
    screen, when the first prompt was missed). The old buttons stop working."""
    now = _now(now_ms)
    p = wallets.pending(profile_id)
    if not p or p["status"] != "pending_confirm" or int(p["expires_at_ms"]) <= now:
        return None
    nonce = secrets.token_urlsafe(16)
    if not store.move_request(p["id"], "pending_confirm", expect=("pending_confirm",), confirm_hash=_hash(nonce)):
        return None
    return p, nonce


def cancel(profile_id: Optional[str], request_id: str) -> Optional[dict]:
    """Cancel a waiting or cooling change from any of the player's chats."""
    req = store.get_request(request_id or "")
    if not req or not profile_id or str(req["profile_id"]) != str(profile_id):
        return None
    if not store.move_request(req["id"], "cancelled", expect=("pending_confirm", "cooling")):
        return None
    logger.warning("[self_custody] player cancelled wallet request %s", req["id"])
    return req
