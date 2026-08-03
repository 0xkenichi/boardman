# Rematch Web App — how it works, parity with Telegram, security, simple UX

**Host:** `https://playingsidequest.fun/rematch/...`  
**Backend:** Rematch Stack API (same rails as Telegram)  
**Audience:** non-crypto users first · money abstracted as **Balance $**

---

## 1. One product, two doors

| Door | Who | Same under the hood? |
|------|-----|----------------------|
| **Telegram bot** | Fast, chat-native | Yes — profiles, wallets, matches, escrow, PLAY |
| **Web app** | Browser / MiniPay / link from chat | **Yes — same Stack + same DB + same USDC escrow** |

Users do **not** get a second wallet or a second balance unless they use a different Telegram account.  
**Login with Telegram** ⇒ same profile as the bot.

```
playingsidequest.fun/rematch/app     → full mini-app (play)
playingsidequest.fun/rematch         → marketing / how-to (today)
playingsidequest.fun/rematch/leaderboard
playingsidequest.fun/rematch/get-usdc
playingsidequest.fun/rematch/wallet  → deep link into app wallet
playingsidequest.fun/rematch/match/CODE
```

Telegram **WebApp** button can open the same `/rematch/app` so bot + web feel like one product.

---

## 2. Will the webapp have “everything” from Telegram?

### Yes (same capabilities)

| Feature | Telegram | Web |
|---------|----------|-----|
| Wallet / balance / fund address | ✅ | ✅ |
| Challenge (iMessage / Mobile / Console catalog) | ✅ | ✅ |
| Accept / lock stake | ✅ | ✅ |
| My match status | ✅ | ✅ |
| Submit result (screenshot + score) | ✅ | ✅ |
| Rematch, profile, PLAY, board | ✅ | ✅ |
| Zingers on settle | ✅ (DM) | ✅ (in-app + optional Telegram ping) |
| Public challenges | ✅ | ✅ |

### Better on web

- Bigger upload UI for screenshots  
- Clear multi-step wizards  
- Shareable links: `.../rematch/match/AB12`  
- Works for people who hate bots  

### Better on Telegram

- Instant push when challenged  
- No “open browser” friction  
- Group / channel discovery later  

### Not “crypto dashboard”

Web must **not** dump seed phrases, chain switchers, or gas tokens. Same abstraction as the bot.

---

## 3. How the webapp works (user journey)

### Non-crypto mental model

> Add money → challenge a friend → lock → play (phone/console/iMessage) → send photo of the end screen → winner gets paid.

No “sign transaction”, no MetaMask for MVP if we keep **Circle custodial** wallets (same as Telegram).

### Step-by-step

1. **Open** `playingsidequest.fun/rematch/app`  
2. **Continue with Telegram** (Login Widget or WebApp `initData`)  
3. **Home:** big **Balance $X**, buttons: Challenge · My match · Get money · Board  
4. **Get money:** show **one** deposit address + “copy” + link to faucet/helper (testnet)  
5. **Challenge:** Who? (tag) → How much? → Where? (iMessage / Mobile / Console) → Which game? → Confirm  
6. **Friend** gets Telegram notify (and/or opens link) → Accept → both Lock  
7. **Play** outside Rematch  
8. **Submit result:** upload photo + score / W-L  
9. **Done:** zinger + updated Balance $  

Same state machine as Telegram:

`open → accepted → lock → play → proof → settle`

---

## 4. Security — how we avoid “users getting hacked”

We design for **custodial USDC under Circle + server authority**, not “paste your private key on a website.”

### 4.1 What users never see

- Private keys / seed phrases  
- Entity secrets / Circle API keys  
- `STACK_API_KEY` (server-only)  

### 4.2 Auth (must be solid)

| Layer | Rule |
|-------|------|
| **Telegram Login Widget** | Verify `hash` with bot token (HMAC) server-side; never trust client-only claims |
| **Telegram WebApp** | Verify `initData` signature server-side on every session mint |
| **Session** | HttpOnly, Secure, SameSite cookies (or short-lived JWT in memory + refresh) |
| **No Stack key in browser** | Browser talks to **our Next.js BFF** (`/rematch/api/...`); BFF holds `STACK_API_KEY` or calls services directly |

```
Browser  →  playingsidequest.fun/rematch/api/*  (your backend, session auth)
                ↓
         Stack / gaming services  (server secrets)
```

**Never** embed `STACK_API_KEY` in frontend JS.

### 4.3 Money safety (same as bot)

| Control | Purpose |
|---------|---------|
| Dual-lock escrow | Neither side can run off mid-match after both lock |
| Stake / withdraw caps | `CLAW_MAX_STAKE_USDC`, daily withdraw caps |
| Pause switch | `CLAW_PAUSED` + admin `/pause` |
| Geo-fence | Blocked regions on API |
| Idempotent locks | No double-lock bugs |
| Rate limits | Challenges, withdraws, uploads |
| Proof + dispute | AI + dual report + admin path |

### 4.4 Web-specific hardening

