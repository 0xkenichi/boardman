"""Prepare, approve and confirm actions signed by the player's passkey.

1. ``prepare_lock`` / ``prepare_withdraw`` (from the chat): checks, exact
   calls for the smart account, an intent row and a one-time approve link
   (``channel_tokens`` purpose ``sc_approve``; SHA-256 at rest, short TTL,
   bound to profile + action + amount + match through the intent).
2. ``view`` (the approve page): shows what will be signed; never consumes.
3. ``submit`` (the page, after the UserOperation landed): the amount and match
   are echoed back (a mismatch burns the link), the token is claimed once, the
   hashes are recorded — and nothing else is trusted.
4. ``confirm`` (right after submit, and from the watcher): reads the receipt
   or scans logs and only moves the intent to ``confirmed`` when the chain
   shows the configured escrow's ``MatchCreated`` / ``MatchJoined`` for this
   match, this account and this stake (or the USDC ``Transfer`` for a
   withdrawal). Then, and only then, the match advances.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from gaming.src.backend.services.self_custody import calls as C
from gaming.src.backend.services.self_custody import chain, config, store, wallets

logger = logging.getLogger(__name__)

PURPOSE = "sc_approve"
SETUP_PURPOSE = "sc_setup"
ACTIONS = ("lock_create", "lock_join", "withdraw")
HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
GAS_MARGIN_RAW = 50_000  # $0.05 kept back when the player pays Arc gas in USDC
EXPIRE_GRACE_MS = 30 * 60 * 1000


class IntentRefused(Exception):
    STATUS = {
        "not_found": 404, "expired": 410, "used": 409, "wrong_profile": 403, "amount_mismatch": 409,
        "rate_limited": 429, "bad_request": 400, "no_wallet": 409, "funds": 402, "wrong_wallet": 409,
        "not_configured": 503, "state": 409, "taken": 409, "exists": 409, "bad_address": 400,
        "off": 404, "gate": 423, "bad_proof": 422, "reauth": 401, "wrong_chain": 409, "no_chat": 409,
    }

    def __init__(self, kind: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail

    @property
    def status_code(self) -> int:
        return self.STATUS.get(self.kind, 400)

    def body(self) -> dict[str, Any]:
        return {"ok": False, "error": self.kind, "message": self.message}


@dataclass
class Prepared:
    intent: dict
    token: str
    url: str
    expires_at_ms: int


def _links():
    from gaming.src.channels.core import withdraw_links

    return withdraw_links


def _site() -> str:
    from gaming.src.channels import config as ch_config

    return ch_config.site_url()


def approve_url(token: str) -> str:
    return f"{_site()}/app/approve/{token}"


def setup_url(token: str) -> str:
    return f"{_site()}/app/wallet/setup?t={token}"


def _require_on() -> None:
    if not config.enabled():
        raise IntentRefused("off", "Not available.")


def _settings() -> dict:
    s = config.chain_settings()
    if not s["escrow"] or not s["usdc"] or not s["evm_chain_id"]:
        raise IntentRefused("not_configured", "Passkey approvals are not set up on this network yet.")
    return s


def _issue(profile_id: str, intent: dict, *, channel: str, external_id: str,
           now_ms: Optional[int] = None) -> Prepared:
    wl = _links()
    try:
        link = wl.issue_purpose(PURPOSE, profile_id, channel=channel, external_id=str(external_id or ""),
                                payload={"intent_id": intent["id"]}, rate_bucket=f"sc_issue:{profile_id}",
                                path="approve", now_ms=now_ms)
    except wl.LinkRefused as exc:
        store.transition(intent["id"], "superseded", expect=("prepared",))
        raise IntentRefused(exc.kind, exc.message) from exc
    store.set_token(intent["id"], wl.token_hash(link.token))
    return Prepared(intent, link.token, approve_url(link.token), link.expires_at_ms)


def _from_block(reader) -> Optional[int]:
    try:
        return max(0, int(reader.block_number()) - 5)
    except Exception:
        logger.warning("[self_custody] block number unavailable", exc_info=True)
        return None


def _check_balance(reader, s: dict, account: str, raw: int) -> None:
    need = raw + (0 if config.sponsor_gas() else GAS_MARGIN_RAW)
    try:
        have = int(reader.usdc_balance(s["usdc"], account))
    except Exception as exc:
        raise IntentRefused("not_configured", "Could not read your wallet balance. Try again shortly.") from exc
    if have < need:
        raise IntentRefused(
            "funds",
            f"Not enough USDC in your wallet. Need ${C.from_raw(need):,.2f}, have ${C.from_raw(have):,.2f}. "
            f"Add USDC on {s['label']} to {account}.",
            address=account, need=C.from_raw(need), have=C.from_raw(have),
        )


def _version(reader, escrow: str) -> int:
    v = config.escrow_version_override()
    if v:
        return v
    try:
        return int(reader.escrow_version(escrow))
    except Exception:
        return 1


# ── which address is a player on the escrow ─────────────────────────────────


def creator_binding(challenge_id: str) -> Optional[dict]:
    """The creator's confirmed passkey lock for this match (its ``detail``
    holds the player2 the permit bound), or None."""
    rows = store.find(challenge_id=str(challenge_id), action="lock_create", statuses=("confirmed",), limit=1)
    return rows[0] if rows else None


def locked_address(challenge_id: str, profile_id: str) -> Optional[str]:
    """The passkey account this player locked this match with, if any.
    The escrow pays winners and refunds only to recorded players, so this is
    the payout address for passkey players."""
    rows = [r for r in store.find(challenge_id=str(challenge_id), profile_id=str(profile_id),
                                  statuses=("confirmed",), limit=5)
            if r["action"] in ("lock_create", "lock_join")]
    return rows[0]["account"] if rows else None


async def escrow_address_of(profile_id: str) -> str:
    """Where a player stakes from: their passkey account, else their Circle wallet."""
    acct = await asyncio.to_thread(wallets.address, profile_id)
    if acct:
        return acct
    from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

    w = await ensure_user_wallet(str(profile_id), chain_id=config.chain_key())
    addr = (w or {}).get("address") or ""
    if not wallets.ADDRESS_RE.match(addr):
        raise IntentRefused("not_configured", "Your opponent's wallet is not ready yet. Try again shortly.")
    return addr


def join_allowed(challenge_id: str, account: str, reader=None) -> bool:
    """May the opponent join from ``account``? Only if that is the player2
    the creator's permit bound (v2), or the escrow binds on join (v1)."""
    b = creator_binding(challenge_id)
    if b is not None:
        p2 = str((b.get("detail") or {}).get("player2") or "")
        return bool(p2) and p2.lower() == account.lower()
    s = config.chain_settings()
    try:
        return _version(reader or chain.get_reader(), s["escrow"]) < 2
    except Exception:
        return False


