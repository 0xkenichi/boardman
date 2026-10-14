"""PSNLayer sybil check, without touching the real PSN API.

This used to call ``verify_sybill`` against PSN at import time (a live call
during collection, using NPSSO from the real .env). Now PSNAWP is faked.
"""
from __future__ import annotations

from types import SimpleNamespace

from gaming.src.backend import psn_layer
from gaming.src.backend.psn_layer import PSNLayer


class _FakeUser:
    def __init__(self, bronze, silver=0, gold=0, platinum=0):
        self._earned = SimpleNamespace(bronze=bronze, silver=silver, gold=gold, platinum=platinum)

    def trophy_summary(self):
        return SimpleNamespace(earned_trophies=self._earned)


class _FakePSNAWP:
    users: dict = {}

    def __init__(self, npsso):
        self.npsso = npsso

    def user(self, *, online_id):
        if online_id not in self.users:
            raise RuntimeError(f"user {online_id} not found")
        return self.users[online_id]


def test_importing_psn_layer_does_not_load_dotenv():
    assert not hasattr(psn_layer, "load_dotenv")


def test_without_npsso_reports_not_initialized(monkeypatch):
    monkeypatch.delenv("NPSSO_CODE", raising=False)
    res = PSNLayer().verify_sybill("anyone")
    assert res["status"] == "error"
    assert "NPSSO" in res["message"]


def test_trophy_threshold(monkeypatch):
    monkeypatch.setenv("NPSSO_CODE", "fake-npsso")
    monkeypatch.setattr(psn_layer, "PSNAWP", _FakePSNAWP)
    monkeypatch.setattr(
        _FakePSNAWP,
        "users",
        {"veteran": _FakeUser(bronze=6, silver=3, gold=1), "fresh": _FakeUser(bronze=9)},
    )
    psn = PSNLayer()

    real = psn.verify_sybill("veteran")
    assert real == {"status": "success", "is_real": True, "total_trophies": 10, "online_id": "veteran"}

    fresh = psn.verify_sybill("fresh")
    assert fresh["is_real"] is False
    assert fresh["total_trophies"] == 9


def test_api_errors_are_reported_not_raised(monkeypatch):
    monkeypatch.setenv("NPSSO_CODE", "fake-npsso")
    monkeypatch.setattr(psn_layer, "PSNAWP", _FakePSNAWP)
    monkeypatch.setattr(_FakePSNAWP, "users", {})
    res = PSNLayer().verify_sybill("ghost")
    assert res["status"] == "error"
    assert "ghost" in res["message"]
