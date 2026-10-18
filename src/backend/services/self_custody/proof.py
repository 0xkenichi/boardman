"""Proof that the player controls the smart account they link (setup / change).

The server issues a one-time challenge: a plain-text EIP-191 message naming
the site, the Boardman profile, the wallet address, the EVM chain id, the
purpose (setup / change), a 128-bit nonce and its validity window. The page
signs it with the passkey smart account (``smart.signMessage``: Circle's MSCA
signs a replay-safe wrapper of the EIP-191 hash bound to its own address and
chain id; viem wraps the result in ERC-6492 while the account is not deployed).

We verify here, in Python, with one read-only ``eth_call`` on the configured
Arc RPC: the *deployless* ERC-6492 universal validator (the contract's init
code followed by ``abi.encode(signer, hash, signature)``, no ``to``). It
returns ``0x01`` when the signature is valid for that address: it deploys a
counterfactual account in the call's scratch state when the signature carries
ERC-6492 factory data, then asks the account's ERC-1271 ``isValidSignature``
(and falls back to ``ecrecover`` for a plain EOA). Nothing is sent; no gas;
nothing is trusted from the browser except the signature itself.

The bytecode is viem's ``erc6492SignatureValidatorByteCode`` (viem 2.57.7,
``viem/_esm/constants/contracts.js``, MIT), the same one ``verifyMessage``
uses; ``frontend/lib/__tests__/setupProof.test.mjs`` checks that the bytes and
the calldata encoding here match viem's.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

SIG_RE = re.compile(r"^0x(?:[0-9a-fA-F]{2}){65,8192}$")
NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
KINDS = ("setup", "change")
MAGIC_OK = b"\x01"

# fmt: off
VALIDATOR_BYTECODE = bytes.fromhex(
    "608060405234801561001057600080fd5b5060405161069438038061069483398101604081905261002f9161051e565b6000"
    "61003c848484610048565b9050806000526001601ff35b60007f649264926492649264926492649264926492649264926492"
    "64926492649264926100748361040c565b036101e7576000606080848060200190518101906100929190610577565b604051"
    "92955090935091506000906001600160a01b038516906100b69085906105dd565b6000604051808303816000865af1915050"
    "3d80600081146100f3576040519150601f19603f3d011682016040523d82523d6000602084013e6100f8565b606091505b50"
    "509050876001600160a01b03163b60000361016057806101605760405162461bcd60e51b815260206004820152601e602482"
    "01527f5369676e617475726556616c696461746f723a206465706c6f796d656e74000060448201526064015b604051809103"
    "90fd5b604051630b135d3f60e11b808252906001600160a01b038a1690631626ba7e90610190908b9087906004016105f956"
    "5b602060405180830381865afa1580156101ad573d6000803e3d6000fd5b505050506040513d601f19601f82011682018060"
    "4052508101906101d19190610633565b6001600160e01b03191614945050505050610405565b6001600160a01b0384163b15"
    "61027a57604051630b135d3f60e11b808252906001600160a01b03861690631626ba7e9061022790879087906004016105f9"
    "565b602060405180830381865afa158015610244573d6000803e3d6000fd5b505050506040513d601f19601f820116820180"
    "604052508101906102689190610633565b6001600160e01b031916149050610405565b81516041146102df5760405162461b"
    "cd60e51b815260206004820152603a602482015260008051602061067483398151915260448201527f3a20696e76616c6964"
    "207369676e6174757265206c656e6774680000000000006064820152608401610157565b6102e7610425565b506020820151"
    "6040808401518451859392600091859190811061030c5761030c61065d565b016020015160f81c9050601b81148015906103"
    "2b57508060ff16601c14155b1561038c5760405162461bcd60e51b815260206004820152603b602482015260008051602061"
    "067483398151915260448201527f3a20696e76616c6964207369676e617475726520762076616c7565000000000060648201"
    "52608401610157565b60408051600081526020810180835289905260ff831691810191909152606081018490526080810183"
    "90526001600160a01b0389169060019060a0016020604051602081039080840390855afa1580156103ea573d6000803e3d60"
    "00fd5b505050602060405103516001600160a01b0316149450505050505b9392505050565b600060208251101561041d5760"
    "0080fd5b508051015190565b60405180606001604052806003906020820280368337509192915050565b6001600160a01b03"
    "8116811461045857600080fd5b50565b634e487b7160e01b600052604160045260246000fd5b60005b8381101561048c5781"
    "81015183820152602001610474565b50506000910152565b600082601f8301126104a657600080fd5b81516001600160401b"
    "038111156104bf576104bf61045b565b604051601f8201601f19908116603f011681016001600160401b0381118282101715"
    "6104ed576104ed61045b565b60405281815283820160200185101561050557600080fd5b6105168260208301602087016104"
    "71565b949350505050565b60008060006060848603121561053357600080fd5b835161053e81610443565b60208501516040"
    "86015191945092506001600160401b0381111561056157600080fd5b61056d86828701610495565b9150509250925092565b"
    "60008060006060848603121561058c57600080fd5b835161059781610443565b60208501519093506001600160401b038111"
    "156105b357600080fd5b6105bf86828701610495565b604086015190935090506001600160401b0381111561056157600080"
    "fd5b600082516105ef818460208701610471565b9190910192915050565b8281526040602082015260008251806040840152"
    "61061e816060850160208701610471565b601f01601f1916919091016060019392505050565b600060208284031215610645"
    "57600080fd5b81516001600160e01b03198116811461040557600080fd5b634e487b7160e01b600052603260045260246000"
    "fdfe5369676e617475726556616c696461746f72237265636f7665725369676e6572"
)
# fmt: on


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def message_for(*, site: str, profile_id: str, address: str, evm_chain_id: int, kind: str, nonce: str,
                issued_ms: int, expires_ms: int) -> str:
    """The exact text the passkey signs. Every binding is in the text, so a
    signature for one profile, wallet, chain, purpose or time cannot be used
    for another, and the stored copy is what we verify against."""
    if kind not in KINDS or not NONCE_RE.match(nonce):
        raise ValueError("bad challenge")
    host = re.sub(r"^https?://", "", site or "").rstrip("/") or "boardman"
    action = "Link this wallet to" if kind == "setup" else "Change the wallet on"
    return "\n".join([
        f"{host} wants you to prove you own this wallet.",
        "",
        f"{action} my Boardman account.",
        "",
        f"Wallet: {to_checksum_address(address)}",
        f"Account: {profile_id}",
        f"Chain ID: {int(evm_chain_id)}",
        f"Purpose: {kind}",
        f"Nonce: {nonce}",
        f"Issued At: {_iso(issued_ms)}",
        f"Expiration Time: {_iso(expires_ms)}",
    ])


def eip191_hash(message: str) -> bytes:
    """``keccak256("\\x19Ethereum Signed Message:\\n" + len + message)`` (viem ``hashMessage``)."""
    raw = message.encode("utf-8")
    return keccak(b"\x19Ethereum Signed Message:\n" + str(len(raw)).encode("ascii") + raw)


def validator_calldata(account: str, digest: bytes, signature: bytes) -> bytes:
    """Init code + constructor args: what viem's ``encodeDeployData`` builds."""
    if len(digest) != 32:
        raise ValueError("digest must be 32 bytes")
    return VALIDATOR_BYTECODE + abi_encode(["address", "bytes32", "bytes"],
                                           [to_checksum_address(account), digest, signature])


def signature_bytes(signature_hex: str) -> bytes:
    if not SIG_RE.match(signature_hex or ""):
        raise ValueError("bad signature")
    return bytes.fromhex(signature_hex[2:])


def verify(reader: Any, account: str, message: str, signature_hex: str) -> bool:
    """True only if the chain says ``account`` signed ``message``. Malformed
    input is False; an RPC failure raises (the caller answers "try again")."""
    try:
        sig = signature_bytes(signature_hex)
    except ValueError:
        return False
    return bool(reader.is_valid_signature(to_checksum_address(account), eip191_hash(message), sig))
