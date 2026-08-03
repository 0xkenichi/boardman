# Rematch web

Public pages + **mini-app** for `playingsidequest.fun/rematch/...`

## Routes

| Path | Purpose |
|------|---------|
| `/rematch` | Marketing / how to play |
| `/rematch/leaderboard` | Public board |
| `/rematch/get-usdc` | Fund helper |
| **`/rematch/app`** | **Mini-app home** (balance, challenge) |
| `/rematch/app/challenge` | New challenge wizard |
| `/rematch/app/match` | Open match by code / list |
| `/rematch/app/match/[code]` | Accept · lock · status |
| `/rematch/app/match/[code]/upload` | Final screenshot proof |
| `/rematch/app/wallet` | Balance $ · fund address |

## BFF (browser never sees Stack key)

| API | Role |
|-----|------|
| `POST /api/rematch/app/session` | Telegram / demo login → HttpOnly cookie |
| `GET /api/rematch/app/me` | Balance snapshot |
| `GET /api/rematch/app/games` | Catalog |
| `POST /api/rematch/app/matches` | Create challenge |
| `GET/POST /api/rematch/app/matches/[code]` | Status / accept / lock |
| `POST /api/rematch/app/matches/[code]/proof` | Upload proof |

Security model: `docs/WEBAPP_UX_AND_SECURITY.md`

## Run locally

```bash
cd frontend
cp .env.example .env.local
# REMATCH_ALLOW_DEMO_LOGIN=1 is fine for local
npm install
npm run dev
```

Open http://localhost:3000/rematch/app → **Continue (demo login)**.

### Live Stack

```bash
# .env.local
STACK_API_URL=http://127.0.0.1:8000
STACK_API_KEY=your-key
TELEGRAM_BOT_TOKEN_CLAWSTATION=...
REMATCH_SESSION_SECRET=...
```

## Production

- Host Next on the same domain as `playingsidequest.fun`
- Set strong `REMATCH_SESSION_SECRET`
- Disable demo login (`REMATCH_ALLOW_DEMO_LOGIN` unset, `NODE_ENV=production`)
- Telegram Login Widget + bot token for real auth
- HTTPS only
