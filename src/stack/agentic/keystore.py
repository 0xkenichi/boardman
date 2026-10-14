"""
Agent key custody — random keys, encrypted at rest, never derived.

Every agent spend key is 32 random bytes from the OS CSPRNG
(``eth_account.Account.create``). Nothing about a key can be recomputed from
public data: not the agent_id, not a manifest field, not a label.

Keys are sealed with AES-256-GCM. The data key is derived per entry with
HKDF-SHA256 from ``BOARDMAN_KEYSTORE_SECRET`` (min 32 chars) and a random salt;
the agent_id and address are bound in as associated data so an entry cannot
be swapped onto another agent.

Backends are pluggable:
  file (default)  data/agentic/keystore/<agent_id>.json  (gitignored, 0600)
  kms             reserved — wire a cloud KMS here later

Public addresses are stored in the clear, so address lookups work without the
secret. Decryption and key creation refuse without it. There is no fallback.

Rotation stages a *pending* key next to the active one; promoting it retires
the old entry. See scripts/rotate_agent_wallets.py.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

SECRET_ENV = "BOARDMAN_KEYSTORE_SECRET"
BACKEND_ENV = "BOARDMAN_KEYSTORE_BACKEND"
DIR_ENV = "BOARDMAN_KEYSTORE_DIR"
MIN_SECRET_LEN = 32
ENTRY_VERSION = 1
_HKDF_INFO = b"boardman.agent.keystore.v1"
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

ACTIVE = "active"
PENDING = "pending"


class KeystoreError(RuntimeError):
    """Base class — every keystore failure fails closed."""


class KeystoreLocked(KeystoreError):
    """BOARDMAN_KEYSTORE_SECRET is missing or too short."""


class KeyNotFound(KeystoreError):
    """No sealed key for this agent. Signing must not proceed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _check_name(agent_id: str) -> str:
    if not isinstance(agent_id, str) or not _NAME_RE.match(agent_id):
        raise KeystoreError(f"invalid agent id for keystore: {agent_id!r}")
    return agent_id


def keystore_secret() -> bytes:
    raw = os.getenv(SECRET_ENV, "")
    if len(raw) < MIN_SECRET_LEN:
        raise KeystoreLocked(
            f"{SECRET_ENV} is not set (or shorter than {MIN_SECRET_LEN} chars); "
            "agent keys cannot be created or unsealed"
        )
    return raw.encode("utf-8")


def keystore_unlocked() -> bool:
    return len(os.getenv(SECRET_ENV, "")) >= MIN_SECRET_LEN


# ------------------------------------------------------------------ crypto


def _data_key(secret: bytes, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=_HKDF_INFO).derive(secret)


def _aad(agent_id: str, address: str) -> bytes:
    return f"{agent_id}|{address.lower()}".encode("utf-8")


