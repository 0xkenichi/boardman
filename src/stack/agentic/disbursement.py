"""House disbursement policy — the only legal way Boardman moves money.

Boardman is the venue cashier, not a wallet with a "send" button.

Hard rules:
  * The House never ERC-20 transfers. Contracts hold USDC.
  * The resolver key may only call BoardmanEscrow.resolveMatch / cancelMatch
    (and flagDispute, which moves nothing).
  * Every fund movement requires an AuthorizedDisbursement minted from a
    specific trigger: dual-lock, terminal game result, or documented abort.
  * Recipients are the two locked players (or the contract feeRecipient).
    The House cannot pick an address or an amount.
  * A missing / contradictory game result is a hard refuse, never a draw refund.

House cashier policy. Resolver signs BoardmanEscrow only.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from gaming.src.stack.agentic.agents.boardman.manifest import HOUSE_ID

# ── Triggers (the only reasons money may move) ────────────────────────────────

TRIGGER_DUAL_LOCK = "MATCH_DUAL_LOCK"
TRIGGER_RESOLVE_WIN = "MATCH_RESOLVE_WIN"
TRIGGER_RESOLVE_DRAW = "MATCH_RESOLVE_DRAW"
TRIGGER_CANCEL_ABORT = "MATCH_CANCEL_ABORT"
TRIGGER_SPECTATOR_SETTLE = "SPECTATOR_SETTLE"

ALLOWED_TRIGGERS = frozenset(
    {
        TRIGGER_DUAL_LOCK,
        TRIGGER_RESOLVE_WIN,
        TRIGGER_RESOLVE_DRAW,
        TRIGGER_CANCEL_ABORT,
        TRIGGER_SPECTATOR_SETTLE,
    }
)

# House resolver calldata — anything else is a random send.
HOUSE_ESCROW_SELECTORS = {
    "0x60ffcc74": "resolveMatch",  # resolveMatch(bytes32,address)
    "0xc82db8f9": "cancelMatch",  # cancelMatch(bytes32)
    "0x9a37e76b": "flagDispute",  # flagDispute(bytes32)
}
FORBIDDEN_SELECTORS = {
    "0xa9059cbb": "transfer",  # ERC-20 transfer(address,uint256)
    "0x095ea7b3": "approve",  # ERC-20 approve(address,uint256)
}

TERMINAL_WIN = frozenset({"white_win", "black_win", "p1_win", "p2_win"})
TERMINAL_DRAW = frozenset({"draw", "1/2-1/2"})
LOCKABLE_STATUSES = frozenset({"open", "partial_lock", "queued", "locking"})
SETTLEABLE_STATUSES = frozenset(
    {"locked", "playing", "queued", "settle_failed", "partial_lock"}
)
CONTRACT_MAX_STAKE_USDC = Decimal("10000")

POLICY_ID = "boardman.house.disbursement.v1"


class DisbursementDenied(ValueError):
    """House refused to move funds. Fail closed."""


@dataclass(frozen=True)
class AuthorizedDisbursement:
    """Capability token. Only authorize_* functions may construct this."""

    policy: str
    trigger: str
    action: str  # lock | resolve | cancel | spectator_settle
    match_id: str
    chain_id: str
    player_wallets: tuple[str, str]
    winner_wallet: Optional[str]
    result: str
    stake_usdc: str
    issued_at: str
    fingerprint: str

    def assert_for_resolve(
        self, match_id: str, winner_address: Optional[str], draw: bool
    ) -> None:
        if self.policy != POLICY_ID:
            raise DisbursementDenied("unknown disbursement policy")
        if self.match_id != match_id:
            raise DisbursementDenied("authorization match_id mismatch")
        if draw:
            if self.action != "cancel" or self.trigger not in {
                TRIGGER_RESOLVE_DRAW,
                TRIGGER_CANCEL_ABORT,
            }:
                raise DisbursementDenied("draw/abort requires cancel authorization")
            return
        if self.action != "resolve" or self.trigger != TRIGGER_RESOLVE_WIN:
            raise DisbursementDenied("win requires MATCH_RESOLVE_WIN authorization")
        if not winner_address or not self.winner_wallet:
            raise DisbursementDenied("resolve requires a winner wallet")
        if winner_address.lower() != self.winner_wallet.lower():
            raise DisbursementDenied("winner address does not match authorization")
        allowed = {w.lower() for w in self.player_wallets}
        if self.winner_wallet.lower() not in allowed:
            raise DisbursementDenied("winner is not a locked player")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "trigger": self.trigger,
            "action": self.action,
            "match_id": self.match_id,
            "chain_id": self.chain_id,
            "player_wallets": list(self.player_wallets),
            "winner_wallet": self.winner_wallet,
            "result": self.result,
            "stake_usdc": self.stake_usdc,
            "issued_at": self.issued_at,
            "fingerprint": self.fingerprint,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_addr(addr: Optional[str]) -> str:
    a = (addr or "").strip()
    if not a:
        raise DisbursementDenied("missing wallet address")
    if not a.startswith("0x"):
        a = "0x" + a
    if len(a) != 42:
        raise DisbursementDenied(f"invalid wallet address: {a}")
    return a.lower()


def _stake(match: dict[str, Any]) -> Decimal:
    try:
        stake = Decimal(str(match.get("stake_usdc") or "0"))
    except Exception as exc:
        raise DisbursementDenied("stake_usdc is not a number") from exc
    if stake <= 0:
        raise DisbursementDenied("stake must be positive")
    if stake > CONTRACT_MAX_STAKE_USDC:
        raise DisbursementDenied(
            f"stake {stake} exceeds BoardmanEscrow MAX_STAKE {CONTRACT_MAX_STAKE_USDC}"
        )
    return stake


def _players(match: dict[str, Any]) -> tuple[str, str]:
    a = _norm_addr(match.get("agent_a_wallet") or match.get("onchain_player1"))
    b = _norm_addr(match.get("agent_b_wallet") or match.get("onchain_player2"))
    if a == b:
        raise DisbursementDenied("both players resolve to the same wallet")
    return a, b


def _assert_not_house_player(match: dict[str, Any]) -> None:
    for key in ("agent_a_id", "agent_b_id", "white_agent_id", "black_agent_id"):
        if match.get(key) == HOUSE_ID:
            raise DisbursementDenied("Boardman House cannot be a player")
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    for aid in (match.get("agent_a_id"), match.get("agent_b_id")):
        rec = reg.get_agent(aid or "") or {}
        if rec.get("role") == "house":
            raise DisbursementDenied("a house-role agent cannot receive skill payouts")


def _fingerprint(**parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def _mint(
    *,
    trigger: str,
    action: str,
    match: dict[str, Any],
    winner_wallet: Optional[str],
    result: str,
) -> AuthorizedDisbursement:
    if trigger not in ALLOWED_TRIGGERS:
        raise DisbursementDenied(f"unknown trigger: {trigger}")
    mid = match.get("match_id") or ""
    if not mid or not str(mid).startswith("agm_"):
        raise DisbursementDenied("match_id is not a Boardman match")
    stake = _stake(match)
    players = _players(match)
    if winner_wallet:
        w = _norm_addr(winner_wallet)
        if w not in players:
            raise DisbursementDenied("winner wallet is not a match party")
    else:
        w = None
    return AuthorizedDisbursement(
        policy=POLICY_ID,
        trigger=trigger,
        action=action,
        match_id=mid,
        chain_id=str(match.get("chain_id") or "arc"),
        player_wallets=players,
        winner_wallet=w,
        result=result,
        stake_usdc=str(stake),
        issued_at=_now(),
        fingerprint=_fingerprint(
            trigger=trigger,
            action=action,
            match_id=mid,
            players=players,
            winner=w,
            result=result,
            stake=str(stake),
        ),
    )


def parse_terminal_result(
    result: dict[str, Any],
    *,
    white: dict[str, Any],
    black: dict[str, Any],
) -> tuple[str, Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Return (kind, winner, loser). kind is 'win' or 'draw'. Fail closed."""
    rcode = str(result.get("result") or "").strip().lower()
    if rcode in TERMINAL_DRAW:
        return "draw", None, None
    winner_id = result.get("winner_agent_id")
    if not winner_id:
        if rcode in {"white_win", "p1_win"}:
            winner_id = white.get("agent_id")
        elif rcode in {"black_win", "p2_win"}:
            winner_id = black.get("agent_id")
    if rcode not in TERMINAL_WIN or not winner_id:
        raise DisbursementDenied(
            f"result is not terminal (result={rcode!r} winner={winner_id!r}) — refuse to move funds"
        )
    white_id = white.get("agent_id")
    black_id = black.get("agent_id")
    if winner_id == white_id:
        winner, loser = white, black
    elif winner_id == black_id:
        winner, loser = black, white
    else:
        raise DisbursementDenied("winner_agent_id is not a player in this match")
    if rcode in {"white_win", "p1_win"} and winner_id != white_id:
        raise DisbursementDenied("winner_agent_id contradicts result code")
    if rcode in {"black_win", "p2_win"} and winner_id != black_id:
        raise DisbursementDenied("winner_agent_id contradicts result code")
    if winner.get("agent_id") == HOUSE_ID or loser.get("agent_id") == HOUSE_ID:
        raise DisbursementDenied("House cannot be a skill payout party")
    return "win", winner, loser


