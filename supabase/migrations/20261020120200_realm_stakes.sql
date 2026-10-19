-- Boardman money realms: real-money stake caps and the chain-tagged stake record.
-- Generated from src/backend/services/stake_caps.py — edit there, then regenerate:
-- python -m gaming.src.backend.services.stake_caps > <this file>

BEGIN;

CREATE TABLE IF NOT EXISTS realm_stakes (
  challenge_id TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  realm TEXT NOT NULL,
  chain TEXT NOT NULL,
  amount_micro BIGINT NOT NULL CHECK (amount_micro > 0),
  status TEXT NOT NULL,
  path TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (challenge_id, profile_id)
);

CREATE INDEX IF NOT EXISTS realm_stakes_profile_idx ON realm_stakes (profile_id, realm, created_at_ms);

CREATE INDEX IF NOT EXISTS realm_stakes_chain_idx ON realm_stakes (chain, status);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE realm_stakes ENABLE ROW LEVEL SECURITY;

COMMIT;
