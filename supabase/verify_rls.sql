-- Read-only checks of what the public anon key can reach. Run in the Supabase
-- SQL editor (or psql) before and after applying
-- migrations/20261020120000_lock_down_legacy_grants.sql. Changes nothing.
-- Every query should return zero rows once the lockdown is applied, except
-- (3), which lists policies to review by hand.

-- 1. Tables in API-reachable schemas with RLS switched off.
SELECT n.nspname AS schema, c.relname AS table_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname IN ('public', 'gaming')
  AND NOT c.relrowsecurity
ORDER BY 1, 2;

-- 2. Table privileges held by anon / authenticated / PUBLIC in those schemas
--    (RLS still applies to these, but a grant plus a permissive policy or
--    RLS-off table is a hole).
SELECT table_schema, table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privileges
FROM information_schema.role_table_grants
WHERE table_schema IN ('public', 'gaming')
  AND grantee IN ('anon', 'authenticated', 'PUBLIC')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- 3. Every RLS policy that lets anon or authenticated in. Review each one.
SELECT schemaname, tablename, policyname, cmd, roles, qual, with_check
FROM pg_policies
WHERE schemaname IN ('public', 'gaming')
  AND (roles && ARRAY['anon', 'authenticated', 'public']::name[])
ORDER BY 1, 2, 3;

-- 4. Functions in public/gaming that anon can execute (exposed as /rest/v1/rpc/*).
SELECT n.nspname AS schema, p.proname AS function_name,
       pg_get_function_identity_arguments(p.oid) AS args,
       p.prosecdef AS security_definer
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('public', 'gaming')
  AND has_function_privilege('anon', p.oid, 'EXECUTE')
ORDER BY 1, 2;

-- 5. Can anon use the gaming schema at all?
SELECT has_schema_privilege('anon', 'gaming', 'USAGE') AS anon_can_use_gaming
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'gaming');