def authorize_skill_lock(match: dict[str, Any]) -> AuthorizedDisbursement:
    """Players lock their own stakes into BoardmanEscrow. House does not send."""
    if not match:
        raise DisbursementDenied("match not found")
    status = match.get("status")
    if status not in LOCKABLE_STATUSES:
        raise DisbursementDenied(f"cannot lock from status {status}")
    if match.get("agent_a_id") == match.get("agent_b_id"):
        raise DisbursementDenied("agents must be different")
    _assert_not_house_player(match)
    return _mint(
        trigger=TRIGGER_DUAL_LOCK,
        action="lock",
        match=match,
        winner_wallet=None,
        result="lock",
    )


def authorize_skill_settlement(
    match: dict[str, Any],
    result: dict[str, Any],
    *,
    white: dict[str, Any],
    black: dict[str, Any],
) -> AuthorizedDisbursement:
    """Mint a resolve/cancel capability from a terminal engine result."""
    if not match:
        raise DisbursementDenied("match not found")
    status = match.get("status")
    if status == "settled":
        raise DisbursementDenied("match already settled")
    if status not in SETTLEABLE_STATUSES:
        raise DisbursementDenied(f"cannot settle from status {status}")
    _assert_not_house_player(match)
    kind, winner, _loser = parse_terminal_result(result, white=white, black=black)
    if kind == "draw":
        return _mint(
            trigger=TRIGGER_RESOLVE_DRAW,
            action="cancel",
            match=match,
            winner_wallet=None,
            result="draw",
        )
    wallet = winner.get("wallet_address") if winner else None
    # Prefer the on-chain player address recorded at lock when keys drifted.
    if winner and match.get("white_agent_id") == winner.get("agent_id"):
        wallet = (
            match.get("onchain_player1")
            or (
                match.get("agent_a_wallet")
                if match.get("white_agent_id") == match.get("agent_a_id")
                else match.get("agent_b_wallet")
            )
            or wallet
        )
    elif winner:
        wallet = (
            match.get("onchain_player2")
            or (
                match.get("agent_b_wallet")
                if match.get("white_agent_id") == match.get("agent_a_id")
                else match.get("agent_a_wallet")
            )
            or wallet
        )
    return _mint(
        trigger=TRIGGER_RESOLVE_WIN,
        action="resolve",
        match=match,
        winner_wallet=wallet,
        result=str(result.get("result") or "win"),
    )