def seal_key(agent_id: str, private_key: bytes, address: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    secret = keystore_secret()
    salt = os.urandom(16)
    nonce = os.urandom(12)
    ct = AESGCM(_data_key(secret, salt)).encrypt(nonce, private_key, _aad(agent_id, address))
    return {
        "version": ENTRY_VERSION,
        "agent_id": agent_id,
        "address": address,
        "cipher": "aes-256-gcm",
        "kdf": "hkdf-sha256",
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ciphertext": _b64(ct),
        "created_at": _now(),
    }


def unseal_key(entry: dict[str, Any]) -> str:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from eth_account import Account

    secret = keystore_secret()
    agent_id = str(entry.get("agent_id") or "")
    address = str(entry.get("address") or "")
    try:
        pk = AESGCM(_data_key(secret, _unb64(entry["salt"]))).decrypt(
            _unb64(entry["nonce"]), _unb64(entry["ciphertext"]), _aad(agent_id, address)
        )
    except (InvalidTag, KeyError, ValueError) as exc:
        raise KeystoreError(
            f"cannot unseal key for {agent_id}: wrong {SECRET_ENV} or tampered entry"
        ) from exc
    hex_pk = "0x" + pk.hex()
    if Account.from_key(hex_pk).address.lower() != address.lower():
        raise KeystoreError(f"keystore entry for {agent_id} does not match its address")
    return hex_pk


# ----------------------------------------------------------------- backends


class KeystoreBackend(Protocol):
    def read(self, agent_id: str, slot: str) -> Optional[dict[str, Any]]: ...

    def write(self, agent_id: str, slot: str, entry: dict[str, Any]) -> None: ...

    def retire(self, agent_id: str, slot: str) -> None: ...

    def remove(self, agent_id: str, slot: str) -> None: ...

    def names(self) -> list[str]: ...


class FileBackend:
    """One JSON file per agent+slot under a private directory."""

    def __init__(self, root: Optional[Path] = None) -> None:
        if root is None:
            env = os.getenv(DIR_ENV)
            if env:
                root = Path(env)
            else:
                from gaming.src.stack.agentic.store import data_dir

                root = data_dir() / "keystore"
        self.root = Path(root)
        self._lock = threading.RLock()

    def _ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        return self.root

    def _path(self, agent_id: str, slot: str) -> Path:
        suffix = "" if slot == ACTIVE else f".{slot}"
        return self.root / f"{_check_name(agent_id)}{suffix}.json"

    def read(self, agent_id: str, slot: str) -> Optional[dict[str, Any]]:
        p = self._path(agent_id, slot)
        with self._lock:
            if not p.exists():
                return None
            return json.loads(p.read_text(encoding="utf-8"))

    def write(self, agent_id: str, slot: str, entry: dict[str, Any]) -> None:
        self._ensure()
        p = self._path(agent_id, slot)
        with self._lock:
            tmp = p.with_suffix(".json.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, indent=2) + "\n")
            tmp.replace(p)

    def retire(self, agent_id: str, slot: str) -> None:
        """Move an entry aside (kept sealed, for audit) instead of deleting it."""
        p = self._path(agent_id, slot)
        with self._lock:
            if p.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                p.replace(self.root / f"{agent_id}.retired-{stamp}.json")

    def remove(self, agent_id: str, slot: str) -> None:
        with self._lock:
            self._path(agent_id, slot).unlink(missing_ok=True)

    def names(self) -> list[str]:
        if not self.root.exists():
            return []
        out = []
        for p in sorted(self.root.glob("*.json")):
            if "." not in p.stem:
                out.append(p.stem)
        return out


def _backend_from_env() -> KeystoreBackend:
    kind = (os.getenv(BACKEND_ENV) or "file").strip().lower()
    if kind == "file":
        return FileBackend()
    raise KeystoreError(
        f"{BACKEND_ENV}={kind!r} is not implemented; use 'file' (KMS backend is planned)"
    )


# ------------------------------------------------------------------ facade


class AgentKeystore:
    def __init__(self, backend: Optional[KeystoreBackend] = None) -> None:
        self.backend = backend or _backend_from_env()

    # public — no secret required
    def address(self, agent_id: str, *, slot: str = ACTIVE) -> Optional[str]:
        entry = self.backend.read(agent_id, slot)
        return str(entry["address"]) if entry and entry.get("address") else None

    def has_key(self, agent_id: str, *, slot: str = ACTIVE) -> bool:
        return self.address(agent_id, slot=slot) is not None

    # sealed — secret required
    def _new_entry(self, agent_id: str) -> dict[str, Any]:
        from eth_account import Account

        keystore_secret()  # refuse before generating anything
        acct = Account.create()
        return seal_key(agent_id, bytes(acct.key), acct.address)

    def create(self, agent_id: str, *, slot: str = ACTIVE) -> str:
        """Generate + seal a fresh random key. Refuses to overwrite."""
        _check_name(agent_id)
        if self.backend.read(agent_id, slot) is not None:
            raise KeystoreError(f"{agent_id} already has a {slot} key; rotate instead")
        entry = self._new_entry(agent_id)
        self.backend.write(agent_id, slot, entry)
        return entry["address"]

    def get_or_create(self, agent_id: str) -> str:
        return self.address(agent_id) or self.create(agent_id)

    def private_key(self, agent_id: str, *, slot: str = ACTIVE) -> str:
        entry = self.backend.read(agent_id, slot)
        if not entry:
            raise KeyNotFound(
                f"no {slot} keystore key for {agent_id}; refusing to sign "
                "(run scripts/rotate_agent_wallets.py to provision)"
            )
        return unseal_key(entry)

    # rotation
    def stage(self, agent_id: str) -> str:
        """Create (or reuse) a pending key for rotation. Returns its address."""
        return self.address(agent_id, slot=PENDING) or self.create(agent_id, slot=PENDING)

    def promote(self, agent_id: str) -> str:
        """Pending → active. The previous active entry is retired, not deleted."""
        pending = self.backend.read(agent_id, PENDING)
        if not pending:
            raise KeyNotFound(f"no pending key staged for {agent_id}")
        unseal_key(pending)  # prove it opens before it becomes the spend key
        self.backend.retire(agent_id, ACTIVE)
        self.backend.write(agent_id, ACTIVE, pending)
        self.backend.remove(agent_id, PENDING)  # now identical to active
        return str(pending["address"])


def get_keystore() -> AgentKeystore:
    return AgentKeystore()
