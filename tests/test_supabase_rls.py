"""Every Supabase table is RLS-protected and nothing is granted to anon.

Static checks over supabase/migrations/*.sql and the legacy sql/*.sql files
(infra audit 2026-10, INF-04). The public anon key ships to every browser, so
a table without RLS, a GRANT to anon/authenticated/PUBLIC, or a function left
executable by PUBLIC is reachable by anyone through the Supabase Data API.

Rules:
  * every CREATE TABLE has RLS enabled, either in a migration
    (ALTER TABLE ... ENABLE ROW LEVEL SECURITY) or by the lockdown migration;
  * every GRANT to anon/authenticated/PUBLIC is undone by the lockdown;
  * every CREATE FUNCTION in public/gaming is revoked from PUBLIC;
  * migrations newer than the lockdown enable RLS in the same file and never
    grant to anon/authenticated/PUBLIC.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
LEGACY = ROOT / "sql"
LOCKDOWN = MIGRATIONS / "20261020120000_lock_down_legacy_grants.sql"

_COMMENT = re.compile(r"--[^\n]*")
_CREATE_TABLE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)", re.I)
_ENABLE_RLS = re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?([\w.\"]+)\s+enable\s+row\s+level\s+security", re.I)
_GRANT = re.compile(r"grant\s+[\w\s,]+?\s+on\s+(?:table\s+)?([\w.\"]+)\s+to\s+([^;]+);", re.I)
_CREATE_FN = re.compile(r"create\s+(?:or\s+replace\s+)?function\s+([\w.\"]+)\s*\(([^)]*)\)", re.I)
_PUBLIC_ROLES = {"anon", "authenticated", "public"}


def _sql(path: Path) -> str:
    return _COMMENT.sub("", path.read_text(encoding="utf-8"))


def _qualify(name: str) -> str:
    name = name.replace('"', "").lower()
    return name if "." in name else f"public.{name}"


def _all_files() -> list[Path]:
    return sorted(LEGACY.glob("*.sql")) + sorted(MIGRATIONS.glob("*.sql"))


def _lockdown_tables() -> set[str]:
    text = _sql(LOCKDOWN)
    block = re.search(r"server_only\s+text\[\]\s*:=\s*ARRAY\[(.*?)\];", text, re.S)
    assert block, "lockdown migration lost its server_only table list"
    tables = {_qualify(t) for t in re.findall(r"'([\w.]+)'", block.group(1))}
    if "public.profiles" in text and "ENABLE ROW LEVEL SECURITY" in text:
        tables.add("public.profiles")
    return tables


def test_lockdown_migration_exists():
    assert LOCKDOWN.is_file()


def test_every_table_has_rls():
    covered = _lockdown_tables()
    created: dict[str, str] = {}
    for f in _all_files():
        text = _sql(f)
        for m in _CREATE_TABLE.finditer(text):
            created.setdefault(_qualify(m.group(1)), f.name)
        covered.update(_qualify(m.group(1)) for m in _ENABLE_RLS.finditer(text))
    missing = {t: f for t, f in created.items() if t not in covered}
    assert not missing, f"tables without RLS (add to the lockdown or enable RLS): {missing}"


def test_grants_to_public_roles_are_revoked():
    covered = _lockdown_tables()
    lockdown_text = _sql(LOCKDOWN)
    for f in _all_files():
        if f == LOCKDOWN:
            continue
        for m in _GRANT.finditer(_sql(f)):
            roles = {r.strip().lower() for r in m.group(2).split(",")}
            if roles & _PUBLIC_ROLES:
                table = _qualify(m.group(1))
                assert table in covered and f.name < LOCKDOWN.name, (
                    f"{f.name} grants {table} to {sorted(roles & _PUBLIC_ROLES)}; "
                    "the lockdown must revoke it"
                )
    assert "REVOKE ALL ON TABLE %s FROM anon, authenticated, PUBLIC" in lockdown_text


def test_functions_are_not_executable_by_public():
    lockdown_text = _sql(LOCKDOWN)
    for f in _all_files():
        if f == LOCKDOWN:
            continue
        for m in _CREATE_FN.finditer(_sql(f)):
            fn = _qualify(m.group(1))
            if not fn.startswith(("public.", "gaming.")):
                continue
            revoked_here = re.search(
                rf"revoke\s+(all|execute)[^;]*on\s+function\s+{re.escape(fn)}\b[^;]*from[^;]*public",
                _sql(f), re.I)
            revoked_in_lockdown = re.search(
                rf"revoke\s+all\s+on\s+function\s+{re.escape(fn)}\(", lockdown_text, re.I)
            assert revoked_here or revoked_in_lockdown, (
                f"{f.name}: {fn} is executable by PUBLIC (reachable as /rest/v1/rpc); revoke it"
            )


def test_new_migrations_enable_rls_and_never_grant_to_anon():
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name <= LOCKDOWN.name:
            continue
        text = _sql(f)
        enabled = {_qualify(m.group(1)) for m in _ENABLE_RLS.finditer(text)}
        for m in _CREATE_TABLE.finditer(text):
            t = _qualify(m.group(1))
            assert t in enabled, f"{f.name}: {t} must ENABLE ROW LEVEL SECURITY in the same file"
        for m in _GRANT.finditer(text):
            roles = {r.strip().lower() for r in m.group(2).split(",")}
            assert not roles & _PUBLIC_ROLES, f"{f.name}: grant to {roles} on {m.group(1)}"


def test_open_policies_and_definer_rpcs_are_closed():
    """Found live on 2026-10-20: "service role" policies scoped to PUBLIC,
    two tables without RLS, and anon-callable SECURITY DEFINER money RPCs."""
    text = _sql(MIGRATIONS / "20261020120400_close_open_policies.sql")
    assert re.search(r"policyname\s+ILIKE\s+'%service%role%'", text, re.I)
    assert "TO service_role USING (true)" in text
    for table in ("public.bot_fsm_state", "public.partner_venues"):
        assert re.search(rf"ALTER TABLE {re.escape(table)} ENABLE ROW LEVEL SECURITY", text)
    for fn in ("credit_wallet", "debit_wallet", "increment_play_points", "fn_gdpr_delete_user", "fn_award_questcoins"):
        assert f"'public.{fn}(" in text, fn
    assert "REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated" in text
