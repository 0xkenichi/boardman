-- Boardman self-custody passkey wallets: wallet link / change requests
-- (signed setup proof, in-chat confirmation, change cool-down).
-- Generated from src/backend/services/self_custody/store.py — edit there, then regenerate:
-- python -m gaming.src.backend.services.self_custody.store requests > <this file>

BEGIN;

CREATE TABLE IF NOT EXISTS self_custody_wallet_requests (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  chain TEXT NOT NULL,
  evm_chain_id BIGINT NOT NULL,
  address TEXT NOT NULL,
  credential_id TEXT,
  previous_address TEXT,
  token_hash TEXT,
  message TEXT NOT NULL,
  confirm_hash TEXT,
  status TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT NOT NULL,
  proved_at_ms BIGINT,
  confirmed_at_ms BIGINT,
  active_at_ms BIGINT
);

CREATE INDEX IF NOT EXISTS self_custody_wallet_requests_profile_idx ON self_custody_wallet_requests (profile_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS self_custody_wallet_requests_confirm_idx ON self_custody_wallet_requests (confirm_hash);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE self_custody_wallet_requests ENABLE ROW LEVEL SECURITY;

COMMIT;
