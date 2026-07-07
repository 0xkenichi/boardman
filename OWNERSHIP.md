# ClawStation Package Ownership & Boundaries

This document defines the package boundary between `gaming/` (ClawStation) and
`app/` (social sideQuest).  It is the source of truth for which code owns which
database object.

## Two-package rule

- `gaming/` owns everything in the `gaming.*` Postgres schema and all columns on
  `public.profiles` whose names begin with `gaming_`.
- `app/` owns everything else in `public.*` (profiles core columns, bets, quests,
  friend circles, etc.).
- There are **zero cross-package direct table writes**:
  - `gaming/` code MUST write to `gaming.*` tables and to its own
    `public.profiles.gaming_*` columns only.
  - `app/` code MUST NOT write to `gaming.*` tables or `gaming_*` profile
    columns.
- When one package needs data owned by the other, it reads through the public
  API / RPC / view contract:
  - `app/` may read `gaming.*` through the public views (`public.challenges`,
    `public.sessions`, `public.base_markets`, `public.proof_of_play_receipts`).
  - `gaming/` may read shared `public.*` tables (e.g. `public.profiles`,
    `public.bets`) but only writes to its own columns on profiles.

## Schema partitioning

| Schema | Owner | Contents |
|--------|-------|----------|
| `public` | `app/` + shared | Core user tables (`profiles`, `bets`, ...), public views that alias `gaming.*` tables for backward compatibility. |
| `gaming` | `gaming/` | All ClawStation tables: `challenges`, `sessions`, `base_markets`, `proof_of_play_receipts`, `wallet_credit_audit`, `notification_failures`. |

The `gaming` schema is the physical home for ClawStation data.  The public views
are a compatibility shim and must not acquire business logic; they are plain
`SELECT * FROM gaming.<table>`.

## Column ownership matrix on `public.profiles`

| Column | Owner | Writable by | Notes |
|--------|-------|-------------|-------|
| `id` | shared | neither directly | Managed by Supabase auth / triggers. |
| `display_name` | `app/` | `app/` | Source for the auto-generated `gaming_tag` backfill. |
| `gaming_tag` | `gaming/` | `gaming/` only | Unique public handle inside ClawStation. Partial unique index (`WHERE gaming_tag IS NOT NULL`). |
| `gaming_telegram_chat_id` | `gaming/` | `gaming/` only | Telegram chat id for the ClawStation bot. |
| `gaming_deposit_address` | `gaming/` | `gaming/` only | Circle Developer-Controlled wallet deposit address. |
| `gaming_reputation_score` | `gaming/` | `gaming/` only | Default 1000. Used for matchmaking and tier calculation. |
| `gaming_tier` | `gaming/` | `gaming/` only | Default `bronze`, CHECK constraint allows bronze/silver/gold/platinum/diamond. |
| All other columns | `app/` | per existing rules | `app/` MUST NOT touch any `gaming_*` column. |

## Enforcement

- Code review: every PR that touches `gaming_*` columns or `gaming.*` tables must
  be reviewed against this matrix.
- Lint/CI: a future CI step should grep for cross-package table writes (e.g.
  `gaming/` code touching non-gaming columns, `app/` code touching `gaming.*`).
- Migration policy: new `gaming_*` columns or `gaming.*` tables require approval
  from the ClawStation owner and must be accompanied by an update to this file.
