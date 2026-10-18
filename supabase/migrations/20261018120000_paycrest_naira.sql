-- Boardman naira rail (Paycrest on/off-ramp) and CCTP bridge legs.
-- Lives in the agentic store's database. No KYC columns, by design.
-- Generated from src/backend/services/paycrest/store.py — edit there, then regenerate:
-- python -m gaming.src.backend.services.paycrest.store > <this file>

BEGIN;

CREATE TABLE IF NOT EXISTS paycrest_orders (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  direction TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  channel TEXT,
  external_id TEXT,
  status TEXT NOT NULL,
  paycrest_id TEXT,
  paycrest_status TEXT,
  amount_ngn TEXT,
  amount_usdc TEXT,
  rate TEXT,
  quote JSONB,
  provider_account JSONB,
  details JSONB,
  bridge_id TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at_ms BIGINT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT,
  settled_at_ms BIGINT
);

CREATE INDEX IF NOT EXISTS paycrest_orders_profile_idx ON paycrest_orders (profile_id, created_at_ms);

CREATE INDEX IF NOT EXISTS paycrest_orders_status_idx ON paycrest_orders (status, updated_at_ms);

CREATE INDEX IF NOT EXISTS paycrest_orders_pcid_idx ON paycrest_orders (paycrest_id);

CREATE TABLE IF NOT EXISTS paycrest_webhook_events (
  event_key TEXT PRIMARY KEY,
  paycrest_id TEXT,
  event TEXT,
  status TEXT,
  outcome TEXT,
  received_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_wallets (
  profile_id TEXT NOT NULL,
  chain TEXT NOT NULL,
  wallet_id TEXT NOT NULL,
  address TEXT NOT NULL,
  account_type TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  PRIMARY KEY (profile_id, chain)
);

CREATE TABLE IF NOT EXISTS bridge_transfers (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  src_chain TEXT NOT NULL,
  dst_chain TEXT NOT NULL,
  amount_usdc TEXT NOT NULL,
  from_wallet_id TEXT NOT NULL,
  mint_recipient TEXT NOT NULL,
  fast INTEGER NOT NULL DEFAULT 0,
  max_fee_usdc TEXT,
  status TEXT NOT NULL,
  approve_tx_id TEXT,
  burn_tx_id TEXT,
  burn_tx_hash TEXT,
  message TEXT,
  attestation TEXT,
  mint_tx_id TEXT,
  mint_tx_hash TEXT,
  minted_usdc TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at_ms BIGINT,
  error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS bridge_transfers_status_idx ON bridge_transfers (status, next_attempt_at_ms);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE paycrest_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE paycrest_webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE bridge_transfers ENABLE ROW LEVEL SECURITY;

COMMIT;
