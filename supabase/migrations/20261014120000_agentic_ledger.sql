-- Boardman agentic ledger v2: ledger, matches, spectator books, LP pools,
-- settlement journal, match leases, on-chain tx/nonce records,
-- tournament payouts and the house log.
-- Generated from src/stack/agentic/db/schema.py — edit there, then
-- regenerate: python -m gaming.src.stack.agentic.db.schema > <this file>
-- Money columns are integer micro-USDC (6 decimals).

BEGIN;

CREATE TABLE IF NOT EXISTS storage_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_balances (
  wallet TEXT PRIMARY KEY,
  balance_micro BIGINT NOT NULL DEFAULT 0 CHECK (balance_micro >= 0),
  scale SMALLINT NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_txs (
  id BIGSERIAL PRIMARY KEY,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  wallet TEXT,
  ref TEXT,
  reason TEXT,
  amount_micro BIGINT,
  balance_after_micro BIGINT,
  doc JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS ledger_txs_wallet_idx ON ledger_txs (wallet, id);

CREATE INDEX IF NOT EXISTS ledger_txs_ref_idx ON ledger_txs (ref);

CREATE INDEX IF NOT EXISTS ledger_txs_reason_idx ON ledger_txs (reason);

CREATE TABLE IF NOT EXISTS ledger_escrows (
  match_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  stake_micro BIGINT NOT NULL CHECK (stake_micro >= 0),
  agent_a_wallet TEXT NOT NULL,
  agent_b_wallet TEXT NOT NULL,
  result TEXT,
  created_at TEXT NOT NULL,
  settled_at TEXT,
  doc JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS ledger_escrows_status_idx ON ledger_escrows (status);

CREATE TABLE IF NOT EXISTS agentic_matches (
  match_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  created_at TEXT,
  updated_at TEXT,
  settled_at TEXT,
  version BIGINT NOT NULL DEFAULT 1,
  doc JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS agentic_matches_status_idx ON agentic_matches (status, settled_at);

CREATE INDEX IF NOT EXISTS agentic_matches_updated_idx ON agentic_matches (updated_at);

CREATE TABLE IF NOT EXISTS spectator_books (
  match_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  created_at TEXT,
  updated_at TEXT,
  settled_at TEXT,
  version BIGINT NOT NULL DEFAULT 1,
  doc JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS spectator_books_status_idx ON spectator_books (status, settled_at);

CREATE TABLE IF NOT EXISTS lp_pools (
  agent_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT,
  updated_at TEXT,
  settled_at TEXT,
  version BIGINT NOT NULL DEFAULT 1,
  doc JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS settlement_journal (
  match_id TEXT NOT NULL,
  step TEXT NOT NULL,
  owner TEXT,
  created_at TEXT NOT NULL,
  detail JSONB,
  PRIMARY KEY (match_id, step)
);

CREATE TABLE IF NOT EXISTS match_leases (
  match_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  epoch BIGINT NOT NULL DEFAULT 1,
  acquired_at_ms BIGINT NOT NULL,
  heartbeat_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS signer_locks (
  chain_key TEXT NOT NULL,
  signer TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (chain_key, signer)
);

CREATE TABLE IF NOT EXISTS onchain_txs (
  id BIGSERIAL PRIMARY KEY,
  chain_key TEXT NOT NULL,
  signer TEXT NOT NULL,
  nonce BIGINT NOT NULL CHECK (nonce >= 0),
  label TEXT NOT NULL,
  status TEXT NOT NULL,
  tx_hash TEXT,
  created_at TEXT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  block_number BIGINT,
  error TEXT
);

CREATE INDEX IF NOT EXISTS onchain_txs_status_idx ON onchain_txs (status);

CREATE INDEX IF NOT EXISTS onchain_txs_signer_idx ON onchain_txs (chain_key, signer, nonce);

CREATE INDEX IF NOT EXISTS onchain_txs_hash_idx ON onchain_txs (tx_hash);

CREATE TABLE IF NOT EXISTS tournament_payouts (
  tournament_key TEXT NOT NULL,
  place INTEGER NOT NULL,
  profile_id TEXT NOT NULL,
  amount_micro BIGINT NOT NULL CHECK (amount_micro >= 0),
  idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  claimed_by TEXT,
  claimed_at_ms BIGINT,
  transaction_id TEXT,
  tx_hash TEXT,
  error TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tournament_key, place)
);

CREATE TABLE IF NOT EXISTS house_log_games (
  match_id TEXT PRIMARY KEY,
  game_id TEXT,
  status TEXT,
  stake_usdc TEXT,
  white_agent_id TEXT,
  black_agent_id TEXT,
  agent_a_id TEXT,
  agent_b_id TEXT,
  winner_agent_id TEXT,
  result TEXT,
  settlement_mode TEXT,
  created_at TEXT,
  settled_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS house_log_txs (
  tx_hash TEXT PRIMARY KEY,
  step TEXT,
  match_id TEXT,
  agent_id TEXT,
  explorer TEXT,
  created_at TEXT
);

CREATE INDEX IF NOT EXISTS house_log_txs_match_idx ON house_log_txs (match_id);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE storage_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_txs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_escrows ENABLE ROW LEVEL SECURITY;
ALTER TABLE agentic_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE spectator_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE lp_pools ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlement_journal ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE signer_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE onchain_txs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tournament_payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE house_log_games ENABLE ROW LEVEL SECURITY;
ALTER TABLE house_log_txs ENABLE ROW LEVEL SECURITY;

INSERT INTO storage_meta (key, value, updated_at)
VALUES ('schema_version', '1', now()::text)
ON CONFLICT (key) DO NOTHING;

COMMIT;