| Control | Purpose |
|---------|---------|
| HTTPS only | playingsidequest.fun |
| CSRF on cookie sessions | State-changing POSTs |
| Content-Security-Policy | Reduce XSS → session theft |
| Upload limits | Max image size, type sniff, virus-size cap |
| Signed upload URLs or direct-to-API with session | No public open upload bucket |
| Withdraw confirm | PIN / Telegram confirmation for large withdraws (recommended) |
| Device session list | “Log out all” later |

### 4.5 What “hacked” usually means — and our answer

| Attack | Mitigation |
|--------|------------|
| Phishing fake site | Official domain only; Telegram deep links; never ask for seeds |
| Stolen session cookie | HttpOnly + short TTL + refresh rotation |
| XSS steals tokens | CSP, no `dangerouslySetInnerHTML` of user content |
| API key leak | Key only on server; rotate if exposed |
| Someone challenges as you | Auth bound to Telegram user id |
| Fake screenshot | Same as bot: dual report, AI confidence, dispute |
| Address swap scams | Show **one** play address; warn if funds on linked/old address (already fixed in bot) |

### 4.6 Honest limits

- **Custodial** = we (via Circle) hold keys → we must protect server + Circle credentials like production money.  
- **Testnet** first reduces real-money loss while UX is proven.  
- No system is “unhackable”; we aim for **no user-held keys on web**, **no secret in browser**, **caps + pause + audit trails**.

---

## 5. Simple UX principles (non-crypto)

| Do | Don’t |
|----|--------|
| Say **Balance $12** | Say “USDC on Arc Testnet gas-native” |
| Say **Get money** | Say “Bridge CCTP to Arc” |
| Say **Challenge friend** | Say “Create escrow dual-lock” |
| One primary button per screen | 12 chain/network toggles |
| Big photo upload | “Submit oracle payload” |
| Errors in plain language | Raw RPC / Circle JSON |

### Screen copy examples

**Home**  
`Balance $12.50`  
`[Challenge]` `[My match]` `[Get money]`

**Wallet**  
`Your fund address` (copy)  
`This is what you can stake.`  
If linked address has $: warn to move funds (same as bot fix).

**Challenge**  
Same steps as Telegram wizard — category → game → stake → friend.

**Result**  
`Send the final screen` + caption `2-1` or `W`/`L`.

---

## 6. Architecture (secure)

```
                    ┌──────────────────────────┐
  User browser      │  playingsidequest.fun      │
  Telegram WebApp   │  /rematch/app/*            │
                    └────────────┬─────────────┘
                                 │ session cookie
                    ┌────────────▼─────────────┐
                    │  BFF (Next.js route       │
                    │  handlers / FastAPI)      │
                    │  - verify Telegram auth   │
                    │  - rate limit             │
                    │  - never expose STACK key │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         Stack/services    Circle W3S          Supabase
         matches/escrow    custodial USDC      profiles
```

**Telegram bot** keeps using Python handlers directly (same services).  
**Web** uses BFF so the browser is never a trusted party for secrets.

---

## 7. Parity checklist

### Production-ready (code in `frontend/` + gaming API)

- [x] Routes under `/rematch/app` (home, challenge, match, upload, wallet)  
- [x] BFF under `/api/rematch/app/*` (session cookie, no Stack key in browser)  
- [x] Demo login for local only (disabled in production)  
- [x] Telegram Login Widget UI + HMAC verify  
- [x] Telegram WebApp `initData` auto-login when inside Telegram  
- [x] Profile lookup `GET /api/rematch/web/profile?telegram_id=`  
- [x] Live wallet `GET /api/rematch/web/wallet?profile_id=`  
- [x] Create match by tag `POST /api/stack/v1/matches/by-tag`  
- [x] Rate limits on BFF  
- [x] CSP / HSTS / security headers middleware  

### Optional next

- [ ] Withdraw flow + extra confirm  
- [ ] Bot button `web_app` → `/rematch/app`  
- [ ] Redis rate limits for multi-instance  
- [ ] Fiat top-up UI (`PAYMENT_RAILS.md`)

---

## 8. MiniPay (later)

Same webapp URL (or `/rematch/app?host=minipay`).  
MiniPay is a **host**, not a second product.  
Security still: no seeds, session + server BFF.  
Celo USDC optional; default stays abstracted Balance $.

---

## 9. Decision log

| Decision | Choice |
|----------|--------|
| URL base | `playingsidequest.fun/rematch/...` |
| Feature parity | Same Stack rails as Telegram |
| Auth | Telegram-verified session (not Stack key in browser) |
| Wallets | Circle custodial — user never holds keys on web MVP |
| UX | Cash-like language only |
| API name | Rematch Stack under the hood; product says “Rematch” |

---

## 10. Bottom line

**Webapp = Telegram features in a simple browser UI, on the same secure Stack, without teaching crypto.**  
Users log in with Telegram, see **Balance $**, challenge, play off-app, upload the final photo, get paid.  
Security = **server-side auth, no secrets in the browser, custodial Circle, escrow caps, and the same proof rules as the bot.**
