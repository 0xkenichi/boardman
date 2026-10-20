-- Close the "service role" policies that were really open to everyone, the
-- two tables still without RLS, and the SECURITY DEFINER money/admin RPCs.
--
-- Found by supabase/verify_rls.sql on the production project (2026-10-20),
-- on top of what 20261020120000_lock_down_legacy_grants.sql covers:
--
--   * Policies named "Allow service role full access" / "... service_role
--     full access ..." were created with no TO clause, so they apply to the
--     PUBLIC role (anon + authenticated) with USING (true). Together with
--     Supabase's default table grants, anyone holding the public anon key
--     could read and write public.profiles (balances), public.withdrawals,
--     public.virtual_accounts, public.circle_transactions, public.bets,
--     public.platform_fees, public.travel_pings and more. service_role
--     bypasses RLS, so these policies never did anything for it: they are
--     recreated TO service_role, which keeps their stated intent.
--   * public.bot_fsm_state and public.partner_venues had RLS off.
--   * credit_wallet, debit_wallet, increment_play_points, add_reputation,
--     fn_award_questcoins, fn_gdpr_delete_user, link_supabase_auth_user,
--     rls_auto_enable, fn_update_trending_scores and handle_new_user are
--     SECURITY DEFINER and executable by anon: /rest/v1/rpc/credit_wallet
--     could mint balance and fn_gdpr_delete_user could erase any user.
--
-- The Boardman backend and the Vercel server routes call all of these with
-- the service-role key (src/backend/supabase_client.get_supabase), so
-- nothing Boardman does needs anon or authenticated access to them.
--
-- Idempotent; every statement is guarded. Run supabase/verify_rls.sql again
-- afterwards: check 3 should list no USING (true) policy for roles=public.

-- 1. Mis-scoped "service role" policies -> TO service_role.
DO $$
DECLARE
  p record;
BEGIN
  FOR p IN
    SELECT schemaname, tablename, policyname, cmd
    FROM pg_policies
    WHERE schemaname IN ('public', 'gaming')
      AND roles = ARRAY['public']::name[]
      AND coalesce(qual, 'true') = 'true'
      AND policyname ILIKE '%service%role%'
  LOOP
    EXECUTE format('DROP POLICY %I ON %I.%I', p.policyname, p.schemaname, p.tablename);
    EXECUTE format(
      'CREATE POLICY %I ON %I.%I AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true)',
      p.policyname, p.schemaname, p.tablename
    );
  END LOOP;
END
$$;

-- 2. Tables that still had RLS off.
DO $$
BEGIN
  -- Bot conversation state: server-only.
  IF to_regclass('public.bot_fsm_state') IS NOT NULL THEN
    ALTER TABLE public.bot_fsm_state ENABLE ROW LEVEL SECURITY;
    REVOKE ALL ON TABLE public.bot_fsm_state FROM anon, authenticated, PUBLIC;
    GRANT ALL ON TABLE public.bot_fsm_state TO service_role;
  END IF;
  -- Venue directory: anyone may read it, only the server writes it.
  IF to_regclass('public.partner_venues') IS NOT NULL THEN
    ALTER TABLE public.partner_venues ENABLE ROW LEVEL SECURITY;
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.partner_venues FROM anon, authenticated, PUBLIC;
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public' AND tablename = 'partner_venues' AND policyname = 'partner_venues_select_all'
    ) THEN
      CREATE POLICY partner_venues_select_all ON public.partner_venues FOR SELECT USING (true);
    END IF;
  END IF;
END
$$;

-- 3. Money and admin RPCs: service role only.
DO $$
DECLARE
  f text;
  server_only text[] := ARRAY[
    'public.credit_wallet(uuid, numeric)',
    'public.debit_wallet(uuid, numeric)',
    'public.increment_play_points(uuid, bigint)',
    'public.add_reputation(uuid, integer, text)',
    'public.fn_award_questcoins(uuid, integer, qc_event_type, uuid, text)',
    'public.fn_gdpr_delete_user(uuid)',
    'public.link_supabase_auth_user(text, text)',
    'public.rls_auto_enable()',
    'public.fn_update_trending_scores()',
    'public.handle_new_user()',
    'public.adjust_balance(uuid, numeric)',
    'public.adjust_play_points(uuid, numeric)'
  ];
BEGIN
  FOREACH f IN ARRAY server_only LOOP
    IF to_regprocedure(f) IS NOT NULL THEN
      EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', f);
      EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
    END IF;
  END LOOP;
END
$$;
