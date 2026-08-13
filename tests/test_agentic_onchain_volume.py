"""On-chain USDC transfer volume: math, caching, and API route wiring."""
from __future__ import annotations

import time

from gaming.src.stack.agentic import onchain
from gaming.src.stack.agentic.api import router as agentic_router


def _fake_cfg():
    return {
        "chain_id": "arc",
        "rpc_url": "http://fake-rpc.test",
        "usdc": "0x3600000000000000000000000000000000000000",
        "escrow": "0x3cD57447490c81598Bd8CaCBe3843b24E5735A77",
        "explorer_tx": "https://testnet.arcscan.app/tx/",
        "evm_chain_id": 5042002,
        "get_explorer_tx": None,
    }


def _make_logs(monkeypatch, block_number=1000, chunks=None):
    """Install fakes: no network. `chunks` maps (from_topic, to_topic) → logs."""
    chunks = chunks or {}

    def fake_chain_config(chain_id="arc"):
        return _fake_cfg()

    def fake_latest_block(cfg):
        return block_number

    def fake_get_logs_paged(cfg, usdc_addr, topics, start, end, chunk=5000):
        return chunks.get(tuple(topics), [])

    monkeypatch.setattr(onchain, "_chain_config", fake_chain_config)
    monkeypatch.setattr(onchain, "latest_block", fake_latest_block)
    monkeypatch.setattr(onchain, "_get_logs_paged", fake_get_logs_paged)


def _fake_store(monkeypatch, initial=None):
    store = dict(initial or {})

    def load():
        # copy, mirroring load_json which returns a fresh parsed object
        return dict(store)

    def save(payload):
        store.clear()
        store.update(payload)

    monkeypatch.setattr(onchain, "_load_volume_cache", load)
    monkeypatch.setattr(onchain, "_save_volume_cache", save)
    return store


ADDR = "0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029"
ADDR_TOPIC = "0x" + ADDR.lower().replace("0x", "").rjust(64, "0")


def _transfer_logs(value_usdc: float, count: int = 1):
    raw = int(value_usdc * 10**6)
    return [{"data": hex(raw)} for _ in range(count)]


def test_volume_sums_in_and_out(monkeypatch):
    _make_logs(
        monkeypatch,
        chunks={
            (onchain.TRANSFER_TOPIC, ADDR_TOPIC, None): _transfer_logs(1.5, 2),
            (onchain.TRANSFER_TOPIC, None, ADDR_TOPIC): _transfer_logs(0.25, 4),
        },
    )
    _fake_store(monkeypatch)

    vol = onchain.usdc_transfer_volume(ADDR, use_cache=False)
    assert vol["in_usdc"] == 1.0  # 4 × 0.25
    assert vol["out_usdc"] == 3.0  # 2 × 1.5
    assert vol["count_in"] == 4
    assert vol["count_out"] == 2
    assert vol["scanned_to"] == 1000
    assert vol["cached"] is False


def test_volume_cache_short_circuits(monkeypatch):
    _make_logs(
        monkeypatch,
        chunks={
            (onchain.TRANSFER_TOPIC, ADDR_TOPIC, None): _transfer_logs(5.0),
            (onchain.TRANSFER_TOPIC, None, ADDR_TOPIC): [],
        },
    )
    _fake_store(monkeypatch)

    first = onchain.usdc_transfer_volume(ADDR)
    assert first["cached"] is False
    assert first["out_usdc"] == 5.0

    # Second call within TTL + same to_block → served from cache, no RPC scan.
    calls = {"n": 0}
    original = onchain._get_logs_paged

    def counting_paged(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(onchain, "_get_logs_paged", counting_paged)
    second = onchain.usdc_transfer_volume(ADDR)
    assert second["cached"] is True
    assert second["out_usdc"] == 5.0
    assert calls["n"] == 0


def test_volume_incremental_scan(monkeypatch):
    _fake_store(monkeypatch)

    # First scan to block 1000: 1.0 out.
    _make_logs(
        monkeypatch,
        block_number=1000,
        chunks={
            (onchain.TRANSFER_TOPIC, ADDR_TOPIC, None): _transfer_logs(1.0),
            (onchain.TRANSFER_TOPIC, None, ADDR_TOPIC): [],
        },
    )
    first = onchain.usdc_transfer_volume(ADDR)
    assert first["out_usdc"] == 1.0
    assert first["scanned_to"] == 1000

    # Chain advanced to 1500: only the delta 1001..1500 is scanned.
    seen_ranges = []

    def paged(cfg, usdc_addr, topics, start, end, chunk=5000):
        seen_ranges.append((start, end))
        if topics[1] == ADDR_TOPIC:
            return _transfer_logs(2.0)
        return []

    monkeypatch.setattr(onchain, "_get_logs_paged", paged)
    monkeypatch.setattr(onchain, "latest_block", lambda cfg: 1500)
    second = onchain.usdc_transfer_volume(ADDR)
    assert second["cached"] is False
    assert second["out_usdc"] == 3.0  # 1.0 cached + 2.0 delta
    # two paged calls (from-side + to-side), both restricted to the delta range
    assert seen_ranges == [(1001, 1500), (1001, 1500)]
    assert onchain._load_volume_cache()  # persisted


def test_volume_no_cache_use(monkeypatch):
    _make_logs(
        monkeypatch,
        chunks={
            (onchain.TRANSFER_TOPIC, ADDR_TOPIC, None): _transfer_logs(2.0),
            (onchain.TRANSFER_TOPIC, None, ADDR_TOPIC): [],
        },
    )
    _fake_store(monkeypatch)

    vol = onchain.usdc_transfer_volume(ADDR, use_cache=False)
    assert vol["cached"] is False
    # With use_cache=False nothing is written to the store.
    assert onchain._load_volume_cache() == {}


def test_api_route_order_static_before_dynamic():
    """GET /agents/onchain_volume must not be shadowed by /agents/{agent_id}.

    FastAPI matches routes in registration order, so the static aggregate route
    has to be registered before the dynamic per-agent route.
    """
    paths = [r.path for r in agentic_router.routes]
    static = paths.index("/api/stack/agentic/agents/onchain_volume")
    dynamic = paths.index("/api/stack/agentic/agents/{agent_id}")
    assert static < dynamic, (
        "/agents/onchain_volume must be registered before /agents/{agent_id}"
    )
    assert "/api/stack/agentic/agents/{agent_id}/onchain_volume" in paths


def test_volume_cache_ttl_expiry_forces_rescan(monkeypatch):
    _make_logs(
        monkeypatch,
        chunks={
            (onchain.TRANSFER_TOPIC, ADDR_TOPIC, None): _transfer_logs(1.0),
            (onchain.TRANSFER_TOPIC, None, ADDR_TOPIC): [],
        },
    )
    _fake_store(monkeypatch)

    onchain.usdc_transfer_volume(ADDR)
    # Expire the TTL by aging the cached entry.
    cache = onchain._load_volume_cache()
    key = f"arc:{ADDR.lower()}"
    cache[key]["scanned_at"] = time.time() - onchain.VOLUME_CACHE_TTL_SEC - 1
    onchain._save_volume_cache(cache)

    calls = {"n": 0}
    original = onchain._get_logs_paged

    def counting_paged(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(onchain, "_get_logs_paged", counting_paged)
    vol = onchain.usdc_transfer_volume(ADDR)
    assert vol["cached"] is False
    assert calls["n"] > 0
