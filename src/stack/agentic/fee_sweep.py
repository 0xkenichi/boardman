"""Periodic on-chain housekeeping: fee sweeps, pending-tx reconcile, tmp cleanup.

v2 contracts no longer push platform fees on every settle; they accrue them:

* BoardmanEscrow v2: ``accruedFees`` -> ``withdrawFees()`` (to feeRecipient);
  ``owed[addr]`` -> ``withdraw()`` for payouts whose push failed.
* SpectatorPool v2: ``protocolFees`` -> ``withdrawFees()`` (to feeRecipient);
  ``owed[creator]`` -> ``withdraw()`` for creator shares (creators are the
  agent wallets).

``withdrawFees`` is callable by anyone and always pays the contract's
feeRecipient, so the resolver key signs it; ``withdraw`` pays msg.sender, so
each agent signs its own. A version probe makes every sweep a no-op on v1.

``maintenance_tick`` runs the sweep at most once per interval across all
processes (the slot is claimed in the database) and is started as a daemon by
the house session (``start_maintenance_thread``).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 6 * 3600
SWEEP_LABELS = frozenset({"withdrawFees", "withdraw"})

ESCROW_FEE_ABI = [
    {"name": "accruedFees", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "owed", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "withdrawFees", "type": "function", "stateMutability": "nonpayable", "inputs": [], "outputs": []},
    {"name": "withdraw", "type": "function", "stateMutability": "nonpayable", "inputs": [], "outputs": []},
]
POOL_FEE_ABI = [
    {"name": "protocolFees", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},
    *ESCROW_FEE_ABI[1:],
]


def interval_sec() -> float:
    try:
        return max(60.0, float(os.getenv("BOARDMAN_FEE_SWEEP_SEC") or DEFAULT_INTERVAL_SEC))
    except ValueError:
        return float(DEFAULT_INTERVAL_SEC)


def _agent_signers() -> list[tuple[str, str]]:
    """(agent_id, wallet) for contestants whose keys this deployment holds."""
    from gaming.src.stack.agentic.registry import get_registry

    out = []
    for a in get_registry().list_agents():
        if a.get("role") == "house" or not a.get("wallet_address"):
            continue
        out.append((str(a["agent_id"]), str(a["wallet_address"])))
    return out


def _sweep_contract(
    w3: Any,
    contract: Any,
    *,
    accrued_fn: str,
    resolver_acct: Any,
    agent_accounts: Iterable[tuple[str, Any]],
    send: Callable[..., str],
) -> dict[str, Any]:
    out: dict[str, Any] = {"withdrawFees": None, "withdraw": []}
    accrued = int(getattr(contract.functions, accrued_fn)().call())
    out["accrued_raw"] = accrued
    if accrued > 0 and resolver_acct is not None:
        tx = contract.functions.withdrawFees().build_transaction({"from": resolver_acct.address})
        out["withdrawFees"] = send(w3, resolver_acct, tx, "withdrawFees")
    for agent_id, acct in agent_accounts:
        owed = int(contract.functions.owed(w3.to_checksum_address(acct.address)).call())
        if owed <= 0:
            continue
        tx = contract.functions.withdraw().build_transaction({"from": acct.address})
        out["withdraw"].append({"agent_id": agent_id, "owed_raw": owed, "tx_hash": send(w3, acct, tx, "withdraw")})
    return out


def _agent_accounts(signers: Iterable[tuple[str, str]]) -> list[tuple[str, Any]]:
    from gaming.src.stack.agentic.onchain import _account, load_agent_private_key

    accts = []
    for agent_id, _wallet in signers:
        try:
            accts.append((agent_id, _account(load_agent_private_key(agent_id))))
        except Exception as exc:  # sealed / keystore locked: that agent pulls its own
            logger.info("[fee_sweep] no spend key for %s: %s", agent_id, exc)
    return accts


def _resolver():
    from gaming.src.stack.agentic.onchain import _account, load_resolver_key

    try:
        return _account(load_resolver_key())
    except Exception as exc:
        logger.warning("[fee_sweep] resolver key unavailable: %s", exc)
        return None


def _guarded_send(w3: Any, acct: Any, tx: dict[str, Any], label: str) -> str:
    from gaming.src.stack.agentic.onchain import _send

    if label not in SWEEP_LABELS:
        raise RuntimeError(f"fee sweep cannot broadcast {label}")
    return _send(w3, acct, tx, label)


def sweep_escrow_fees(chain_id: str = "arc") -> dict[str, Any]:
    from gaming.src.stack.agentic.onchain import _chain_config, _w3, escrow_version

    cfg = _chain_config(chain_id)
    w3 = _w3(cfg)
    version = escrow_version(w3, cfg)
    if version < 2:
        return {"contract": "BoardmanEscrow", "skipped": f"v{version} has no accrued fees"}
    c = w3.eth.contract(address=w3.to_checksum_address(cfg["escrow"]), abi=ESCROW_FEE_ABI)
    out = _sweep_contract(
        w3, c, accrued_fn="accruedFees", resolver_acct=_resolver(),
        agent_accounts=_agent_accounts(_agent_signers()), send=_guarded_send,
    )
    return {"contract": "BoardmanEscrow", "version": version, **out}


def sweep_pool_fees(chain_id: str = "arc") -> dict[str, Any]:
    from gaming.src.stack.agentic.spectator_onchain import _pool_cfg, pool_version, spectator_pool_address
    from gaming.src.stack.agentic.onchain import _w3

    if not spectator_pool_address():
        return {"contract": "SpectatorPool", "skipped": "no pool configured"}
    cfg = _pool_cfg(chain_id)
    w3 = _w3(cfg)
    version = pool_version(w3, cfg)
    if version < 2:
        return {"contract": "SpectatorPool", "skipped": f"v{version} has no accrued fees"}
    c = w3.eth.contract(address=w3.to_checksum_address(cfg["pool"]), abi=POOL_FEE_ABI)
    out = _sweep_contract(
        w3, c, accrued_fn="protocolFees", resolver_acct=_resolver(),
        agent_accounts=_agent_accounts(_agent_signers()), send=_guarded_send,
    )
    return {"contract": "SpectatorPool", "version": version, **out}


def sweep_all(chain_id: str = "arc") -> list[dict[str, Any]]:
    results = []
    for fn in (sweep_escrow_fees, sweep_pool_fees):
        try:
            results.append(fn(chain_id))
        except Exception as exc:
            logger.warning("[fee_sweep] %s failed: %s", fn.__name__, exc)
            results.append({"contract": fn.__name__, "error": str(exc)})
    return results


def _claim_slot(key: str, every_sec: float) -> bool:
    """True for exactly one process per interval (claimed in the database)."""
    from datetime import datetime, timezone

    from gaming.src.stack.agentic.db import transaction

    now = time.time()
    with transaction() as tx:
        row = tx.one(f"SELECT value FROM storage_meta WHERE key = ?{tx.for_update}", (key,))
        if row is not None and now - float(row["value"] or 0) < every_sec:
            return False
        tx.execute(
            "INSERT INTO storage_meta (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, str(now), datetime.now(timezone.utc).isoformat()),
        )
        return True


def maintenance_tick(chain_id: str = "arc", *, force: bool = False) -> dict[str, Any]:
    from gaming.src.stack.agentic.onchain import onchain_enabled, reconcile_pending_txs
    from gaming.src.stack.agentic.store import cleanup_orphan_tmp

    out: dict[str, Any] = {"tmp_removed": cleanup_orphan_tmp()}
    if not onchain_enabled():
        out["onchain"] = "disabled"
        return out
    try:
        out["reconciled"] = reconcile_pending_txs(chain_id)
    except Exception as exc:
        out["reconcile_error"] = str(exc)
    if force or _claim_slot(f"fee_sweep:{chain_id}", interval_sec()):
        out["sweeps"] = sweep_all(chain_id)
    return out


_thread: Optional[threading.Thread] = None


def start_maintenance_thread(chain_id: str = "arc", *, every_sec: float = 300.0) -> None:
    """Daemon that runs ``maintenance_tick`` every few minutes (sweeps throttle themselves)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return

    def _loop() -> None:
        while True:
            try:
                res = maintenance_tick(chain_id)
                if res.get("sweeps"):
                    logger.info("[fee_sweep] %s", res["sweeps"])
            except Exception:
                logger.warning("[fee_sweep] maintenance tick failed", exc_info=True)
            time.sleep(every_sec)

    _thread = threading.Thread(target=_loop, name="agentic-maintenance", daemon=True)
    _thread.start()