def authorize_replay_settlement(match: dict[str, Any]) -> AuthorizedDisbursement:
    """Ops replay for a match that already has a stored terminal result.

    Used by settle_stuck_matches.py — still requires the recorded result,
    still cannot pick an arbitrary winner.
    """
    if not match:
        raise DisbursementDenied("match not found")
    if match.get("status") not in {"settled", "settle_failed"}:
        raise DisbursementDenied(
            "replay only allowed for settled / settle_failed matches"
        )
    white_id = match.get("white_agent_id")
    black_id = match.get("black_agent_id")
    white_wallet = (
        match.get("onchain_player1")
        or (
            match.get("agent_a_wallet")
            if white_id == match.get("agent_a_id")
            else match.get("agent_b_wallet")
        )
    )
    black_wallet = (
        match.get("onchain_player2")
        or (
            match.get("agent_b_wallet")
            if white_id == match.get("agent_a_id")
            else match.get("agent_a_wallet")
        )
    )
    white = {"agent_id": white_id, "wallet_address": white_wallet}
    black = {"agent_id": black_id, "wallet_address": black_wallet}
    # Temporarily treat as settleable so authorize_skill_settlement accepts it.
    scratch = dict(match)
    scratch["status"] = "settle_failed"
    return authorize_skill_settlement(
        scratch,
        {
            "result": match.get("result"),
            "winner_agent_id": match.get("winner_agent_id"),
        },
        white=white,
        black=black,
    )


