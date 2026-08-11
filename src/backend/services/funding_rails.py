"""
Abstract multi-rail USDC for Boardman.

Players see one "play balance". Under the hood:
  - settlement rail (Arc): can stake, USDC gas, BoardmanEscrow
  - funding rails (Stellar, Avalanche, Paystack, bank): money in → convert to Arc

Stakes ALWAYS require spendable USDC on the settlement rail unless a rail
is marked can_stake + usdc_gas (only Arc today).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "funding_rails.yaml"


@lru_cache(maxsize=1)
def load_funding_config() -> dict[str, Any]:
    if yaml is not None and _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {
        "settlement_rail": "arc",
        "require_settlement_for_stake": True,
        "rails": {
            "arc": {
                "id": "arc",
                "kind": "settlement",
                "enabled": True,
                "can_stake": True,
                "usdc_gas": True,
                "player_label": "Play wallet",
                "deposit_mode": "play_address",
            }
        },
        "player_copy": {
            "balance_label": "Play balance",
            "settlement_label": "ready to play",
            "pending_label": "on the way / other wallet",
            "convert_hint": "We'll move it into play money before your next stake.",
        },
        "bridge": {
            "auto_convert_to_settlement": False,
            "mode": "manual_ops",
            "target": "arc",
        },
    }


def reload_funding_config() -> dict[str, Any]:
    load_funding_config.cache_clear()
    return load_funding_config()


def settlement_rail_id() -> str:
    cfg = load_funding_config()
    return (os.getenv("BOARDMAN_SETTLEMENT_RAIL") or cfg.get("settlement_rail") or "arc").strip().lower()


def player_copy() -> dict[str, str]:
    return dict(load_funding_config().get("player_copy") or {})


def list_rails(*, funding_only: bool = False, enabled_only: bool = True) -> list[dict[str, Any]]:
    rails = load_funding_config().get("rails") or {}
    out = []
    for rid, row in rails.items():
        r = dict(row or {})
        r["id"] = r.get("id") or rid
        if enabled_only and not r.get("enabled", True):
            continue
        if funding_only and r.get("kind") == "settlement" and r.get("deposit_mode") == "play_address":
            # still include arc as "crypto play address" path separately
            pass
        if funding_only and not r.get("kind") in ("funding", "settlement"):
            continue
        out.append(r)
    return out


def get_rail(rail_id: str) -> Optional[dict[str, Any]]:
    rid = (rail_id or "").strip().lower()
    rails = load_funding_config().get("rails") or {}
    if rid in rails:
        r = dict(rails[rid])
        r["id"] = rid
        return r
    return None


def rail_can_stake(rail_id: str) -> bool:
    r = get_rail(rail_id)
    if not r:
        return False
    return bool(r.get("can_stake")) and bool(r.get("usdc_gas") or rail_id == settlement_rail_id())


def _clean_env_addr(raw: str) -> str:
    """Drop empty / FILL_ME placeholders so watchers don't treat them as live."""
    v = (raw or "").strip().strip('"').strip("'")
    if not v:
        return ""
    up = v.upper()
    if up.startswith("FILL_ME") or up in ("TODO", "CHANGE_ME", "YOUR_KEY_HERE", "XXX"):
        return ""
    return v


def ops_deposit_address(rail_id: str) -> str:
    """Where users send USDC on a funding rail (ops treasury)."""
    r = get_rail(rail_id) or {}
    env_key = (r.get("env_ops_address") or "").strip()
    if env_key:
        got = _clean_env_addr(os.getenv(env_key) or "")
        if got:
            return got
    # Shared Boardman ops EOA works for EVM funding rails until split
    if rail_id in ("avalanche", "base", "arc"):
        return _clean_env_addr(
            os.getenv("BOARDMAN_OPS_USDC_ADDRESS")
            or os.getenv("BOARDMAN_FEE_RECIPIENT")
            or ""
        )
    if rail_id == "stellar":
        return _clean_env_addr(os.getenv("BOARDMAN_OPS_USDC_STELLAR") or "")
    return ""


def stellar_memo_for_ref(topup_ref: str) -> str:
    """Stellar memo text — must stay short (max 28 bytes for MEMO_TEXT)."""
    prefix = (os.getenv("BOARDMAN_STELLAR_MEMO_PREFIX") or "BM").strip()[:4]
    ref = re.sub(r"[^A-Za-z0-9]", "", topup_ref or "")[:20]
    memo = f"{prefix}{ref}"[:28]
    return memo or prefix


