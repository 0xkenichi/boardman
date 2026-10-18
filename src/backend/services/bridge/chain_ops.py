"""On-chain operations the naira rail needs, behind one small interface.

``CircleChainOps`` is the real implementation: Circle developer-controlled
wallets (contractExecution / transfer) plus Circle's Iris attestation API.
Every call that moves money takes a deterministic idempotency key, so a
retry after a crash or timeout cannot execute twice (Circle dedups on it).

Tests install a fake with ``set_chain_ops``; nothing here runs in tests.

CCTP v2 calls (https://developers.circle.com/cctp/references/contract-interfaces):
  USDC.approve(TokenMessengerV2, amount)
  TokenMessengerV2.depositForBurn(uint256 amount, uint32 destinationDomain,
      bytes32 mintRecipient, address burnToken, bytes32 destinationCaller,
      uint256 maxFee, uint32 minFinalityThreshold)      1000 = fast, 2000 = standard
  MessageTransmitterV2.receiveMessage(bytes message, bytes attestation)
Iris: GET /v2/messages/{sourceDomain}?transactionHash=…  → message + attestation
      GET /v2/burn/USDC/fees/{sourceDomain}/{destDomain}   → minimumFee (bps) per finality
"""
from __future__ import annotations

import logging
import uuid
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

MICRO = Decimal("1000000")
FINALITY_FAST = 1000
FINALITY_STANDARD = 2000
ZERO32 = "0x" + "00" * 32


def atoms(amount: Decimal) -> int:
    return int((Decimal(amount) * MICRO).to_integral_value(rounding=ROUND_DOWN))


def to_bytes32(address: str) -> str:
    a = (address or "").lower().removeprefix("0x")
    if len(a) != 40:
        raise ValueError("not an EVM address")
    return "0x" + "0" * 24 + a


