-- Boardman channels: one profile, many chat identities (docs/channels/CHANNELS_DESIGN.md §2).
-- Lives in the profiles database (Supabase). Idempotent; run in the SQL editor
-- or psql. Read by src/channels/core/identity/repo.py with the service role.
--
-- After applying: python scripts/backfill_channel_identities.py (dry run),
-- then again with --apply.

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.channel_identities (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id          uuid NOT NULL REFERENCES public.profiles(id),
  channel             text NOT NULL CHECK (channel IN ('telegram','whatsapp','web_wallet','email','imessage')),
  external_id         text NOT NULL,         -- TG user id | WA wa_id (BSUID later) | 0x lowercased | Apple id
  address             text,                  -- where to deliver: TG chat id | E.164 phone | null
  handle              text,                  -- @username / WA profile name (display only, not unique)
  country_hint        char(2),               -- from the phone calling code (WA)
  verified_at         timestamptz,           -- when control of this identity was proven
  verify_method       text,                  -- tg_login | inbound_message | link_code | wallet_sig | backfill
  opted_in_at         timestamptz,           -- WhatsApp: consent to business-initiated messages
  opted_out_at        timestamptz,
  last_inbound_at     timestamptz,           -- WhatsApp 24 h customer-service window
  notify_priority     smallint NOT NULL DEFAULT 100,  -- lower = preferred for notices
  revoked_at          timestamptz,
  withdraw_hold_until timestamptz,           -- set when a channel is linked to an existing profile
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (channel, external_id)
);

CREATE INDEX IF NOT EXISTS channel_identities_profile_idx ON public.channel_identities (profile_id);

-- One-time link codes. Only an HMAC-SHA256 of the code is stored.
CREATE TABLE IF NOT EXISTS public.channel_link_codes (
  code_hash     text PRIMARY KEY,
  profile_id    uuid NOT NULL REFERENCES public.profiles(id),
  purpose       text NOT NULL CHECK (purpose IN ('link_channel','web_login')),
  issued_via    text NOT NULL,               -- channel that was already signed in
  browser_nonce text,                        -- web_login only
  expires_at    timestamptz NOT NULL,        -- 10 min
  attempts      smallint NOT NULL DEFAULT 0,
  consumed_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS channel_link_codes_profile_idx ON public.channel_link_codes (profile_id, created_at);

-- An empty profile merged into another one by account linking.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS merged_into uuid;

-- Service role only: never readable or writable with the anon/authenticated keys.
ALTER TABLE public.channel_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.channel_link_codes ENABLE ROW LEVEL SECURITY;

COMMIT;
