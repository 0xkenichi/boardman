-- Initial Supabase schema helpers for rematch/Boardman
-- Run this in the Supabase SQL editor (or psql against the DB)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Helper schema for immutable audit tables and supporting objects
CREATE SCHEMA IF NOT EXISTS gaming;

-- Wallet credit audit: immutable records of inbound credits
CREATE TABLE IF NOT EXISTS gaming.wallet_credit_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id uuid NOT NULL,
  amount numeric NOT NULL,
  tx_hash text,
  reason text,
  metadata jsonb,
  inserted_at timestamptz DEFAULT now()
);

-- Wallet debit audit: immutable records of outbound debits
CREATE TABLE IF NOT EXISTS gaming.wallet_debit_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id uuid NOT NULL,
  amount numeric NOT NULL,
  tx_hash text,
  reason text,
  metadata jsonb,
  inserted_at timestamptz DEFAULT now()
);

-- Minimal withdrawals table (safe to create if migrations were not applied)
CREATE TABLE IF NOT EXISTS public.withdrawals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id uuid NOT NULL,
  amount numeric NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Atomic adjust_balance RPC used by backend to avoid race conditions.
-- It locks the profile row, updates balance, and returns the new balance.
CREATE OR REPLACE FUNCTION public.adjust_balance(p_id uuid, delta numeric)
RETURNS numeric
LANGUAGE plpgsql
AS $$
DECLARE
  cur_balance numeric;
BEGIN
  PERFORM 1 FROM public.profiles WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'profile not found';
  END IF;
  SELECT COALESCE(balance, 0) INTO cur_balance FROM public.profiles WHERE id = p_id FOR UPDATE;
  cur_balance := cur_balance + delta;
  UPDATE public.profiles SET balance = cur_balance, updated_at = now() WHERE id = p_id;
  RETURN cur_balance;
END;
$$;

-- Atomic adjust_play_points RPC used to increment play points safely.
CREATE OR REPLACE FUNCTION public.adjust_play_points(p_id uuid, delta numeric)
RETURNS numeric
LANGUAGE plpgsql
AS $$
DECLARE
  cur_points numeric;
BEGIN
  PERFORM 1 FROM public.profiles WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'profile not found';
  END IF;
  SELECT COALESCE(play_points, 0) INTO cur_points FROM public.profiles WHERE id = p_id FOR UPDATE;
  cur_points := cur_points + delta;
  UPDATE public.profiles SET play_points = cur_points, updated_at = now() WHERE id = p_id;
  RETURN cur_points;
END;
$$;

-- Grant read access to the public role for audit tables so PostgREST can query them if needed.
GRANT SELECT ON gaming.wallet_credit_audit TO anon, authenticated, public;
GRANT SELECT ON gaming.wallet_debit_audit TO anon, authenticated, public;

-- Idempotent done