def idem_uuid(key: str) -> str:
    """Circle wants a UUID idempotency key: derive one deterministically."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"boardman:{key}"))


class ChainOpsError(Exception):
    pass


class ChainOps(Protocol):
    def create_wallet(self, chain: str, profile_id: str, account_type: str, idem: str) -> tuple[str, str]: ...
    def usdc_balance(self, chain: str, address: str) -> Decimal: ...
    def ensure_gas(self, chain: str, address: str) -> None: ...
    def transfer_usdc(self, chain: str, wallet_id: str, to: str, amount: Decimal, idem: str) -> str: ...
    def approve_burn(self, chain: str, wallet_id: str, amount: Decimal, idem: str) -> str: ...
    def burn(self, chain: str, wallet_id: str, amount: Decimal, dst_domain: int, mint_recipient: str,
             max_fee: Decimal, fast: bool, idem: str) -> str: ...
    def tx_status(self, chain: str, tx_id: str) -> tuple[str, str]: ...
    def fetch_message(self, src_chain: str, burn_tx_hash: str) -> dict[str, Any]: ...
    def mint(self, dst_chain: str, relayer_wallet_id: str, message: str, attestation: str, idem: str) -> str: ...
    def fast_fee_bps(self, src_chain: str, dst_chain: str) -> Optional[Decimal]: ...


class CircleChainOps:
    """Real chain operations. Requires CIRCLE_API_KEY / CIRCLE_ENTITY_SECRET."""

    def _circle(self, chain: str):
        from gaming.src.backend.services.clawstation_circle import _circle_for_chain

        return _circle_for_chain(chain)

    def create_wallet(self, chain: str, profile_id: str, account_type: str, idem: str) -> tuple[str, str]:
        res = self._circle(chain).create_custodial_wallet_for_user(
            profile_id, None, account_type=account_type, idempotency_key=idem_uuid(idem))
        if not res.get("success"):
            raise ChainOpsError(f"wallet create failed on {chain}: {res.get('error')}")
        return str(res["wallet_id"]), str(res["wallet_address"])

    def usdc_balance(self, chain: str, address: str) -> Decimal:
        from gaming.src.backend.services.clawstation_circle import _on_chain_usdc

        bal, err = _on_chain_usdc(address, chain)
        if err is not None or bal is None:
            raise ChainOpsError(f"balance read failed on {chain}: {err}")
        return Decimal(bal)

    def ensure_gas(self, chain: str, address: str) -> None:
        from gaming.src.backend.services.gas_tank import ensure_native_gas

        out = ensure_native_gas(chain, address)
        if not out.get("ok"):
            raise ChainOpsError(f"gas top-up failed on {chain}: {out.get('action')}")

    def transfer_usdc(self, chain: str, wallet_id: str, to: str, amount: Decimal, idem: str) -> str:
        res = self._circle(chain).transfer_usdc(wallet_id, to, float(amount), idempotency_key=idem_uuid(idem))
        if not res.get("success"):
            raise ChainOpsError(f"transfer failed on {chain}: {res.get('error')}")
        return str(res.get("transaction_id") or "")

    def _exec(self, chain: str, wallet_id: str, contract: str, sig: str, args: list, idem: str) -> str:
        res = self._circle(chain).execute_contract_function(wallet_id, contract, sig, args,
                                                            idempotency_key=idem_uuid(idem))
        if not res.get("success"):
            raise ChainOpsError(f"{sig.split('(')[0]} failed on {chain}: {res.get('error')}")
        return str(res.get("transaction_id") or "")

    def approve_burn(self, chain: str, wallet_id: str, amount: Decimal, idem: str) -> str:
        from gaming.src.backend.services.chains import cctp_contracts, get_usdc_address

        messenger = cctp_contracts(chain)["token_messenger_v2"]
        return self._exec(chain, wallet_id, get_usdc_address(chain), "approve(address,uint256)",
                          [messenger, str(atoms(amount))], idem)

    def burn(self, chain: str, wallet_id: str, amount: Decimal, dst_domain: int, mint_recipient: str,
             max_fee: Decimal, fast: bool, idem: str) -> str:
        from gaming.src.backend.services.chains import cctp_contracts, get_usdc_address

        messenger = cctp_contracts(chain)["token_messenger_v2"]
        args = [str(atoms(amount)), str(int(dst_domain)), to_bytes32(mint_recipient), get_usdc_address(chain),
                ZERO32, str(atoms(max_fee)), str(FINALITY_FAST if fast else FINALITY_STANDARD)]
        return self._exec(chain, wallet_id, messenger,
                          "depositForBurn(uint256,uint32,bytes32,address,bytes32,uint256,uint32)", args, idem)

    def tx_status(self, chain: str, tx_id: str) -> tuple[str, str]:
        res = self._circle(chain).get_transaction_status(tx_id)
        if not res.get("success"):
            return "pending", ""
        st = str(res.get("status") or "").upper()
        if st in ("COMPLETE", "CONFIRMED"):
            return "confirmed", str(res.get("tx_hash") or "")
        if st in ("FAILED", "CANCELLED", "DENIED"):
            return "failed", str(res.get("tx_hash") or "")
        return "pending", str(res.get("tx_hash") or "")

    def _iris(self, chain: str) -> str:
        from gaming.src.backend.services.chains import cctp_contracts

        return str(cctp_contracts(chain).get("iris_api") or "https://iris-api.circle.com").rstrip("/")

    def fetch_message(self, src_chain: str, burn_tx_hash: str) -> dict[str, Any]:
        from gaming.src.backend.services.chains import cctp_domain

        url = f"{self._iris(src_chain)}/v2/messages/{cctp_domain(src_chain)}"
        with httpx.Client(timeout=httpx.Timeout(15.0)) as http:
            resp = http.get(url, params={"transactionHash": burn_tx_hash})
        if resp.status_code == 404:
            return {"status": "pending"}
        resp.raise_for_status()
        msgs = (resp.json() or {}).get("messages") or []
        if not msgs:
            return {"status": "pending"}
        m = msgs[0]
        att = str(m.get("attestation") or "")
        if str(m.get("status") or "") != "complete" or not att or att == "PENDING":
            return {"status": "pending"}
        return {"status": "complete", "message": str(m.get("message") or ""), "attestation": att}

    def mint(self, dst_chain: str, relayer_wallet_id: str, message: str, attestation: str, idem: str) -> str:
        from gaming.src.backend.services.chains import cctp_contracts

        transmitter = cctp_contracts(dst_chain)["message_transmitter_v2"]
        return self._exec(dst_chain, relayer_wallet_id, transmitter, "receiveMessage(bytes,bytes)",
                          [message, attestation], idem)

    def fast_fee_bps(self, src_chain: str, dst_chain: str) -> Optional[Decimal]:
        from gaming.src.backend.services.chains import cctp_domain

        url = f"{self._iris(src_chain)}/v2/burn/USDC/fees/{cctp_domain(src_chain)}/{cctp_domain(dst_chain)}"
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0)) as http:
                resp = http.get(url)
            resp.raise_for_status()
            rows = resp.json()
        except Exception:
            logger.warning("[cctp] fee quote unavailable %s->%s", src_chain, dst_chain, exc_info=True)
            return None
        rows = rows if isinstance(rows, list) else (rows or {}).get("data") or []
        for r in rows:
            if int(r.get("finalityThreshold") or 0) == FINALITY_FAST:
                return Decimal(str(r.get("minimumFee") or "0"))
        return None


_override: Optional[Any] = None


def set_chain_ops(ops: Optional[Any]) -> None:
    global _override
    _override = ops


def get_chain_ops() -> Any:
    return _override if _override is not None else CircleChainOps()