# ── prepare ──────────────────────────────────────────────────────────────────


async def prepare_lock(profile_id: str, challenge: dict, *, channel: str, external_id: str,
                       now_ms: Optional[int] = None) -> Prepared:
    _require_on()
    from eth_utils import to_checksum_address

    from gaming.src.channels.core.actions import matches as svc

    pid = str(profile_id)
    account = await asyncio.to_thread(wallets.address, pid)
    if not account:
        raise IntentRefused("no_wallet", "Set up your passkey wallet first.")
    who = svc.role(challenge, pid)
    if who is None:
        raise IntentRefused("wrong_profile", "Not your match.")
    # Boardman's own rules for entering a match still apply (pause, stake
    # limits, lock rate); they gate the escrow, not the player's wallet.
    from gaming.src.backend.services.safety import assert_money_ops_allowed

    gate = assert_money_ops_allowed(pid, action="lock", amount=Decimal(str(challenge["amount_usdc"])), kind="lock")
    if gate:
        raise IntentRefused("gate", svc.plain(gate))
    s = _settings()
    reader = chain.get_reader()
    cid = str(challenge["id"])
    amount = Decimal(str(challenge["amount_usdc"]))
    raw = C.to_raw(amount)
    mid = C.match_id_bytes32(cid)
    version = await asyncio.to_thread(_version, reader, s["escrow"])
    detail: dict[str, Any] = {"role": who, "version": version, "match_id": "0x" + mid.hex(),
                              "escrow": s["escrow"], "usdc": s["usdc"]}

    if who == "creator":
        if challenge.get("creator_lock_tx_id"):
            raise IntentRefused("state", "You already locked your stake.")
        if not challenge.get("opponent_id"):
            raise IntentRefused("state", "Wait until your opponent accepts, then lock.")
        action = "lock_create"
        if version >= 2:
            from gaming.src.stack.agentic.onchain import load_resolver_key, sign_create_permit

            p2 = to_checksum_address(await escrow_address_of(str(challenge["opponent_id"])))
            deadline = (now_ms or store.now_ms()) // 1000 + config.ttl_ms() // 1000
            sig = await asyncio.to_thread(
                sign_create_permit, load_resolver_key(), chain_id=s["evm_chain_id"],
                escrow=to_checksum_address(s["escrow"]), match_id_b32=mid,
                player1=to_checksum_address(account), player2=p2, stake_raw=raw, deadline=deadline,
            )
            lock = C.create_match_v2(s["escrow"], mid, p2, raw, deadline, sig)
            detail.update(player2=p2, deadline=deadline)
        else:
            lock = C.create_match_v1(s["escrow"], mid, raw)
    else:
        if challenge.get("opponent_lock_tx_id"):
            raise IntentRefused("state", "You already locked your stake.")
        if challenge.get("status") != "creator_locked":
            raise IntentRefused("state", "Wait for the challenger to lock first.")
        if not await asyncio.to_thread(join_allowed, cid, account, reader):
            raise IntentRefused("wrong_wallet", "This match was set up with your previous wallet; "
                                                "finish it there.")
        action = "lock_join"
        lock = C.join_match(s["escrow"], mid, raw)

    await asyncio.to_thread(_check_balance, reader, s, account, raw)
    call_list = [C.usdc_approve(s["usdc"], s["escrow"], raw).as_dict(), lock.as_dict()]
    from_block = await asyncio.to_thread(_from_block, reader)
    expires = (now_ms or store.now_ms()) + config.ttl_ms()

    def _make() -> Prepared:
        intent = store.create(profile_id=pid, action=action, chain=s["chain"], account=account,
                              challenge_id=cid, amount_micro=raw, to_address=s["escrow"], calls=call_list,
                              detail=detail, expires_at_ms=expires, from_block=from_block)
        return _issue(pid, intent, channel=channel, external_id=external_id, now_ms=now_ms)

    return await asyncio.to_thread(_make)