def stellar_network() -> str:
    return (os.getenv("STELLAR_NETWORK") or "testnet").strip().lower()


def stellar_horizon_url() -> str:
    explicit = (os.getenv("STELLAR_HORIZON_URL") or "").strip()
    if explicit:
        return explicit
    if stellar_network() in ("public", "mainnet", "pubnet"):
        return "https://horizon.stellar.org"
    return "https://horizon-testnet.stellar.org"


def funding_rail_enabled(rail_id: str) -> bool:
    r = get_rail(rail_id)
    if not r or not r.get("enabled", True):
        return False
    if rail_id == "stellar":
        # Show if configured OR always as "coming" instructions with ops addr
        return bool(ops_deposit_address("stellar") or os.getenv("STELLAR_SHOW_ALWAYS", "1") == "1")
    if rail_id == "avalanche":
        return bool(ops_deposit_address("avalanche") or os.getenv("BOARDMAN_OPS_USDC_ADDRESS"))
    return True


@dataclass
class AbstractBalance:
    """Player-facing money snapshot — one number, optional breakdown."""

    play_usdc: Decimal = Decimal("0")  # spendable on settlement rail
    other_usdc: Decimal = Decimal("0")  # same chain other addresses / linked
    ledger_usdc: Decimal = Decimal("0")
    play_address: str = ""
    settlement_rail: str = "arc"
    balance_error: Optional[str] = None
    rails: dict[str, Decimal] = field(default_factory=dict)

    @property
    def total_known(self) -> Decimal:
        return (self.play_usdc or Decimal("0")) + (self.other_usdc or Decimal("0"))

    def as_dict(self) -> dict[str, Any]:
        copy = player_copy()
        return {
            "play_usdc": float(self.play_usdc),
            "other_usdc": float(self.other_usdc),
            "ledger_usdc": float(self.ledger_usdc),
            "total_known": float(self.total_known),
            "play_address": self.play_address,
            "settlement_rail": self.settlement_rail,
            "balance_error": self.balance_error,
            "rails": {k: float(v) for k, v in self.rails.items()},
            "labels": copy,
            # Back-compat with get_balance_summary consumers
            "spendable_usdc": float(self.play_usdc),
            "address": self.play_address,
            "chain_id": self.settlement_rail,
        }


async def get_abstract_balance(user_id: str) -> AbstractBalance:
    """Single play balance on settlement rail (Arc). Chain names stay internal."""
    from gaming.src.backend.services.clawstation_circle import get_balance_summary

    settle = settlement_rail_id()
    summary = await get_balance_summary(user_id, chain_id=settle)
    play = Decimal(str(summary.get("spendable_usdc") or 0))
    other = Decimal(str(summary.get("other_usdc") or 0))
    ledger = Decimal(str(summary.get("ledger_usdc") or 0))
    return AbstractBalance(
        play_usdc=play,
        other_usdc=other,
        ledger_usdc=ledger,
        play_address=summary.get("address") or "",
        settlement_rail=settle,
        balance_error=summary.get("balance_error"),
        rails={settle: play},
    )


@dataclass
class StakeReadiness:
    ok: bool
    amount_usdc: Decimal
    play_usdc: Decimal
    shortfall: Decimal = Decimal("0")
    settlement_rail: str = "arc"
    needs_convert: bool = False
    message_html: str = ""


async def ensure_stake_ready(user_id: str, amount_usdc: float | Decimal) -> StakeReadiness:
    """
    Stakes require USDC on the settlement rail (Arc).

    Funding-rail balances are NOT stakeable until converted.
    """
    amount = Decimal(str(amount_usdc)).quantize(Decimal("0.01"))
    bal = await get_abstract_balance(user_id)
    settle = bal.settlement_rail
    play = bal.play_usdc
    short = amount - play if play < amount else Decimal("0")
    copy = player_copy()

    if short <= 0:
        return StakeReadiness(
            ok=True,
            amount_usdc=amount,
            play_usdc=play,
            settlement_rail=settle,
            message_html="",
        )

    # Could scan other EVM wallets later; for now abstract = Arc play only
    msg = (
        f"You need <b>${amount:,.2f}</b> play money to lock this stake.\n"
        f"{copy.get('balance_label', 'Play balance')}: <b>${play:,.2f}</b> "
        f"({copy.get('settlement_label', 'ready to play')}).\n"
        f"Short by <b>${short:,.2f}</b>.\n\n"
        f"Tap <b>Get money</b> — Naira, Stellar USDC, Avalanche USDC, or crypto all "
        f"credit the same play balance. "
        f"{copy.get('convert_hint', '')}"
    )
    return StakeReadiness(
        ok=False,
        amount_usdc=amount,
        play_usdc=play,
        shortfall=short,
        settlement_rail=settle,
        needs_convert=False,
        message_html=msg,
    )


