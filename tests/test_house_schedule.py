"""House schedule: clock-aligned set-time rounds + cadence_mode passthrough."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))


def test_next_round_wait_aligns_to_the_boundary():
    from gaming.src.stack.agentic.house_schedule import next_round_wait_sec

    now = datetime(2026, 10, 3, 12, 43, 21, tzinfo=timezone.utc)
    w = next_round_wait_sec(now, period_sec=3600)
    # 12:43:21 → 13:00:00 is 16m39s, plus the small wake buffer
    assert 960 <= w <= 1004
    # seconds before the boundary → a tiny wait, never a full hour
    almost = datetime(2026, 10, 3, 12, 59, 59, tzinfo=timezone.utc)
    assert 0 < next_round_wait_sec(almost, period_sec=3600) <= 4
    # sub-hour periods align to their own boundary
    w15 = next_round_wait_sec(now, period_sec=900)
    assert 0 < w15 <= 900 + 3
    # degenerate periods clamp to at least a minute
    assert next_round_wait_sec(now, period_sec=1) >= 1


def test_cadence_mode_roundtrips_through_the_store():
    from gaming.src.stack.agentic.house_schedule import (
        read_schedule,
        write_schedule,
    )

    write_schedule(set_by="test", cadence_sec=3600, cadence_mode="on_the_hour")
    sch = read_schedule()
    assert sch["cadence_mode"] == "on_the_hour"
    assert sch["cadence_sec"] == 3600
    assert sch["enabled"] is True
    # unknown keys are dropped; known keys survive later writes
    write_schedule(set_by="test", nonsense=1)
    cur = read_schedule()
    assert "nonsense" not in cur
    assert cur["cadence_mode"] == "on_the_hour"
