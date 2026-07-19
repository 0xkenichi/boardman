"""
Platform gas tank for chains that need native gas (Base ETH, Avalanche AVAX).

Arc does not need this — gas is paid in USDC.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from gaming.src.backend.services.chains import gas_tank_required, get_chain

logger = logging.getLogger(__name__)


def ensure_native_gas(chain_id: str, wallet_address: str) -> dict:
    """
    If chain requires a gas tank and the wallet is below min balance,
    top up from ADMIN_PRIVATE_KEY.

    Returns ``{"ok": bool, "action": str, "tx_hash": optional, "error": optional}``.
    """
    if not gas_tank_required(chain_id):
        return {"ok": True, "action": "skipped_usdc_gas_chain"}

    chain = get_chain(chain_id)
    min_wei = int(chain.get("gas_tank_min_wei") or "0")
    topup_wei = int(chain.get("gas_tank_topup_wei") or min_wei)
    rpc = chain["rpc_url"]

    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError as exc:
        return {"ok": False, "action": "error", "error": f"web3 missing: {exc}"}

    pk = os.getenv("ADMIN_PRIVATE_KEY") or os.getenv("GAS_TANK_PRIVATE_KEY")
    if not pk:
        logger.warning("[GasTank] No ADMIN_PRIVATE_KEY — cannot top up %s", chain_id)
        return {"ok": False, "action": "no_admin_key", "error": "ADMIN_PRIVATE_KEY not set"}
    if not pk.startswith("0x"):
        pk = "0x" + pk

    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        return {"ok": False, "action": "rpc_fail", "error": f"Cannot connect to {rpc}"}

    try:
        to = Web3.to_checksum_address(wallet_address)
    except Exception as exc:
        return {"ok": False, "action": "bad_address", "error": f"Invalid wallet address: {exc}"}
    bal = w3.eth.get_balance(to)
    if bal >= min_wei:
        return {
            "ok": True,
            "action": "already_funded",
            "balance_wei": str(bal),
        }

    acct = Account.from_key(pk)
    admin_bal = w3.eth.get_balance(acct.address)
    if admin_bal < topup_wei + w3.to_wei(0.00005, "ether"):
        return {
            "ok": False,
            "action": "admin_low",
            "error": f"Gas tank low on {chain_id}: admin has {admin_bal} wei",
        }

    try:
        nonce = w3.eth.get_transaction_count(acct.address)
        # EIP-1559 with modest fees; works on Base/Avalanche C-Chain.
        tx = {
            "to": to,
            "value": topup_wei,
            "gas": 21000,
            "maxFeePerGas": w3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": w3.to_wei(0.2, "gwei"),
            "nonce": nonce,
            "chainId": int(chain["chain_id"]),
            "type": 2,
        }
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
        h = w3.eth.send_raw_transaction(raw)
        rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=120)
        logger.info(
            "[GasTank] Topped up %s on %s tx=%s status=%s",
            to,
            chain_id,
            h.hex(),
            rcpt.status,
        )
        return {
            "ok": rcpt.status == 1,
            "action": "topped_up",
            "tx_hash": h.hex(),
            "amount_wei": str(topup_wei),
        }
    except Exception as exc:
        logger.exception("[GasTank] Top-up failed chain=%s to=%s", chain_id, wallet_address)
        return {"ok": False, "action": "tx_failed", "error": str(exc)}
