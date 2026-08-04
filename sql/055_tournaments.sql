-- Rematch Tournament Mode v0
-- Run in Supabase SQL editor when ready (gaming schema).
-- Until applied, the bot uses data/tournaments.json local store.

-- tournaments
create table if not exists gaming.tournaments (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  host_profile_id uuid,
  title text not null default 'Rematch Cup',
  game_id text not null,
  preset int not null check (preset in (4, 8, 16)),
  entry_usdc numeric(12,2) not null default 0,
  fee_bps int not null default 1000, -- 10%
  payout_card jsonb not null default '{"1":0.65,"2":0.20,"3":0.15}'::jsonb,
  status text not null default 'open'
    check (status in ('draft','open','locked','live','final','cancelled')),
  visibility text not null default 'public'
    check (visibility in ('public','private')),
  chain_id text not null default 'arc',
  money_live boolean not null default false,
  pot_usdc numeric(12,2) not null default 0,
  bracket jsonb not null default '[]'::jsonb,
  payouts jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create index if not exists idx_tournaments_status on gaming.tournaments (status);
create index if not exists idx_tournaments_code on gaming.tournaments (code);

-- entries (one seat per profile)
create table if not exists gaming.tournament_entries (
  id uuid primary key default gen_random_uuid(),
  tournament_id uuid not null references gaming.tournaments(id) on delete cascade,
  profile_id uuid not null,
  seat_status text not null default 'joined'
    check (seat_status in ('joined','locked','refunded','eliminated','winner','active')),
  entry_tx_hash text,
  amount_usdc numeric(12,2) not null default 0,
  created_at timestamptz not null default now(),
  unique (tournament_id, profile_id)
);

create index if not exists idx_tournament_entries_tid on gaming.tournament_entries (tournament_id);
create index if not exists idx_tournament_entries_profile on gaming.tournament_entries (profile_id);

-- optional: progression matches linked to challenges later
create table if not exists gaming.tournament_matches (
  id uuid primary key default gen_random_uuid(),
  tournament_id uuid not null references gaming.tournaments(id) on delete cascade,
  match_key text not null,
  round int not null,
  player_a uuid,
  player_b uuid,
  winner_id uuid,
  challenge_id uuid,
  status text not null default 'pending'
    check (status in ('pending','ready','done','bye','forfeit')),
  unique (tournament_id, match_key)
);

comment on table gaming.tournaments is 'Rematch cup pots — Model A entry pool; see docs/TOURNAMENT_MODE.md';
