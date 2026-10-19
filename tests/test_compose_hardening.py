"""docker-compose.yml keeps the production containers locked down.

Infra audit 2026-10 (INF-13): the base compose file published the API on
0.0.0.0:8000 (the VM only stayed safe through an untracked override file), and
Docker-published ports bypass the host firewall's INPUT chain.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]


def test_api_port_is_loopback_by_default():
    for spec in SERVICES["boardman-api"]["ports"]:
        host = str(spec).rsplit(":", 2)[0]
        assert host in ("127.0.0.1", "${BOARDMAN_API_BIND:-127.0.0.1}"), spec


def test_only_the_api_publishes_ports():
    for name, svc in SERVICES.items():
        if name != "boardman-api":
            assert not svc.get("ports"), f"{name} must not publish ports"


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_service_is_unprivileged(name):
    svc = SERVICES[name]
    assert not svc.get("privileged"), name
    assert "ALL" in svc.get("cap_drop", []), name
    assert not svc.get("cap_add"), name
    assert "no-new-privileges:true" in svc.get("security_opt", []), name
    assert svc.get("network_mode") != "host", name
    assert svc.get("pid") != "host", name
    for vol in svc.get("volumes", []):
        assert "docker.sock" not in str(vol), f"{name} mounts the Docker socket"
