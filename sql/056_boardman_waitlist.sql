-- Optional: Boardman waitlist (run in Supabase if you want durable storage)
create table if not exists public.boardman_waitlist (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  name text,
  telegram text,
  source text default 'web',
  created_at timestamptz not null default now()
);

create unique index if not exists boardman_waitlist_email_uidx
  on public.boardman_waitlist (lower(email));

-- Service role inserts from API; no public read
alter table public.boardman_waitlist enable row level security;
