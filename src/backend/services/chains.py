"""
Multi-chain config for ClawStation / Rematch.

Product posture (now):
  - testnet only
  - Arc enabled for users
  - Avalanche next (config kept, enabled: false)
  - Base legacy (enabled: false)

Phase C (disabled): bridge-on-behalf + extra fee cut.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "chains.yaml"

# Built-in fallback if PyYAML is not installed or file is missing.
_FALLBACK_CHAINS: dict[str, Any] = {
    "default_settlement_chain": "arc",
    "chains": {
        "arc": {
            "id": "arc",
            "label": "Arc Testnet",
            "enabled": True,
            "recommended": True,
            "status": "live",
            "circle_blockchain": "ARC-TESTNET",
            "chain_id": 5042002,
            "rpc_url": "https://rpc.testnet.arc.network",
            "explorer_tx": "https://testnet.arcscan.app/tx/",
            "usdc_address": "0x3600000000000000000000000000000000000000",
            "circle_usdc_token_id": "",
            "gas_token": "USDC",
            "gas_mode": "usdc_native",
            "gas_tank_required": False,
            "escrow_address": "0xFC44a06295d4fC58420027932A6FcB3C13D83859",
        },
        "avalanche": {
            "id": "avalanche",
            "label": "Avalanche Fuji",
            "enabled": False,
            "recommended": False,
            "status": "next",
            "circle_blockchain": "AVAX-FUJI",
            "chain_id": 43113,
            "rpc_url": "https://api.avax-test.network/ext/bc/C/rpc",
            "explorer_tx": "https://testnet.snowtrace.io/tx/",
            "usdc_address": "0x5425890298aed601595a70AB815c96711a31Bc65",
            "circle_usdc_token_id": "",
            "gas_token": "AVAX",
            "gas_mode": "native_avax",
            "gas_tank_required": True,
            "gas_tank_min_wei": "10000000000000000",
            "gas_tank_topup_wei": "50000000000000000",
            "escrow_address": "0xFC44a06295d4fC58420027932A6FcB3C13D83859",
        },
        "base": {
            "id": "base",
            "label": "Base Sepolia",
            "enabled": False,
            "recommended": False,
            "status": "legacy",
            "circle_blockchain": "BASE-SEPOLIA",
            "chain_id": 84532,
            "rpc_url": "https://sepolia.base.org",
            "explorer_tx": "https://sepolia.basescan.org/tx/",
            "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            "circle_usdc_token_id": "bdf128b4-827b-5267-8f9e-243694989b5f",
            "gas_token": "ETH",
            "gas_mode": "native_eth",
            "gas_tank_required": True,
            "gas_tank_min_wei": "100000000000000",
            "gas_tank_topup_wei": "1000000000000000",
            "escrow_address": "0xDb76714390ccE1729558DF3c9EC4f45A1690dE78",
        },
    },
    "bridge": {"enabled": False, "extra_fee_bps": 50},
}

# Env overrides for escrow addresses after deploy.
_ESCROW_ENV = {
    "arc": "CLAW_ESCROW_ADDRESS_ARC",
    "base": "CLAW_ESCROW_ADDRESS_BASE_SEPOLIA",
    "avalanche": "CLAW_ESCROW_ADDRESS_AVALANCHE",
}

_TOKEN_ENV = {
    "arc": "CIRCLE_USDC_TOKEN_ID_ARC",
    "base": "CIRCLE_USDC_TOKEN_ID",
    "avalanche": "CIRCLE_USDC_TOKEN_ID_AVALANCHE",
}

# Circle blockchain labels → our chain id
CIRCLE_TO_CHAIN = {
    "ARC-TESTNET": "arc",
    "BASE-SEPOLIA": "base",
    "AVAX-FUJI": "avalanche",
}

_ALIASES = {
    "base_sepolia": "base",
    "basesepolia": "base",
    "arc_testnet": "arc",
    "arctestnet": "arc",
    "avax": "avalanche",
    "avax_fuji": "avalanche",
    "fuji": "avalanche",
    "avalanche_fuji": "avalanche",
}


@lru_cache(maxsize=1)
def load_chains_config() -> dict[str, Any]:
    data: dict[str, Any]
    if yaml is not None and _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    else:
        import copy

        data = copy.deepcopy(_FALLBACK_CHAINS)

    chains = data.get("chains") or {}
    for chain_id, env_key in _ESCROW_ENV.items():
        if chain_id not in chains:
            continue
        env_val = os.getenv(env_key)
        if not env_val and chain_id == "base":
            env_val = os.getenv("CSC_ADDRESS")
        if env_val and env_val not in ("", "0x...", "0x0000"):
            chains[chain_id]["escrow_address"] = env_val

        token_env = _TOKEN_ENV.get(chain_id)
        if token_env and os.getenv(token_env):
            chains[chain_id]["circle_usdc_token_id"] = os.getenv(token_env)

        rpc_env = {
            "arc": "ARC_TESTNET_RPC_URL",
            "base": "BASE_SEPOLIA_RPC_URL",
            "avalanche": "AVALANCHE_FUJI_RPC_URL",
        }.get(chain_id)
        if rpc_env and os.getenv(rpc_env):
            chains[chain_id]["rpc_url"] = os.getenv(rpc_env)
    data["chains"] = chains
    return data


def reload_chains_config() -> dict[str, Any]:
    load_chains_config.cache_clear()
    return load_chains_config()


def _env_enabled_set() -> Optional[set[str]]:
    """Optional override: CLAW_ENABLED_CHAINS=arc or arc,avalanche."""
    raw = (os.getenv("CLAW_ENABLED_CHAINS") or "").strip().lower()
    if not raw:
        return None
    return {p.strip() for p in raw.split(",") if p.strip()}


def is_chain_enabled(chain_id: str) -> bool:
    """Whether a chain is offered for *new* user activity."""
    # Do not call normalize_chain_id() here — it may call default_chain_id() → recursion.
    cid = _ALIASES.get((chain_id or "").lower().strip(), (chain_id or "").lower().strip())
    chains = load_chains_config().get("chains") or {}
    if cid not in chains:
        return False
    env_set = _env_enabled_set()
    if env_set is not None:
        return cid in env_set
    # Default: explicit enabled flag (missing → True only for arc for safety)
    c = chains[cid]
    if "enabled" in c:
        return bool(c.get("enabled"))
    return cid == "arc"


def default_chain_id() -> str:
    cfg = load_chains_config()
    env_default = (os.getenv("CLAW_DEFAULT_CHAIN") or "").strip().lower()
    if env_default and is_chain_enabled(env_default):
        return normalize_chain_id(env_default)
    # Prefer default_settlement_chain if enabled
    preferred = cfg.get("default_settlement_chain") or "arc"
    if is_chain_enabled(preferred):
        return normalize_chain_id(preferred)
    for cid, c in (cfg.get("chains") or {}).items():
        if is_chain_enabled(cid) and c.get("escrow_address"):
            return cid
    for cid in (cfg.get("chains") or {}):
        if is_chain_enabled(cid):
            return cid
    return "arc"


def list_chains(*, include_disabled: bool = False) -> list[dict[str, Any]]:
    """User/product chain list. Pass include_disabled=True for ops/Stack full map."""
    cfg = load_chains_config()
    out = []
    for cid, c in (cfg.get("chains") or {}).items():
        row = {**c, "id": cid}
        row["enabled"] = is_chain_enabled(cid)
        if not include_disabled and not row["enabled"]:
            continue
        out.append(row)
    out.sort(
        key=lambda x: (
            0 if x.get("recommended") else 1,
            0 if x.get("enabled") else 1,
            x.get("id") or "",
        )
    )
    return out


def normalize_chain_id(chain_id: Optional[str]) -> str:
    cid = (chain_id or default_chain_id()).lower().strip()
    return _ALIASES.get(cid, cid)


def get_chain(chain_id: str, *, require_enabled: bool = False) -> dict[str, Any]:
    """Load chain config. require_enabled=True rejects disabled chains (new activity)."""
    cid = normalize_chain_id(chain_id)
    chains = load_chains_config().get("chains") or {}
    if cid not in chains:
        enabled_ids = [c["id"] for c in list_chains()]
        raise ValueError(
            f"Unsupported chain '{chain_id}'. "
            f"Live chains: {', '.join(enabled_ids) or 'none'} "
            f"(default: {default_chain_id()})"
        )
    if require_enabled and not is_chain_enabled(cid):
        raise ValueError(
            f"Chain '{cid}' is not live for users yet "
            f"(status={chains[cid].get('status') or 'disabled'}). "
            f"Use: {', '.join(c['id'] for c in list_chains()) or 'arc'}"
        )
    row = {**chains[cid], "id": cid}
    row["enabled"] = is_chain_enabled(cid)
    return row


def chain_has_escrow(chain_id: str) -> bool:
    try:
        c = get_chain(chain_id)
        addr = (c.get("escrow_address") or "").strip()
        return bool(addr and addr not in ("0x...", "0x0000"))
    except ValueError:
        return False


def get_escrow_address(chain_id: str) -> str:
    c = get_chain(chain_id)
    addr = (c.get("escrow_address") or "").strip()
    if not addr or addr in ("0x...", "0x0000"):
        raise ValueError(
            f"No ClawEscrow deployed for chain '{chain_id}'. "
            f"Set {_ESCROW_ENV.get(c['id'], 'CLAW_ESCROW_ADDRESS_*')} in .env "
            f"or deploy: npx hardhat run scripts/deploy_escrow.js --network <net>"
        )
    return addr


def get_usdc_address(chain_id: str) -> str:
    return get_chain(chain_id)["usdc_address"]


def get_rpc_url(chain_id: str) -> str:
    return get_chain(chain_id)["rpc_url"]


def get_circle_blockchain(chain_id: str) -> str:
    return get_chain(chain_id)["circle_blockchain"]


def get_circle_usdc_token_id(chain_id: str) -> str:
    c = get_chain(chain_id)
    tid = (c.get("circle_usdc_token_id") or "").strip()
    if not tid:
        # Fall back to global env / Base default used historically.
        tid = os.getenv("CIRCLE_USDC_TOKEN_ID", "bdf128b4-827b-5267-8f9e-243694989b5f")
    return tid


def get_explorer_tx(chain_id: str, tx_hash: str = "") -> str:
    base = get_chain(chain_id).get("explorer_tx") or ""
    if not tx_hash:
        return base
    return f"{base}{tx_hash}"


def circle_blockchains_for_wallets() -> list[str]:
    # Wallet fan-out only on live chains (Arc-only today)
    return [c["circle_blockchain"] for c in list_chains(include_disabled=False)]


def gas_tank_required(chain_id: str) -> bool:
    return bool(get_chain(chain_id).get("gas_tank_required"))


def bridge_config() -> dict[str, Any]:
    return load_chains_config().get("bridge") or {"enabled": False}


def format_chain_help() -> str:
    lines = [
        "Settlement network (testnet):",
        "  • arc — Arc Testnet ★ live (USDC gas)",
    ]
    # Roadmap hint without offering other chains
    disabled = list_chains(include_disabled=True)
    upcoming = [c for c in disabled if not c.get("enabled") and c.get("status") == "next"]
    if upcoming:
        lines.append(
            "  · next: "
            + ", ".join(f"{c['id']} ({c['label']})" for c in upcoming)
            + " — not ready yet"
        )
    lines.append("")
    lines.append(f"Default / only live chain: {default_chain_id()}")
    lines.append("Example: /challenge @rival 5 EAFC private arc")
    return "\n".join(lines)
