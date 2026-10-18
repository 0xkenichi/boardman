"""Read-only chain access for confirmations. Never signs, never sends.

``ChainReader`` is what ``intents.confirm`` and the setup proof need; ``Web3Reader`` talks JSON-RPC
to the configured Arc RPC, tests install a fake with ``set_reader``.
Logs and receipts are returned as plain dicts with hex strings:
``{"address", "topics": [...], "data", "transactionHash", "blockNumber"}``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


class ChainReader(Protocol):
    def block_number(self) -> int: ...

    def receipt(self, tx_hash: str) -> Optional[dict]: ...

    def logs(self, address: str, topics: list[Optional[str]], from_block: int) -> list[dict]: ...

    def usdc_balance(self, usdc: str, account: str) -> int: ...

    def escrow_version(self, escrow: str) -> int: ...

    def is_valid_signature(self, account: str, digest: bytes, signature: bytes) -> bool: ...


def _hex(v: Any) -> str:
    if isinstance(v, (bytes, bytearray)):
        return "0x" + bytes(v).hex()
    if hasattr(v, "hex") and not isinstance(v, str):
        h = v.hex()
        return h if h.startswith("0x") else "0x" + h
    return str(v)


def _norm_log(log: Any) -> dict:
    return {
        "address": str(log["address"]),
        "topics": [_hex(t).lower() for t in log["topics"]],
        "data": _hex(log["data"]),
        "transactionHash": _hex(log.get("transactionHash") or ""),
        "blockNumber": int(log.get("blockNumber") or 0),
    }


class Web3Reader:
    """JSON-RPC reader for one chain (``config.chain_settings``)."""

    LOG_WINDOW = 5_000

    def __init__(self, rpc_url: str) -> None:
        from web3 import Web3

        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))

    def block_number(self) -> int:
        return int(self.w3.eth.block_number)

    def receipt(self, tx_hash: str) -> Optional[dict]:
        try:
            r = self.w3.eth.get_transaction_receipt(tx_hash)
        except Exception:  # TransactionNotFound and transport errors alike: not yet
            return None
        return {
            "status": int(r["status"]),
            "blockNumber": int(r["blockNumber"]),
            "transactionHash": _hex(r["transactionHash"]),
            "logs": [_norm_log(lg) for lg in r["logs"]],
        }

    def logs(self, address: str, topics: list[Optional[str]], from_block: int) -> list[dict]:
        latest = self.block_number()
        start = max(int(from_block), latest - self.LOG_WINDOW)
        raw = self.w3.eth.get_logs({
            "address": self.w3.to_checksum_address(address),
            "topics": topics,
            "fromBlock": start,
            "toBlock": latest,
        })
        return [_norm_log(lg) for lg in raw]

    def usdc_balance(self, usdc: str, account: str) -> int:
        from gaming.src.stack.agentic.onchain import ERC20_ABI

        c = self.w3.eth.contract(address=self.w3.to_checksum_address(usdc), abi=ERC20_ABI)
        return int(c.functions.balanceOf(self.w3.to_checksum_address(account)).call())

    def escrow_version(self, escrow: str) -> int:
        from gaming.src.stack.agentic.onchain import ESCROW_ABI

        try:
            c = self.w3.eth.contract(address=self.w3.to_checksum_address(escrow), abi=ESCROW_ABI)
            return int(c.functions.ESCROW_VERSION().call())
        except Exception:
            return 1

    def is_valid_signature(self, account: str, digest: bytes, signature: bytes) -> bool:
        """ERC-1271 / ERC-6492 check through the deployless universal
        validator (``proof.py``). A revert means "not valid"; transport errors
        raise so the caller can say "try again" instead of "forged"."""
        from web3.exceptions import ContractLogicError

        from gaming.src.backend.services.self_custody import proof

        data = proof.validator_calldata(account, digest, signature)
        try:
            out = self.w3.eth.call({"data": "0x" + data.hex()})
        except ContractLogicError:
            return False
        return bytes(out)[-1:] == proof.MAGIC_OK and int.from_bytes(bytes(out), "big") == 1


_reader: Optional[ChainReader] = None


def set_reader(reader: Optional[ChainReader]) -> None:
    """Tests install a fake; ``None`` goes back to the RPC reader."""
    global _reader
    _reader = reader


def get_reader() -> ChainReader:
    if _reader is not None:
        return _reader
    from gaming.src.backend.services.self_custody import config

    url = config.chain_settings()["rpc_url"]
    if not url:
        raise RuntimeError("no RPC URL for the self-custody chain")
    return Web3Reader(url)