def prepare_withdraw(profile_id: str, to_address: str, amount: Decimal, *, channel: str, external_id: str,
                     now_ms: Optional[int] = None) -> Prepared:
    """A USDC transfer from the player's own account (sync)."""
    _require_on()
    from eth_utils import to_checksum_address

    pid = str(profile_id)
    account = wallets.address(pid)
    if not account:
        raise IntentRefused("no_wallet", "Set up your passkey wallet first.")
    if not wallets.ADDRESS_RE.match(to_address or ""):
        raise IntentRefused("bad_address", "That is not a wallet address.")
    if to_address.lower() == account.lower():
        raise IntentRefused("bad_address", "That is your own wallet.")
    raw = C.to_raw(amount)
    if raw <= 0:
        raise IntentRefused("bad_request", "Send an amount above zero.")
    s = _settings()
    reader = chain.get_reader()
    _check_balance(reader, s, account, raw)
    dest = to_checksum_address(to_address)
    intent = store.create(
        profile_id=pid, action="withdraw", chain=s["chain"], account=account, challenge_id=None,
        amount_micro=raw, to_address=dest, calls=[C.usdc_transfer(s["usdc"], dest, raw).as_dict()],
        detail={"usdc": s["usdc"]}, expires_at_ms=(now_ms or store.now_ms()) + config.ttl_ms(),
        from_block=_from_block(reader),
    )
    return _issue(pid, intent, channel=channel, external_id=external_id, now_ms=now_ms)


# ── the approve page ─────────────────────────────────────────────────────────


def _open(token: str, session_profile_id: Optional[str], now: int) -> tuple[dict, dict]:
    wl = _links()
    try:
        row = wl.check_open(wl.load(token), now, session_profile_id, purposes=(PURPOSE,))
    except wl.LinkRefused as exc:
        raise IntentRefused(exc.kind, exc.message) from exc
    intent = store.get(str((row.get("payload") or {}).get("intent_id") or ""))
    if intent is None or intent["profile_id"] != row["profile_id"]:
        raise IntentRefused("not_found", "This link is not valid.")
    if intent["status"] != "prepared":
        raise IntentRefused("used", "This request was already handled or replaced. Start again in the chat.")
    return row, intent


