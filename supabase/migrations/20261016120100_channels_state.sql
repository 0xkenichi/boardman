-- Boardman channels state: conversation state machines, one-time tokens
-- (withdraw links, PIN resets), rate-limit events, inbound webhook dedupe
-- and the notification outbox. Lives in the agentic store's database.
-- Generated from src/channels/core/store.py — edit there, then regenerate:
-- python -m gaming.src.channels.core.store > <this file>

BEGIN;

CREATE TABLE IF NOT EXISTS channel_conversations (
  channel TEXT NOT NULL,
  external_id TEXT NOT NULL,
  flow TEXT,
  step TEXT,
  data JSONB NOT NULL,
  version BIGINT NOT NULL DEFAULT 1,
  expires_at_ms BIGINT,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (channel, external_id)
);

CREATE TABLE IF NOT EXISTS channel_tokens (
  token_hash TEXT PRIMARY KEY,
  purpose TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  external_id TEXT,
  amount_micro BIGINT,
  payload JSONB NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT NOT NULL,
  consumed_at_ms BIGINT,
  result JSONB
);

CREATE INDEX IF NOT EXISTS channel_tokens_profile_idx ON channel_tokens (profile_id, created_at_ms);

CREATE TABLE IF NOT EXISTS channel_rate_events (
  id BIGSERIAL PRIMARY KEY,
  bucket TEXT NOT NULL,
  at_ms BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS channel_rate_bucket_idx ON channel_rate_events (bucket, at_ms);

CREATE TABLE IF NOT EXISTS channel_inbound (
  channel TEXT NOT NULL,
  message_id TEXT NOT NULL,
  external_id TEXT,
  status TEXT NOT NULL,
  payload JSONB,
  received_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (channel, message_id)
);

CREATE INDEX IF NOT EXISTS channel_inbound_status_idx ON channel_inbound (status, received_at_ms);

CREATE TABLE IF NOT EXISTS channel_outbox (
  id BIGSERIAL PRIMARY KEY,
  channel TEXT NOT NULL,
  external_id TEXT NOT NULL,
  profile_id TEXT,
  kind TEXT NOT NULL,
  mode TEXT NOT NULL,
  template TEXT,
  provider_message_id TEXT,
  status TEXT NOT NULL,
  error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS channel_outbox_provider_idx ON channel_outbox (provider_message_id);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE channel_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_rate_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_inbound ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_outbox ENABLE ROW LEVEL SECURITY;

COMMIT;