def funding_instructions_html(
    rail_id: str,
    *,
    play_address: str = "",
    topup_ref: str = "",
    amount_usdc: Optional[float] = None,
) -> str:
    """Player-facing deposit instructions — minimal chain jargon."""
    r = get_rail(rail_id) or {}
    label = r.get("player_label") or rail_id
    amt = f"${amount_usdc:,.2f} " if amount_usdc else ""
    copy = player_copy()

    if rail_id == "arc" or r.get("deposit_mode") == "play_address":
        addr = play_address or "(open Wallet after /start)"
        return (
            f"🪙 <b>Fund with crypto</b>\n\n"
            f"Send {amt}USDC to your <b>play address</b> (this is your Boardman wallet):\n"
            f"<code>{_esc(addr)}</code>\n\n"
            f"Network: Arc (USDC). After it lands, balance updates — "
            f"you don't need to switch chains to play.\n\n"
            f"<i>{copy.get('convert_hint', '')}</i>"
        )

    if rail_id == "stellar":
        dest = ops_deposit_address("stellar")
        memo = stellar_memo_for_ref(topup_ref) if topup_ref else stellar_memo_for_ref("TOPUP")
        if not dest:
            return (
                f"⭐ <b>Fund with USDC (link)</b>\n\n"
                f"This option is almost ready. "
                f"For now use <b>Pay with Naira</b> or <b>Crypto / play address</b>.\n"
                f"<i>Ops: set BOARDMAN_OPS_USDC_STELLAR (Stellar public key).</i>"
            )
        return (
            f"⭐ <b>Fund with USDC (link)</b>\n\n"
            f"1. Send {amt}<b>USDC</b> to:\n"
            f"<code>{_esc(dest)}</code>\n\n"
            f"2. Put this exact <b>memo</b> (required):\n"
            f"<code>{_esc(memo)}</code>\n\n"
            f"3. We detect it automatically and credit your <b>play balance</b> "
            f"(same money you stake with).\n\n"
            f"Ref: <code>{_esc(topup_ref or '—')}</code>\n"
            f"<i>You don't need to pick a network to play — just fund and stake.</i>"
        )

    if rail_id == "avalanche":
        dest = ops_deposit_address("avalanche")
        if not dest:
            return (
                f"🔺 <b>Fund with USDC (alt)</b>\n\n"
                f"Not configured yet. Use Pay with Naira or play address."
            )
        ref = topup_ref or "RM-XXXX"
        return (
            f"🔺 <b>Fund with USDC (alt)</b>\n\n"
            f"1. Send {amt}<b>USDC</b> to:\n"
            f"<code>{_esc(dest)}</code>\n\n"
            f"2. Include this ref in the note / screenshot:\n"
            f"<code>{_esc(ref)}</code>\n\n"
            f"3. We move it into your <b>play balance</b> so you can stake.\n\n"
            f"<i>One play balance for all matches — funding path is just plumbing.</i>"
        )

    return f"Unknown funding option: {rail_id}"


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def abstract_balance_html(bal: AbstractBalance) -> str:
    copy = player_copy()
    label = copy.get("balance_label", "Play balance")
    ready = copy.get("settlement_label", "ready to play")
    pending = copy.get("pending_label", "other")
    lines = [
        f"💰 <b>{label}: ${bal.play_usdc:,.2f}</b>",
        f"<i>{ready}</i>",
    ]
    if bal.other_usdc > Decimal("0.009"):
        lines.append(
            f"⚠️ ${bal.other_usdc:,.2f} {pending} — move to play address to stake."
        )
    if bal.play_address:
        lines.append(f"\nPlay address:\n<code>{_esc(bal.play_address)}</code>")
    return "\n".join(lines)
