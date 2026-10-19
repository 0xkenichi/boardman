-- Follow-up for databases that already ran 20261016120100_channels_state.sql:
-- the screenshot-reuse guard (audit/channels M-5) added channel_evidence there,
-- but an applied migration is never re-run. Idempotent; safe on fresh databases.
BEGIN;

CREATE TABLE IF NOT EXISTS channel_evidence (
  digest TEXT PRIMARY KEY,
  challenge_id TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  first_seen_ms BIGINT NOT NULL
);

-- Never reachable with the anon/authenticated keys.
ALTER TABLE channel_evidence ENABLE ROW LEVEL SECURITY;

COMMIT;
