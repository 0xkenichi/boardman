# Rematch web (production)

**App:** `https://playingsidequest.fun/rematch/app`  
**Security model:** `docs/WEBAPP_UX_AND_SECURITY.md`

## What is production-ready

| Piece | Status |
|-------|--------|
| Mini-app UI (home, challenge, match, upload, wallet) | ✅ |
| BFF — no Stack key in browser | ✅ |
| HttpOnly HMAC session cookie | ✅ |
| Telegram Login Widget + WebApp initData verify | ✅ |
| Profile lookup by telegram_id | ✅ (`/api/rematch/web/profile`) |
| Live balance snapshot | ✅ (`/api/rematch/web/wallet`) |
| Create match by @tag | ✅ (`/api/stack/v1/matches/by-tag`) |
| Rate limits on BFF | ✅ |
| Security headers (CSP, HSTS) | ✅ |
| Demo login | Dev only (off in production) |

## Run locally

```bash
cd frontend
cp .env.example .env.local
# fill TELEGRAM + STACK if testing live; else demo works without Stack
npm install
npm run dev
```

http://localhost:3000/rematch/app

## Production checklist

1. **BotFather** `/setdomain` → `playingsidequest.fun` (and `www` if used)  
2. Env on host:

```bash
NODE_ENV=production
REMATCH_SESSION_SECRET=<32+ random bytes>
TELEGRAM_BOT_TOKEN_CLAWSTATION=<bot token>
NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=ClawStationOfficialBot
NEXT_PUBLIC_TELEGRAM_BOT_URL=https://t.me/ClawStationOfficialBot
STACK_API_URL=https://<your-gaming-api-host>
STACK_API_KEY=<same key as API STACK_API_KEY>
```

3. Gaming API must expose:
   - `/api/rematch/web/profile`
   - `/api/rematch/web/wallet`
   - `/api/stack/v1/*`
   - Set `STACK_API_KEY` on the API

4. Users must **`/start` the bot once** (creates wallet + profile) before web login succeeds in production.

5. Deploy this Next app on the same domain as marketing pages (or reverse-proxy `/rematch` + `/api/rematch`).

## Routes

| Path | Purpose |
|------|---------|
| `/rematch/app` | Home + Telegram sign-in |
| `/rematch/app/challenge` | Wizard |
| `/rematch/app/match` | Codes / list |
| `/rematch/app/match/[code]` | Accept · lock |
| `/rematch/app/match/[code]/upload` | Proof photo |
| `/rematch/app/wallet` | Balance $ · fund address |

## Architecture

```
Browser  →  /api/rematch/app/* (BFF, session cookie)
                →  STACK_API_URL + X-Stack-Key
                     →  /api/rematch/web/*  (profile, wallet)
                     →  /api/stack/v1/*     (matches)
```