def authorize_abort(match: dict[str, Any], *, reason: str) -> AuthorizedDisbursement:
    """Refund both players before a result exists (lock failed / no-show)."""
    if not match:
        raise DisbursementDenied("match not found")
    if match.get("status") in {"settled", "playing"}:
        raise DisbursementDenied(
            f"cannot abort from status {match.get('status')} — wait for a game result"
        )
    if match.get("status") not in {
        "open",
        "partial_lock",
        "locked",
        "queued",
        "lock_failed",
        "locking",
    }:
        raise DisbursementDenied(f"cannot abort from status {match.get('status')}")
    why = (reason or "").strip().lower()
    if why not in {"no_show", "lock_failed", "never_started", "ops_abort"}:
        raise DisbursementDenied(
            "abort reason must be no_show | lock_failed | never_started | ops_abort"
        )
    _assert_not_house_player(match)
    return _mint(
        trigger=TRIGGER_CANCEL_ABORT,
        action="cancel",
        match=match,
        winner_wallet=None,
        result=f"abort:{why}",
    )


def winner_wallet_for_match(match: dict[str, Any]) -> Optional[str]:
    """Map stored winner_agent_id → the wallet that actually locked on-chain.

    Must not assume player1 == agent_a (white creates the match).
    """
    wid = match.get("winner_agent_id")
    if not wid:
        return None
    if wid == match.get("white_agent_id"):
        return (
            match.get("onchain_player1")
            or (
                match.get("agent_a_wallet")
                if match.get("white_agent_id") == match.get("agent_a_id")
                else match.get("agent_b_wallet")
            )
        )
    if wid == match.get("black_agent_id"):
        return (
            match.get("onchain_player2")
            or (
                match.get("agent_b_wallet")
                if match.get("white_agent_id") == match.get("agent_a_id")
                else match.get("agent_a_wallet")
            )
        )
    if wid == match.get("agent_a_id"):
        return match.get("agent_a_wallet")
    if wid == match.get("agent_b_id"):
        return match.get("agent_b_wallet")
    return None


def assert_house_escrow_call(tx: dict[str, Any], escrow_address: str, label: str) -> None:
    """Resolver may only call BoardmanEscrow resolve/cancel/flagDispute."""
    to = str(tx.get("to") or "").lower()
    if to != (escrow_address or "").lower():
        raise DisbursementDenied(
            f"House signer may only call BoardmanEscrow ({escrow_address}), not {to}"
        )
    data = tx.get("data") or tx.get("input") or ""
    if isinstance(data, (bytes, bytearray)):
        selector = "0x" + bytes(data[:4]).hex()
    else:
        s = str(data)
        selector = s[:10].lower() if s.startswith("0x") and len(s) >= 10 else ""
    if selector in FORBIDDEN_SELECTORS:
        raise DisbursementDenied(
            f"House signer cannot {FORBIDDEN_SELECTORS[selector]} — contracts hold the funds"
        )
    allowed = HOUSE_ESCROW_SELECTORS.get(selector)
    if selector and allowed is None:
        raise DisbursementDenied(
            f"House signer cannot call selector {selector} on escrow (label={label})"
        )
    if label not in {"resolveMatch", "cancelMatch", "flagDispute"}:
        raise DisbursementDenied(f"House signer cannot broadcast {label}")


def assert_not_resolver_funder(funder_key: str) -> None:
    """The resolver key is not a faucet. It must never ERC-20 transfer."""
    try:
        from gaming.src.stack.agentic.onchain import load_resolver_key
    except Exception:
        return
    try:
        resolver = load_resolver_key()
    except Exception:
        return
    a = funder_key.strip().lower()
    b = resolver.strip().lower()
    if not a.startswith("0x"):
        a = "0x" + a
    if not b.startswith("0x"):
        b = "0x" + b
    if a == b:
        raise DisbursementDenied(
            "BOARDMAN_RESOLVER_KEY cannot ERC-20 transfer. "
            "Set a separate BOARDMAN_FUNDER_KEY for the ops faucet."
        )


