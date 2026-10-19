-- Lock down the legacy grants and the tables that never had RLS.
--
-- Infra audit 2026-10 (docs/security/AUDIT_2026-10_infra.md, INF-04):
--   * 000_initial_schema.sql granted SELECT on gaming.wallet_credit_audit and
--     gaming.wallet_debit_audit to anon/authenticated/public, without RLS.
--   * 001_approval_flow.sql granted SELECT, INSERT, UPDATE on
--     gaming.tx_approvals to anon/authenticated/public, without RLS. If the
--     gaming schema is exposed through the Data API, anyone holding the public
--     anon key could read or approve pending spends.
--   * public.adjust_balance / public.adjust_play_points are callable by PUBLIC
--     (Postgres default) and so reachable as /rest/v1/rpc/* with the anon key.
--   * public.withdrawals, public.football_players and the gaming.tournament*
--     tables were created without RLS.
--
-- The backend and the Vercel server routes use the service-role key for all
-- of these (src/backend/supabase_client.get_supabase, frontend/lib/
-- supabaseAdmin.ts), and service_role bypasses RLS, so nothing the product
-- does needs anon or authenticated access to them.
--
-- Idempotent and safe on a database where some tables do not exist: every
-- statement is guarded by to_regclass / to_regprocedure.
-- Before applying, run supabase/verify_rls.sql and keep its output.

DO $$
DECLARE
  t text;
  server_only text[] := ARRAY[
    -- legacy money / approval tables (gaming schema)
    'gaming.wallet_credit_audit',
    'gaming.wallet_debit_audit',
    'gaming.tx_approvals',
    'gaming.escrow_audit',
    'gaming.challenges',
    'gaming.tournaments',
    'gaming.tournament_entries',
    'gaming.tournament_matches',
    -- legacy public tables created without RLS
    'public.withdrawals',
    'public.football_players',
    'public.boardman_waitlist',
    -- agentic ledger (20261014/20261015)
    'public.storage_meta',
    'public.ledger_balances',
    'public.ledger_txs',
    'public.ledger_escrows',
    'public.agentic_matches',
    'public.spectator_books',
    'public.lp_pools',
    'public.settlement_journal',
    'public.match_leases',
    'public.signer_locks',
    'public.onchain_txs',
    'public.tournament_payouts',
    'public.wallet_bridge_transfers',
    'public.house_log_games',
    'public.house_log_txs',
    -- channels
    'public.channel_identities',
    'public.channel_link_codes',
    'public.channel_conversations',
    'public.channel_tokens',
    'public.channel_rate_events',
    'public.channel_inbound',
    'public.channel_outbox',
    -- payments / custody
    'public.paycrest_orders',
    'public.paycrest_webhook_events',
    'public.payment_wallets',
    'public.bridge_transfers',
    'public.self_custody_intents',
    'public.self_custody_wallet_requests'
  ];
BEGIN
  FOREACH t IN ARRAY server_only LOOP
    IF to_regclass(t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
      EXECUTE format('REVOKE ALL ON TABLE %s FROM anon, authenticated, PUBLIC', t);
      EXECUTE format('GRANT ALL ON TABLE %s TO service_role', t);
    END IF;
  END LOOP;
END
$$;

-- public.profiles holds balances. It was created in the dashboard, so its RLS
-- state is not in this repo. Turn RLS on (a no-op if it already is) and make
-- sure the anon role cannot write it directly. Read/update policies for
-- signed-in users, if any exist, are left untouched.
DO $$
BEGIN
  IF to_regclass('public.profiles') IS NOT NULL THEN
    ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.profiles FROM anon, PUBLIC;
  END IF;
END
$$;

-- Balance RPCs: service role only.
DO $$
BEGIN
  IF to_regprocedure('public.adjust_balance(uuid, numeric)') IS NOT NULL THEN
    REVOKE ALL ON FUNCTION public.adjust_balance(uuid, numeric) FROM PUBLIC, anon, authenticated;
    GRANT EXECUTE ON FUNCTION public.adjust_balance(uuid, numeric) TO service_role;
  END IF;
  IF to_regprocedure('public.adjust_play_points(uuid, numeric)') IS NOT NULL THEN
    REVOKE ALL ON FUNCTION public.adjust_play_points(uuid, numeric) FROM PUBLIC, anon, authenticated;
    GRANT EXECUTE ON FUNCTION public.adjust_play_points(uuid, numeric) TO service_role;
  END IF;
END
$$;

-- The gaming schema is server-only.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'gaming') THEN
    REVOKE USAGE ON SCHEMA gaming FROM anon, authenticated, PUBLIC;
    GRANT USAGE ON SCHEMA gaming TO service_role;
  END IF;
END
$$;