def _match_info(challenge_id: Optional[str], profile_id: str) -> dict:
    if not challenge_id:
        return {}
    try:
        from gaming.src.channels.core.actions import matches as svc
        from gaming.src.channels.core.identity.repo import get_repo
        from gaming.src.channels.core.match_notices import game_label

        ch = svc.load(challenge_id) or {}
        other = svc.other_party(ch, profile_id) if ch else None
        tag = (get_repo().get_profile(str(other)) or {}).get("gaming_tag") if other else None
        return {"code": svc.code_of(ch) if ch else "", "game": game_label(str(ch.get("game") or "")),
                "opponent": f"@{tag}" if tag else ""}
    except Exception:
        logger.debug("[self_custody] match info unavailable", exc_info=True)
        return {}


def headline(intent: dict, match: dict) -> str:
    amt = f"{C.from_raw(intent['amount_micro']):,.2f}"
    label = config.chain_settings(intent["chain"])["label"]
    if intent["action"] == "withdraw":
        return f"Send {amt} USDC from your wallet to {intent['to_address']} on {label}"
    code = match.get("code") or "your match"
    return f"Lock {amt} USDC into escrow for match {code} on {label}"


def view(token: str, *, session_profile_id: Optional[str] = None, now_ms: Optional[int] = None) -> dict:
    _require_on()
    now = now_ms if now_ms is not None else store.now_ms()
    row, intent = _open(token, session_profile_id, now)
    s = config.chain_settings(intent["chain"])
    match = _match_info(intent.get("challenge_id"), intent["profile_id"])
    w = wallets.get(intent["profile_id"], intent["chain"]) or {}
    return {
        "ok": True,
        "action": intent["action"],
        "headline": headline(intent, match),
        "amount": str(C.from_raw(intent["amount_micro"])),
        "account": intent["account"],
        "credential_id": w.get("credential_id"),
        "to": intent["to_address"],
        "challenge_id": intent.get("challenge_id"),
        "match": match,
        "calls": intent["calls"],
        "sponsor_gas": config.sponsor_gas(),
        "chain": {k: s[k] for k in ("chain", "label", "evm_chain_id", "rpc_url", "modular_path", "explorer_tx")},
        "expires_in_sec": max(0, (int(row["expires_at_ms"]) - now) // 1000),
    }


def submit(token: str, *, tx_hash: str, user_op_hash: Optional[str], amount: Optional[str],
           challenge_id: Optional[str], session_profile_id: Optional[str] = None,
           now_ms: Optional[int] = None) -> dict:
    """The page reports a landed UserOperation. Claims the link once, records
    the hashes, then confirms against the chain. Sync: call off the event loop."""
    _require_on()
    wl = _links()
    now = now_ms if now_ms is not None else store.now_ms()
    row, intent = _open(token, session_profile_id, now)
    th = row["token_hash"]
    try:
        echoed = C.to_raw(Decimal(str(amount)))
    except (InvalidOperation, ValueError, TypeError):
        raise IntentRefused("bad_request", "Amount missing.")
    if echoed != int(intent["amount_micro"]) or (challenge_id or None) != (intent.get("challenge_id") or None):
        wl.set_status(th, "burned", {"reason": "amount_mismatch"})
        logger.warning("[self_custody] approve link burned: amount or match tampering")
        raise IntentRefused("amount_mismatch", "This request does not match. The link is now closed.")
    if not HASH_RE.match(tx_hash or "") or (user_op_hash and not HASH_RE.match(user_op_hash)):
        raise IntentRefused("bad_request", "Transaction hash missing.")
    tx_hash = tx_hash.lower()
    if store.tx_hash_taken(tx_hash, intent["id"]):
        raise IntentRefused("taken", "That transaction belongs to another request.")
    if not wl.set_status(th, "claimed", {"tx_hash": tx_hash}):
        raise IntentRefused("used", "This request was already handled. Start again in the chat.")
    store.transition(intent["id"], "submitted", expect=("prepared",), tx_hash=tx_hash,
                     user_op_hash=(user_op_hash or "").lower() or None)
    out = confirm(intent["id"])
    wl.set_status(th, "done" if out["status"] != "failed" else "failed", out, only_if="claimed")
    msg = {
        "confirmed": "Done. Confirmed on chain.",
        "pending": "Sent. Waiting for the network to confirm; the chat will tell you.",
        "failed": "The network rejected this transaction. Nothing moved; start again in the chat.",
    }[out["status"]]
    return {"ok": out["status"] != "failed", "status": out["status"], "message": msg, "tx_hash": tx_hash,
            "newly_confirmed": out.get("newly", False), "intent_id": intent["id"]}


# ── confirmation: the chain, never the client ────────────────────────────────


def _int(data: str) -> int:
    h = (data or "0x")[2:] or "0"
    return int(h[:64] or "0", 16)


def _log_matches(intent: dict, log: dict) -> bool:
    t = [x.lower() for x in log.get("topics") or []]
    addr = str(log.get("address") or "").lower()
    s = config.chain_settings(intent["chain"])
    raw = int(intent["amount_micro"])
    acct = C.addr_topic(intent["account"])
    if intent["action"] in ("lock_create", "lock_join"):
        if addr != str((intent.get("detail") or {}).get("escrow") or s["escrow"]).lower() or len(t) < 3:
            return False
        mid = C.match_id_hex(intent["challenge_id"]).lower()
        if intent["action"] == "lock_create":
            return t[0] == C.MATCH_CREATED_TOPIC and t[1] == mid and t[2] == acct and _int(log.get("data")) == raw
        return t[0] == C.MATCH_JOINED_TOPIC and t[1] == mid and t[2] == acct
    if intent["action"] == "withdraw":
        usdc = str((intent.get("detail") or {}).get("usdc") or s["usdc"]).lower()
        return (addr == usdc and len(t) >= 3 and t[0] == C.TRANSFER_TOPIC and t[1] == acct
                and t[2] == C.addr_topic(intent["to_address"]) and _int(log.get("data")) == raw)
    return False


def _search_topics(intent: dict) -> tuple[str, list[Optional[str]]]:
    s = config.chain_settings(intent["chain"])
    acct = C.addr_topic(intent["account"])
    if intent["action"] == "lock_create":
        return s["escrow"], [C.MATCH_CREATED_TOPIC, C.match_id_hex(intent["challenge_id"]), acct]
    if intent["action"] == "lock_join":
        return s["escrow"], [C.MATCH_JOINED_TOPIC, C.match_id_hex(intent["challenge_id"]), acct]
    return s["usdc"], [C.TRANSFER_TOPIC, acct, C.addr_topic(intent["to_address"])]


def confirm(intent_id: str, *, reader=None) -> dict:
    """``{"status": confirmed|pending|failed, "newly": bool}``. Sync."""
    intent = store.get(intent_id)
    if intent is None:
        return {"status": "failed", "newly": False}
    if intent["status"] == "confirmed":
        return {"status": "confirmed", "newly": False}
    if intent["status"] in ("failed",):
        return {"status": "failed", "newly": False}
    reader = reader or chain.get_reader()
    found: Optional[dict] = None
    if intent.get("tx_hash"):
        try:
            rec = reader.receipt(intent["tx_hash"])
        except Exception:
            logger.warning("[self_custody] receipt read failed", exc_info=True)
            rec = None
        if rec is None:
            return {"status": "pending", "newly": False}
        if int(rec.get("status") or 0) != 1:
            store.transition(intent_id, "failed", expect=("submitted", "prepared"),
                             detail={**(intent.get("detail") or {}), "failure": "reverted"})
            return {"status": "failed", "newly": False}
        found = next((lg for lg in rec.get("logs") or [] if _log_matches(intent, lg)), None)
        if found is None:
            # A successful transaction without our event (some other tx's
            # hash): never advance on it. Forget the claimed hash and let the
            # log scan (now and in the watcher) find the real one, if any.
            logger.warning("[self_custody] tx %s has no matching event for %s", intent["tx_hash"], intent_id)
            store.transition(intent_id, "submitted", expect=("submitted", "prepared"), tx_hash=None,
                             detail={**(intent.get("detail") or {}), "ignored_tx": intent["tx_hash"]})
            intent = store.get(intent_id) or intent
        else:
            found = {**found, "transactionHash": rec.get("transactionHash") or intent["tx_hash"]}
    if found is None:
        addr, topics = _search_topics(intent)
        try:
            logs = reader.logs(addr, topics, int(intent.get("from_block") or 0))
        except Exception:
            logger.warning("[self_custody] log scan failed", exc_info=True)
            return {"status": "pending", "newly": False}
        found = next((lg for lg in logs if _log_matches(intent, lg)), None)
        if found is None:
            return {"status": "pending", "newly": False}
    tx = str(found.get("transactionHash") or intent.get("tx_hash") or "").lower()
    if tx and store.tx_hash_taken(tx, intent_id):
        store.transition(intent_id, "failed", expect=("submitted", "prepared"),
                         detail={**(intent.get("detail") or {}), "failure": "tx_reused"})
        return {"status": "failed", "newly": False}
    moved = store.transition(intent_id, "confirmed", expect=("prepared", "submitted"),
                             tx_hash=tx or None, confirmed_at_ms=store.now_ms())
    if moved:
        _apply(store.get(intent_id) or intent)
    return {"status": "confirmed", "newly": moved}


def _apply(intent: dict) -> None:
    """Advance the match exactly like the custodial lock does, once."""
    if intent["action"] not in ("lock_create", "lock_join"):
        return
    from gaming.src.backend.services import clawstation_escrow as esc

    cid = intent["challenge_id"]
    creator = intent["action"] == "lock_create"
    tx = intent.get("tx_hash") or ""
    ref = f"userop:{intent.get('user_op_hash') or tx}"
    try:
        ch = esc._load_challenge(cid)
    except Exception:
        logger.exception("[self_custody] lock confirmed but challenge %s unreadable", cid)
        return
    expected = ("open", "accepted") if creator else ("accepted", "creator_locked")
    done_col = "creator_lock_tx_id" if creator else "opponent_lock_tx_id"
    if ch.get(done_col):
        return
    amount = C.from_raw(intent["amount_micro"])
    esc._record_audit(
        challenge_id=cid, profile_id=intent["profile_id"], movement="lock_in", amount=amount,
        idempotency_key=f"approve-{'create' if creator else 'join'}-{cid}", circle_tx_id=ref, tx_hash=tx,
        status="confirmed",
        metadata={"side": "creator" if creator else "opponent", "self_custody": True,
                  "account": intent["account"], "intent_id": intent["id"], "chain": intent["chain"]},
    )
    if ch.get("status") not in expected:
        # Money is in escrow but the match moved on (e.g. cancelled): never
        # overwrite; the escrow's refund paths return it to this account.
        logger.error("[self_custody] lock %s confirmed on a %s match %s: needs review",
                     intent["id"], ch.get("status"), cid)
        return
    if creator:
        esc._update_challenge(cid, {"status": "creator_locked", "creator_lock_tx_id": ref,
                                    "creator_lock_tx_hash": tx})
    else:
        esc._update_challenge(cid, {"status": "locked", "opponent_id": intent["profile_id"],
                                    "opponent_lock_tx_id": ref, "opponent_lock_tx_hash": tx})


async def confirm_and_notify(intent_id: str) -> dict:
    out = await asyncio.to_thread(confirm, intent_id)
    if out.get("newly"):
        from gaming.src.backend.services.self_custody import notices

        await notices.confirmed(intent_id)
    return out


# ── the watcher ──────────────────────────────────────────────────────────────


def due(now_ms: Optional[int] = None) -> list[dict]:
    return store.find(statuses=store.OPEN, limit=200)


async def sweep(now_ms: Optional[int] = None) -> dict[str, int]:
    """Confirm open intents from the chain; expire old prepared ones."""
    now = now_ms if now_ms is not None else store.now_ms()
    counts = {"confirmed": 0, "pending": 0, "failed": 0, "expired": 0}
    for it in await asyncio.to_thread(due, now):
        out = await confirm_and_notify(it["id"])
        st = out["status"]
        if st == "pending" and it["status"] == "prepared" and now > int(it["expires_at_ms"]) + EXPIRE_GRACE_MS:
            if await asyncio.to_thread(store.transition, it["id"], "expired", expect=("prepared",)):
                st = "expired"
        counts[st] = counts.get(st, 0) + 1
    return counts


INTERVAL_SEC = 20.0


async def _loop(interval: float) -> None:
    while True:
        try:
            await sweep()
        except Exception:
            logger.exception("[self_custody] sweep failed")
        await asyncio.sleep(interval)


def start_worker(interval: float = INTERVAL_SEC) -> Optional[asyncio.Task]:
    """Started from the API's startup hook; does nothing while the flag is off."""
    if not config.enabled():
        return None
    return asyncio.get_running_loop().create_task(_loop(interval))