def assert_faucet_destination(to_address: str) -> None:
    """Faucet may only top up registered contestant wallets, never House."""
    dest = _norm_addr(to_address)
    house = house_public_wallet()
    if house and dest == _norm_addr(house):
        raise DisbursementDenied("cannot faucet the House / feeRecipient wallet")
    from gaming.src.stack.agentic.registry import get_registry

    allowed: set[str] = set()
    for rec in get_registry().list_agents():
        if rec.get("role") == "house" or rec.get("agent_id") == HOUSE_ID:
            continue
        w = rec.get("wallet_address")
        if w:
            allowed.add(w.lower())
    if dest not in allowed:
        raise DisbursementDenied(
            "faucet may only fund a registered contestant wallet"
        )


def onchain_explicitly_enabled() -> bool:
    v = os.getenv("BOARDMAN_AGENTIC_ONCHAIN", "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def allow_ledger_fallback() -> bool:
    """Demo-only. Default off when on-chain is requested — no silent honeypot."""
    return os.getenv("BOARDMAN_ALLOW_LEDGER_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_onchain_settlement(match: dict[str, Any]) -> bool:
    if not onchain_explicitly_enabled() and match.get("settlement_mode") != "onchain":
        return False
    if allow_ledger_fallback() and not match.get("onchain"):
        return False
    if match.get("onchain") or match.get("settlement_mode") == "onchain":
        return True
    return onchain_explicitly_enabled()


def configured_escrow_address(chain_id: str = "arc") -> str:
    env = (
        os.getenv("BOARDMAN_ESCROW_ADDRESS_ARC")
        or os.getenv("CLAW_ESCROW_ADDRESS_ARC")
        or ""
    ).strip()
    if env:
        return env
    dep = _deployment()
    addr = ((dep.get("contracts") or {}).get("BoardmanEscrow")) or ""
    return addr or "0xD8984396f12Cd0BD3C3e120858dd7eCdEeEF66Fc"


def house_public_wallet() -> Optional[str]:
    """Venue address (feeRecipient). Not a spend key."""
    env = (
        os.getenv("BOARDMAN_HOUSE_WALLET")
        or os.getenv("BOARDMAN_FEE_RECIPIENT")
        or ""
    ).strip()
    if env:
        return env
    dep = _deployment()
    return (dep.get("config") or {}).get("feeRecipient")


def _deployment() -> dict[str, Any]:
    here = Path(__file__).resolve()
    root = here.parents[3]
    path = root / "contracts" / "deployments" / "boardman_v1_arcTestnet.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def seal_house_secrets() -> None:
    """House has no spend key on disk. Resolver key stays in process env."""
    from gaming.src.stack.agentic.store import save_json

    save_json(
        f"secrets_{HOUSE_ID}.json",
        {
            "private_key": None,
            "sealed": True,
            "policy": POLICY_ID,
            "note": (
                "House has no spend key. BOARDMAN_RESOLVER_KEY lives in process "
                "env and may only sign BoardmanEscrow resolveMatch/cancelMatch "
                f"after an {POLICY_ID} authorization."
            ),
        },
    )


def public_policy() -> dict[str, Any]:
    return {
        "policy": POLICY_ID,
        "can_erc20_transfer": False,
        "can_pick_recipient": False,
        "can_pick_amount": False,
        "funds_held_by": "BoardmanEscrow",
        "escrow_contract": configured_escrow_address(),
        "house_wallet": house_public_wallet(),
        "house_wallet_role": "fee_recipient",
        "allowed_triggers": sorted(ALLOWED_TRIGGERS),
        "allowed_house_calls": sorted(set(HOUSE_ESCROW_SELECTORS.values())),
        "forbidden_house_calls": sorted(set(FORBIDDEN_SELECTORS.values())),
        "onchain_required": onchain_explicitly_enabled(),
        "ledger_fallback": allow_ledger_fallback(),
        "contract_max_stake_usdc": str(CONTRACT_MAX_STAKE_USDC),
        "fee_bps": 700,
    }
