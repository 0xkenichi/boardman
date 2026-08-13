-- Approval flow for spectator spends (bets / LP deposits)
-- Run in the Supabase SQL editor (or psql). Idempotent.

-- Pending transaction approvals: created by the web backend, resolved by the
-- Telegram bot when the user taps Yes / No / Always approve.
CREATE TABLE IF NOT EXISTS gaming.tx_approvals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id uuid NOT NULL,
  action text NOT NULL,              -- spectator_bet | lp_deposit
  payload jsonb,                     -- {amount, side, match_id, agent_id, ...}
  status text NOT NULL DEFAULT 'pending',  -- pending | approved | denied | expired
  expires_at timestamptz NOT NULL,
  chat_id bigint,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

-- Per-action approval preference: 'ask' (prompt in Telegram each time) or
-- 'always' (skip the prompt). Kept per action type so users can allow bets
-- but still gate LP deposits (or vice versa).
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS approval_mode_spectator_bet text NOT NULL DEFAULT 'ask';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS approval_mode_lp_deposit text NOT NULL DEFAULT 'ask';

GRANT SELECT, INSERT, UPDATE ON gaming.tx_approvals TO anon, authenticated, public;
