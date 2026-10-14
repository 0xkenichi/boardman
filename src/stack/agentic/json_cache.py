"""Read cache for big JSON state files under the agentic data dir.

Some state files are large (afm_season.json is ~20MB) and were re-parsed on
every request. This keeps one parsed version per file in memory, keyed by the
file's identity on disk — (path, inode, mtime_ns, size) — so a write from any
process (atomic tmp+replace gives a new inode) is picked up on the next read,
and a write from this process can drop the entry explicitly via `invalidate`.

Callers pick how they read:

  view(name, default)  shared, deeply read-only structure (dict/list
                       subclasses that raise on mutation). Zero-copy; for
                       read paths. `copy.deepcopy`/pickle of a view yields
                       plain mutable containers.
  copy(name, default)  a private mutable copy (pickle round-trip of the
                       cached version — about half the cost of re-parsing).
                       For read-modify-write paths.

An optional `transform` lets a caller cache a slimmed projection instead of
the whole file (e.g. metrics over the match archive drop move lists).
"""
from __future__ import annotations

import os
import pickle
import threading
from typing import Any, Callable, Optional

from gaming.src.stack.agentic.store import data_dir, load_json


class ReadOnlyError(TypeError):
    pass


def _ro(*_a: Any, **_k: Any) -> Any:
    raise ReadOnlyError("cached read-only view — copy it before mutating")


class FrozenDict(dict):
    __slots__ = ()
    __setitem__ = __delitem__ = __ior__ = _ro  # type: ignore[assignment]
    setdefault = pop = popitem = clear = update = _ro  # type: ignore[assignment]

    def __reduce_ex__(self, protocol: Any) -> Any:  # pickle / deepcopy → plain dict
        return (dict, (dict(self),))

    def __copy__(self) -> dict:
        return dict(self)


class FrozenList(list):
    __slots__ = ()
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _ro  # type: ignore[assignment]
    append = extend = insert = remove = pop = clear = sort = reverse = _ro  # type: ignore[assignment]

    def __reduce_ex__(self, protocol: Any) -> Any:
        return (list, (list(self),))

    def __copy__(self) -> list:
        return list(self)


def freeze(obj: Any) -> Any:
    if isinstance(obj, dict):
        return FrozenDict((k, freeze(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return FrozenList(freeze(v) for v in obj)
    return obj


def thaw(obj: Any) -> Any:
    """Plain mutable deep copy of a (possibly frozen) structure."""
    return pickle.loads(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def _identity(path: str) -> Optional[tuple]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


class _Entry:
    __slots__ = ("key", "frozen", "pickled")

    def __init__(self, key: tuple, frozen: Any, pickled: Optional[bytes]) -> None:
        self.key = key
        self.frozen = frozen
        self.pickled = pickled


class JsonFileCache:
    def __init__(self) -> None:
        self._entries: dict[tuple, _Entry] = {}
        self._lock = threading.RLock()
        self.parses = 0  # observability for tests / benchmarks

    def _entry(self, name: str, transform: Optional[Callable[[Any], Any]]) -> Optional[_Entry]:
        path = str(data_dir() / name)
        ident = _identity(path)
        if ident is None:
            return None
        slot = (path, id(transform) if transform else None)
        key = (*slot, *ident)
        ent = self._entries.get(slot)
        if ent is not None and ent.key == key:
            return ent
        with self._lock:
            ent = self._entries.get(slot)
            ident = _identity(path)
            if ident is None:
                return None
            key = (*slot, *ident)
            if ent is not None and ent.key == key:
                return ent
            raw = load_json(name, None)
            self.parses += 1
            if raw is None:
                return None
            # A file replaced mid-read changes identity; next read re-parses.
            if _identity(path) != ident:
                key = (*slot, None)
            data = transform(raw) if transform else raw
            # Pickle the plain structure now: unpickling plain containers is
            # native-speed, unlike unpickling the frozen subclasses.
            blob = None if transform else pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            ent = _Entry(key, freeze(data), blob)
            self._entries[slot] = ent
            return ent

    def view(self, name: str, default: Any, *, transform: Optional[Callable[[Any], Any]] = None) -> Any:
        ent = self._entry(name, transform)
        if ent is None:
            return freeze(default)
        return ent.frozen

    def copy(self, name: str, default: Any, *, transform: Optional[Callable[[Any], Any]] = None) -> Any:
        ent = self._entry(name, transform)
        if ent is None:
            return thaw(default)
        if ent.pickled is None:
            return thaw(ent.frozen)
        return pickle.loads(ent.pickled)

    def invalidate(self, name: Optional[str] = None) -> None:
        with self._lock:
            if name is None:
                self._entries.clear()
                return
            path = str(data_dir() / name)
            for slot in [s for s in self._entries if s[0] == path]:
                self._entries.pop(slot, None)


_CACHE = JsonFileCache()


def get_cache() -> JsonFileCache:
    return _CACHE
