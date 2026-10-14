"""Parsed-file cache for big state files (afm_season.json et al.)."""
from __future__ import annotations

import copy
import json
import time

import pytest

from gaming.src.stack.agentic.json_cache import ReadOnlyError, get_cache
from gaming.src.stack.agentic.store import data_dir, save_json
from gaming.src.stack.agentic.games.football_managers import season as S


def _write_raw(name: str, payload) -> None:
    (data_dir() / name).write_text(json.dumps(payload), encoding="utf-8")


def test_view_is_shared_and_read_only():
    save_json("perf_probe.json", {"a": {"b": [1, 2]}})
    c = get_cache()
    v1 = c.view("perf_probe.json", {})
    v2 = c.view("perf_probe.json", {})
    assert v1 is v2
    with pytest.raises(ReadOnlyError):
        v1["a"]["c"] = 1
    with pytest.raises(ReadOnlyError):
        v1["a"]["b"].append(3)
    with pytest.raises(ReadOnlyError):
        v1.setdefault("z", 1)
    # copies out of a view are plain and mutable
    d = copy.deepcopy(v1)
    d["a"]["b"].append(3)
    assert type(d) is dict and type(d["a"]["b"]) is list
    assert json.loads(json.dumps(v1)) == {"a": {"b": [1, 2]}}


def test_copy_is_private():
    save_json("perf_probe.json", {"n": [1]})
    c = get_cache()
    a = c.copy("perf_probe.json", {})
    a["n"].append(2)
    assert c.copy("perf_probe.json", {}) == {"n": [1]}
    assert c.view("perf_probe.json", {}) == {"n": [1]}


def test_external_write_is_picked_up_without_invalidate():
    c = get_cache()
    save_json("perf_probe.json", {"v": 1})
    assert c.view("perf_probe.json", {})["v"] == 1
    time.sleep(0.01)
    _write_raw("perf_probe.json", {"v": 22})  # another process, in-place write
    assert c.view("perf_probe.json", {})["v"] == 22


def test_missing_file_returns_default_copy():
    c = get_cache()
    d = c.copy("perf_nope.json", {"x": []})
    d["x"].append(1)
    assert c.copy("perf_nope.json", {"x": []}) == {"x": []}


def test_season_save_invalidates_and_reads_hit_cache():
    c = get_cache()
    st = S._state()
    st["pending_joins"] = ["agent_x"]
    S._save(st)
    parses = c.parses
    for _ in range(5):
        assert S._state_view()["pending_joins"] == ["agent_x"]
        assert S._state()["pending_joins"] == ["agent_x"]
    assert c.parses == parses + 1  # one parse serves every read until the next write
    st = S._state()
    st["pending_joins"] = []
    S._save(st)
    assert S._state_view()["pending_joins"] == []


def test_cached_view_is_much_faster_than_parse():
    # ~2MB of season-shaped JSON; the cached view must not re-parse it
    big = {"season": {"matchdays": {str(i): {"results": [{"feed": ["x" * 40] * 50}]} for i in range(200)}}, "pending_joins": []}
    save_json(S.STATE_FILE, big)
    get_cache().invalidate(S.STATE_FILE)
    t = time.perf_counter()
    S._state_view()
    cold = time.perf_counter() - t
    t = time.perf_counter()
    for _ in range(20):
        S._state_view()
    warm = (time.perf_counter() - t) / 20
    assert warm < cold / 20
