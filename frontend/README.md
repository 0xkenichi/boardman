# Rematch web surfaces

These Next.js App Router pages are the **source of truth** for public Rematch UI.

| Path | Purpose |
|------|---------|
| `app/rematch/page.tsx` | Product docs / how to play |
| `app/rematch/leaderboard/page.tsx` | Leaderboard + open challenges |
| `app/rematch/get-usdc/page.tsx` | Faucet / fund helper |
| `app/clawstation/page.tsx` | Legacy URL → `/rematch` |
| `app/api/rematch/public/route.ts` | Public JSON for leaderboard (Next route) |
| `public/rematch-logo.*` | Brand assets |

## Hosting

Deploy this folder as (or into) a Next.js app, **or** mount these routes into a host app.

The sideQuest monorepo no longer ships the full Rematch product UI — `/rematch` there only redirects to the Telegram bot. Prefer hosting docs + leaderboard from **this** repo.

Leaderboard data can also be served from the FastAPI backend (`src/backend/api/rematch.py` + `services/rematch_public.py`) if you do not use the Next route.
