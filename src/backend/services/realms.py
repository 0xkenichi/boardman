"""Money realms: real money (humans) never mixes with practice money (arena).

Boardman runs two economies in one process:

``humans``  friend challenges between people with REAL USDC on a mainnet
            chain (Arc mainnet): naira top-up / cash-out via Paycrest, Circle
            developer-controlled play wallets created with the LIVE Circle
            entity, and passkey self-custody wallets.
``arena``   the AI arena, spectator betting, AFM football, the football-ledger
            wallet bridge and the faucet: practice chips (testnet USDC, no cash
            value) on Arc testnet.

The realm of any money row is the realm of its chain, and the network of a
chain is declared in ``config/chains.yaml`` (``network: mainnet|testnet``).
Everything here fails closed: a chain without a declared network counts as
real money, so practice-only paths refuse it.

Hard invariants (tests/test_money_realms.py):

1. Arena paths (spectator bets, LP deposits, AFM bets, the wallet bridge, the
   House / agentic signer, faucet, play_adjust overlay) only ever touch a
   practice chain. ``assert_practice`` guards each of them, and the agentic
   signer refuses to broadcast to a real chain id.
2. Real-money paths (Paycrest on/off-ramp, CCTP for Paycrest, real-money play
   wallets) only ever touch a real chain. ``assert_real`` guards each of them,
   and a CCTP leg can never cross networks.
3. Circle credentials follow the blockchain: a mainnet blockchain uses
   ``CIRCLE_API_KEY_LIVE`` / ``CIRCLE_ENTITY_SECRET_LIVE`` /
   ``CIRCLE_WALLET_SET_ID_LIVE`` and nothing else; a testnet blockchain uses
   ``CIRCLE_API_KEY`` / ``CIRCLE_ENTITY_SECRET`` / ``CIRCLE_WALLET_SET_ID`` and
   refuses a ``LIVE_API_KEY:`` key.
4. Signing keys follow the chain: the mainnet escrow resolver comes only from
   the keystore entry named by ``BOARDMAN_RESOLVER_KEY_MAINNET``; a plaintext
   private key there (or the testnet resolver key) is refused.
5. Every human challenge carries its ``settlement_chain`` and every lock,
   balance check, cap and payout uses that chain, never a process default.

Env (read per call):
  REAL_MONEY_ENABLED       master switch for real money (default off)
  BOARDMAN_HUMANS_CHAIN    humans-realm chain (default ``realms.humans.chain``
                           in chains.yaml, i.e. ``arc_mainnet``)
  BOARDMAN_ARENA_CHAIN     arena-realm chain (default ``arc``)
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

HUMANS = "humans"
ARENA = "arena"
REALMS = (HUMANS, ARENA)

MAINNET = "mainnet"
TESTNET = "testnet"

_TRUTHY = {"1", "true", "yes", "on"}

# Circle W3S blockchain labels for test networks end in one of these.
_CIRCLE_TEST_SUFFIXES = ("-TESTNET", "-SEPOLIA", "-FUJI", "-AMOY", "-DEVNET", "-HOLESKY")
LIVE_KEY_PREFIX = "LIVE_API_KEY:"
TEST_KEY_PREFIX = "TEST_API_KEY:"

_PRIVATE_KEY_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


class RealmViolation(PermissionError):
    """A money action tried to cross realms (real <-> practice). Nothing moved."""

    status_code = 409

    def __init__(self, message: str, *, path: str = "", chain: str = "", realm: str = "") -> None:
        super().__init__(message)
        self.path = path
        self.chain = chain
        self.realm = realm
        self.detail = {"error": "money_realm_violation", "message": message, "chain": chain, "path": path}


class RealmMisconfigured(RuntimeError):
    """The realm configuration itself is unsafe (e.g. arena on a mainnet chain)."""


def _flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in _TRUTHY


# ── chain network ─────────────────────────────────────────────────────────────


def _chains_cfg() -> dict[str, Any]:
    from gaming.src.backend.services.chains import load_chains_config

    return load_chains_config()


def _norm(chain_id: Optional[str]) -> str:
    from gaming.src.backend.services.chains import _ALIASES

    cid = (chain_id or "").lower().strip()
    return _ALIASES.get(cid, cid)


def chain_network(chain_id: Optional[str]) -> str:
    """``mainnet`` or ``testnet`` for a chain key. Unknown chains, and chains
    without a declared network, are ``mainnet`` (fail closed: treated as real)."""
    cid = _norm(chain_id)
    try:
        row = (_chains_cfg().get("chains") or {}).get(cid) or {}
    except Exception:
        logger.error("[realms] chains config unreadable; treating %r as mainnet", chain_id, exc_info=True)
        return MAINNET
    net = str(row.get("network") or "").strip().lower()
    if net in (MAINNET, TESTNET):
        return net
    return MAINNET


def is_real_chain(chain_id: Optional[str]) -> bool:
    return chain_network(chain_id) == MAINNET


def is_practice_chain(chain_id: Optional[str]) -> bool:
    return chain_network(chain_id) == TESTNET


def realm_of_chain(chain_id: Optional[str]) -> str:
    return HUMANS if is_real_chain(chain_id) else ARENA


def money_kind(chain_id: Optional[str]) -> str:
    """Player-facing word for the money on a chain."""
    return "real" if is_real_chain(chain_id) else "practice"


def real_evm_chain_ids() -> set[int]:
    """EVM chain ids of every chain declared (or defaulted) as mainnet."""
    out: set[int] = set()
    for cid, row in (_chains_cfg().get("chains") or {}).items():
        try:
            n = int(row.get("chain_id") or 0)
        except (TypeError, ValueError):
            continue
        if n and chain_network(cid) == MAINNET:
            out.add(n)
    # Well-known mainnets even if a config row is missing.
    out.update({1, 10, 137, 8453, 42161, 43114, 42220})
    return out


def practice_evm_chain_ids() -> set[int]:
    out: set[int] = set()
    for cid, row in (_chains_cfg().get("chains") or {}).items():
        try:
            n = int(row.get("chain_id") or 0)
        except (TypeError, ValueError):
            continue
        if n and chain_network(cid) == TESTNET:
            out.add(n)
    return out


# ── realm chains ──────────────────────────────────────────────────────────────


def _realm_cfg(realm: str) -> dict[str, Any]:
    try:
        return dict((_chains_cfg().get("realms") or {}).get(realm) or {})
    except Exception:
        return {}


def arena_chain() -> str:
    """The practice chain the arena, spectator betting and AFM use. Raises
    RealmMisconfigured if it names a real-money chain."""
    raw = (os.getenv("BOARDMAN_ARENA_CHAIN") or _realm_cfg(ARENA).get("chain") or "arc").strip()
    cid = _norm(raw)
    if not is_practice_chain(cid):
        raise RealmMisconfigured(
            f"arena realm chain {cid!r} is not a testnet chain; the arena only ever uses practice money"
        )
    return cid


def humans_chain() -> str:
    """The real-money chain for human challenges. Raises RealmMisconfigured if
    it names a practice chain."""
    raw = (os.getenv("BOARDMAN_HUMANS_CHAIN") or _realm_cfg(HUMANS).get("chain") or "arc_mainnet").strip()
    cid = _norm(raw)
    if not is_real_chain(cid):
        raise RealmMisconfigured(f"humans realm chain {cid!r} is not a mainnet chain")
    return cid


def realm_chain(realm: str) -> str:
    if realm == HUMANS:
        return humans_chain()
    if realm == ARENA:
        return arena_chain()
    raise ValueError(f"unknown money realm {realm!r}")


def real_money_enabled() -> bool:
    return _flag("REAL_MONEY_ENABLED")


def humans_live() -> bool:
    """Real-money human challenges are live: the switch is on AND the humans
    chain has an escrow address. Any config error means not live."""
    if not real_money_enabled():
        return False
    try:
        from gaming.src.backend.services.chains import chain_has_escrow

        return chain_has_escrow(humans_chain())
    except Exception:
        logger.error("[realms] humans realm not usable", exc_info=True)
        return False


def new_challenge_chain() -> str:
    """Chain for a new human friend challenge: real money when the humans
    realm is live, practice chips otherwise."""
    return humans_chain() if humans_live() else arena_chain()


def resolve_challenge_chain(requested: Optional[str] = None) -> str:
    """The chain a new human challenge is created on.

    * nothing requested -> ``new_challenge_chain()``
    * a real chain      -> only the humans chain, only while humans are live
    * a practice chain  -> only the arena chain (practice chips)
    """
    if not (requested or "").strip():
        return new_challenge_chain()
    cid = _norm(requested)
    if is_real_chain(cid):
        if not humans_live():
            raise RealmViolation("Real-money challenges are not open yet.", path="challenge", chain=cid)
        if cid != humans_chain():
            raise RealmViolation(f"Real-money challenges run on {humans_chain()} only.", path="challenge", chain=cid)
        return cid
    if cid != arena_chain():
        raise RealmViolation(f"Practice challenges run on {arena_chain()} only.", path="challenge", chain=cid)
    return cid


# ── guards ────────────────────────────────────────────────────────────────────


def assert_practice(chain_id: Optional[str], *, path: str) -> str:
    """Refuse real money on a practice-only path. Returns the normalized chain."""
    cid = _norm(chain_id)
    if not is_practice_chain(cid):
        logger.error("[realms] REFUSED real-money chain %r on practice path %s", cid, path)
        raise RealmViolation(
            f"{path} uses practice money only; refusing chain {cid or '?'}",
            path=path, chain=cid, realm=ARENA,
        )
    return cid


def assert_real(chain_id: Optional[str], *, path: str) -> str:
    """Refuse practice money on a real-money path. Returns the normalized chain."""
    cid = _norm(chain_id)
    if not is_real_chain(cid):
        logger.error("[realms] REFUSED practice chain %r on real-money path %s", cid, path)
        raise RealmViolation(
            f"{path} moves real money only; refusing practice chain {cid or '?'}",
            path=path, chain=cid, realm=HUMANS,
        )
    return cid


def assert_same_network(src_chain: str, dst_chain: str, *, path: str) -> None:
    if chain_network(src_chain) != chain_network(dst_chain):
        raise RealmViolation(
            f"{path}: {src_chain} -> {dst_chain} crosses real and practice money",
            path=path, chain=f"{src_chain}->{dst_chain}",
        )


def assert_practice_evm(evm_chain_id: int, *, path: str) -> None:
    """The arena signer must never broadcast on a real-money chain id."""
    n = int(evm_chain_id)
    if n in real_evm_chain_ids():
        logger.error("[realms] REFUSED arena broadcast %s on real chain id %s", path, n)
        raise RealmViolation(
            f"{path}: the arena signer refuses real-money chain id {n}", path=path, chain=str(n), realm=ARENA,
        )


def assert_practice_balance_source(chain_id: Optional[str], *, path: str) -> str:
    """Spectator / LP / AFM / bridge debits come off the PRACTICE balance only."""
    return assert_practice(chain_id, path=path)


# ── Circle credentials ───────────────────────────────────────────────────────


def circle_blockchain_is_real(blockchain: Optional[str]) -> bool:
    """Circle W3S label (``ARC``, ``ARC-TESTNET``, ``BASE``…): real unless it
    names a test network. Empty or unknown counts as real (fail closed)."""
    b = (blockchain or "").strip().upper().replace("_", "-")
    if not b:
        return True
    return not b.endswith(_CIRCLE_TEST_SUFFIXES)


@dataclass(frozen=True)
class CircleCreds:
    realm: str
    api_key: str
    entity_secret: str
    wallet_set_id: str
    api_key_env: str
    entity_secret_env: str
    wallet_set_env: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.entity_secret)


CIRCLE_ENV = {
    HUMANS: ("CIRCLE_API_KEY_LIVE", "CIRCLE_ENTITY_SECRET_LIVE", "CIRCLE_WALLET_SET_ID_LIVE"),
    ARENA: ("CIRCLE_API_KEY", "CIRCLE_ENTITY_SECRET", "CIRCLE_WALLET_SET_ID"),
}


def circle_credentials(blockchain: Optional[str]) -> CircleCreds:
    """Circle API key + entity secret + wallet set for a blockchain's realm.

    Never falls back across realms. Raises RealmViolation when the key that
    is set belongs to the other environment (Circle prefixes keys with
    ``TEST_API_KEY:`` / ``LIVE_API_KEY:``). Secret values are never logged.
    """
    realm = HUMANS if circle_blockchain_is_real(blockchain) else ARENA
    key_env, secret_env, set_env = CIRCLE_ENV[realm]
    key = (os.getenv(key_env) or "").strip()
    if key:
        if realm == HUMANS and not key.startswith(LIVE_KEY_PREFIX):
            raise RealmViolation(
                f"{key_env} is not a LIVE Circle key; refusing to use it for {blockchain}",
                path="circle", chain=str(blockchain or ""), realm=realm,
            )
        if realm == ARENA and key.startswith(LIVE_KEY_PREFIX):
            raise RealmViolation(
                f"{key_env} is a LIVE Circle key; practice blockchain {blockchain} needs the TEST key",
                path="circle", chain=str(blockchain or ""), realm=realm,
            )
    return CircleCreds(
        realm=realm,
        api_key=key,
        entity_secret=(os.getenv(secret_env) or "").strip(),
        wallet_set_id=(os.getenv(set_env) or "").strip(),
        api_key_env=key_env,
        entity_secret_env=secret_env,
        wallet_set_env=set_env,
    )


# ── resolver keys ────────────────────────────────────────────────────────────

RESOLVER_MAINNET_ENV = "BOARDMAN_RESOLVER_KEY_MAINNET"


def resolver_keystore_name() -> str:
    """Keystore entry holding the real-money escrow resolver key.

    ``BOARDMAN_RESOLVER_KEY_MAINNET`` names the entry (e.g.
    ``resolver_arc_mainnet``); it is NEVER the key itself."""
    raw = (os.getenv(RESOLVER_MAINNET_ENV) or "").strip()
    if not raw:
        raise RealmMisconfigured(
            f"{RESOLVER_MAINNET_ENV} is not set (run scripts/create_mainnet_resolver.py on the server)"
        )
    if _PRIVATE_KEY_RE.match(raw):
        raise RealmMisconfigured(
            f"{RESOLVER_MAINNET_ENV} looks like a plaintext private key. It must name a keystore "
            "entry; rotate that key now and use scripts/create_mainnet_resolver.py"
        )
    return raw


def resolver_private_key(chain_id: str) -> str:
    """Resolver private key for a chain's escrow, from the right realm.

    Real chain: the sealed keystore entry named by BOARDMAN_RESOLVER_KEY_MAINNET
    (unsealed with BOARDMAN_KEYSTORE_SECRET), never an env private key.
    Practice chain: the existing arena resolver (BOARDMAN_RESOLVER_KEY …).
    """
    if is_real_chain(chain_id):
        from gaming.src.stack.agentic.keystore import get_keystore

        pk = get_keystore().private_key(resolver_keystore_name())
        try:
            from gaming.src.stack.agentic.onchain import load_resolver_key

            arena_pk = load_resolver_key()
        except Exception:
            arena_pk = ""
        if arena_pk and arena_pk.lower().removeprefix("0x") == pk.lower().removeprefix("0x"):
            raise RealmMisconfigured("the mainnet resolver must not be the testnet resolver key")
        return pk
    from gaming.src.stack.agentic.onchain import load_resolver_key

    return load_resolver_key()


# ── status ───────────────────────────────────────────────────────────────────


def status() -> dict[str, Any]:
    """Operator view; never includes secret values."""
    out: dict[str, Any] = {"real_money_enabled": real_money_enabled()}
    for realm in REALMS:
        try:
            cid = realm_chain(realm)
            creds = circle_credentials("ARC" if realm == HUMANS else "ARC-TESTNET")
            out[realm] = {
                "chain": cid,
                "network": chain_network(cid),
                "circle_key_set": bool(creds.api_key),
                "circle_entity_secret_set": bool(creds.entity_secret),
                "circle_wallet_set_set": bool(creds.wallet_set_id),
            }
        except Exception as exc:
            out[realm] = {"error": f"{type(exc).__name__}: {exc}"}
    out["humans_live"] = humans_live()
    return out
