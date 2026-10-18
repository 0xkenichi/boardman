"""Calldata for the player's smart account, built server-side.

The approve page shows these calls and passes them unchanged to
``sendUserOperation({calls})``; the smart account runs them atomically.
Event topics here are what ``confirm`` looks for on chain.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from eth_abi import encode
from eth_utils import keccak, to_checksum_address

USDC_DECIMALS = 6


def selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def topic(signature: str) -> str:
    return "0x" + keccak(text=signature).hex()


TRANSFER_TOPIC = topic("Transfer(address,address,uint256)")
MATCH_CREATED_TOPIC = topic("MatchCreated(bytes32,address,uint256)")
MATCH_TERMS_TOPIC = topic("MatchTerms(bytes32,address,uint256,uint256)")
MATCH_JOINED_TOPIC = topic("MatchJoined(bytes32,address)")
MATCH_LOCKED_TOPIC = topic("MatchLocked(bytes32)")
DEPOSIT_FOR_BURN_TOPIC = topic(
    "DepositForBurn(address,uint256,address,bytes32,uint32,bytes32,bytes32,uint256,uint32,bytes)"
)


@dataclass(frozen=True)
class Call:
    to: str
    data: str
    value: int = 0
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"to": self.to, "data": self.data, "value": hex(self.value), "label": self.label}


def to_raw(amount: Decimal) -> int:
    return int((Decimal(amount) * Decimal(10**USDC_DECIMALS)).to_integral_value(rounding=ROUND_DOWN))


def from_raw(raw: int) -> Decimal:
    return Decimal(int(raw)) / Decimal(10**USDC_DECIMALS)


def match_id_bytes32(challenge_id: str) -> bytes:
    """Same id the custodial path and the resolver use (sha256 of the uuid)."""
    return hashlib.sha256(str(challenge_id).encode("utf-8")).digest()


def match_id_hex(challenge_id: str) -> str:
    return "0x" + match_id_bytes32(challenge_id).hex()


def _hex(sel: bytes, types: list[str], args: list[Any]) -> str:
    return "0x" + (sel + encode(types, args)).hex()


def usdc_approve(usdc: str, spender: str, raw: int) -> Call:
    return Call(to_checksum_address(usdc),
                _hex(selector("approve(address,uint256)"), ["address", "uint256"],
                     [to_checksum_address(spender), int(raw)]),
                label=f"Allow the escrow to take {from_raw(raw):,.2f} USDC")


def usdc_transfer(usdc: str, to: str, raw: int) -> Call:
    return Call(to_checksum_address(usdc),
                _hex(selector("transfer(address,uint256)"), ["address", "uint256"],
                     [to_checksum_address(to), int(raw)]),
                label=f"Send {from_raw(raw):,.2f} USDC to {to_checksum_address(to)}")


def create_match_v2(escrow: str, match_id: bytes, player2: str, raw: int, deadline: int, sig: bytes) -> Call:
    return Call(to_checksum_address(escrow),
                _hex(selector("createMatch(bytes32,address,uint256,uint256,bytes)"),
                     ["bytes32", "address", "uint256", "uint256", "bytes"],
                     [match_id, to_checksum_address(player2), int(raw), int(deadline), bytes(sig)]),
                label=f"Lock {from_raw(raw):,.2f} USDC in escrow")


def create_match_v1(escrow: str, match_id: bytes, raw: int) -> Call:
    return Call(to_checksum_address(escrow),
                _hex(selector("createMatch(bytes32,uint256)"), ["bytes32", "uint256"], [match_id, int(raw)]),
                label=f"Lock {from_raw(raw):,.2f} USDC in escrow")


def join_match(escrow: str, match_id: bytes, raw: int) -> Call:
    return Call(to_checksum_address(escrow),
                _hex(selector("joinMatch(bytes32)"), ["bytes32"], [match_id]),
                label=f"Lock {from_raw(raw):,.2f} USDC in escrow")


def to_bytes32_address(addr: str) -> bytes:
    return bytes(12) + bytes.fromhex(to_checksum_address(addr)[2:])


def cctp_burn_calls(usdc: str, token_messenger: str, raw: int, dst_domain: int, mint_recipient: str,
                    max_fee_raw: int = 0, min_finality: int = 2000) -> list[Call]:
    """approve + CCTP v2 depositForBurn from the player's own account.

    Built and tested; not wired into the naira cash-out yet (see the doc, §4).
    """
    burn = Call(
        to_checksum_address(token_messenger),
        _hex(selector("depositForBurn(uint256,uint32,bytes32,address,bytes32,uint256,uint32)"),
             ["uint256", "uint32", "bytes32", "address", "bytes32", "uint256", "uint32"],
             [int(raw), int(dst_domain), to_bytes32_address(mint_recipient), to_checksum_address(usdc),
              bytes(32), int(max_fee_raw), int(min_finality)]),
        label=f"Bridge {from_raw(raw):,.2f} USDC",
    )
    return [usdc_approve(usdc, token_messenger, raw), burn]


def addr_topic(addr: str) -> str:
    return "0x" + "00" * 12 + to_checksum_address(addr)[2:].lower()


def topic_address(t: str) -> str:
    h = t[2:] if t.startswith("0x") else t
    return to_checksum_address("0x" + h[-40:])
