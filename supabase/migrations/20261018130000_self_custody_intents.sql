-- Boardman self-custody passkey wallets: prepared intents (lock / withdraw)
-- that the player approves with a passkey. Accounts live in payment_wallets.
-- Generated from src/backend/services/self_custody/store.py — edit there, then regenerate:
-- python -m gaming.src.backend.services.self_custody.store > <this file>

BEGIN;

CREATE TABLE IF NOT EXISTS self_custody_intents (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  action TEXT NOT NULL,
  chain TEXT NOT NULL,
  account TEXT NOT NULL,
  challenge_id TEXT,
  amount_micro BIGINT NOT NULL,
  to_address TEXT,
  calls JSONB NOT NULL,
  detail JSONB NOT NULL,
  status TEXT NOT NULL,
  token_hash TEXT,
  user_op_hash TEXT,
  tx_hash TEXT,
  from_block BIGINT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT NOT NULL,
  confirmed_at_ms BIGINT
);

CREATE INDEX IF NOT EXISTS self_custody_intents_profile_idx ON self_custody_intents (profile_id, created_at_ms);

CREATE INDEX IF NOT EXISTS self_custody_intents_status_idx ON self_custody_intents (status, updated_at_ms);

CREATE INDEX IF NOT EXISTS self_custody_intents_match_idx ON self_custody_intents (challenge_id, profile_id);

CREATE UNIQUE INDEX IF NOT EXISTS self_custody_intents_tx_idx ON self_custody_intents (tx_hash);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE self_custody_intents ENABLE ROW LEVEL SECURITY;

COMMIT;
