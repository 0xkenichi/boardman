"""Opt-in Postgres test mode (``BOARDMAN_TEST_DATABASE_URL``), shared by
conftest.py and the spawned helpers in _proc_helpers.py.

On SQLite every data dir has its own database file, and tests rely on that:
pointing ``BOARDMAN_AGENTIC_DATA`` somewhere new means an empty store. Postgres
keeps the same rule: each test owns a base name, and each data dir it touches
gets its own schema ``<base>_<hash(data dir)>``. The app reaches it through an
ordinary URL whose ``search_path`` is pinned to that schema, and whose
``application_name`` is the schema too, so teardown can cut off any straggling
connection (daemon threads, child processes) before dropping it.
"""
from __future__ import annotations

import hashlib
import json
import os
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

# Handed to spawned children (conftest.py does not run there).
CHILD_ENV = "BOARDMAN_TEST_PG_CHILD"


def schema_for(base: str, data_dir: str | os.PathLike) -> str:
    digest = hashlib.sha1(os.path.realpath(os.fspath(data_dir)).encode()).hexdigest()[:10]
    return f"{base}_{digest}"


def url_for(url: str, schema: str) -> str:
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query) if k not in {"options", "application_name"}]
    q += [("options", f"-c search_path={schema}"), ("application_name", schema)]
    return urlunsplit(parts._replace(query=urlencode(q, quote_via=quote)))


def create_schema(conn, schema: str) -> None:
    """CREATE SCHEMA IF NOT EXISTS, tolerating a concurrent creator."""
    try:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    except Exception as exc:  # two processes racing on pg_namespace
        if "already exists" not in str(exc) and "duplicate key" not in str(exc):
            raise


def child_env(url: str, base: str) -> str:
    return json.dumps({"url": url, "base": base})


def use_in_child(data_dir: str) -> None:
    """In a spawned helper: point the app at the parent test's schema for
    ``data_dir`` (no-op on SQLite)."""
    import multiprocessing

    if multiprocessing.parent_process() is None:
        return  # called in the test process itself: conftest already routes it
    raw = os.environ.get(CHILD_ENV)
    if not raw or os.environ.get("BOARDMAN_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        return  # SQLite mode, or the test chose a store explicitly
    spec = json.loads(raw)
    schema = schema_for(spec["base"], data_dir)
    import psycopg  # type: ignore

    with psycopg.connect(spec["url"], autocommit=True) as conn:
        create_schema(conn, schema)
    os.environ["BOARDMAN_DATABASE_URL"] = url_for(spec["url"], schema)
