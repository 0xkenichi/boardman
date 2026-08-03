# URLs + console errors (what matters)

## Should it be `playingsidequest.fun` or `/rematch`?

**Use the `/rematch` path for everything Rematch.**

| URL | Role |
|-----|------|
| `https://playingsidequest.fun` | sideQuest parent brand / other products |
| **`https://playingsidequest.fun/rematch`** | Rematch marketing / how-to |
| **`https://playingsidequest.fun/rematch/app`** | **Play mini-app** (login, challenge, match, upload) |
| `.../rematch/leaderboard` | Public board |
| `.../rematch/get-usdc` | Fund helper |
| `.../rematch/match/CODE` | Deep link into a match (via `/rematch/app/match/CODE`) |

**Do not put the mini-app at the site root** (`playingsidequest.fun/` alone) — that belongs to the broader sideQuest site. Rematch is namespaced under **`/rematch`**.

BotFather `/setdomain` should be: **`playingsidequest.fun`** (domain of the site; path is free).

---

## Console errors you pasted

### 1. `Cannot redefine property: ethereum` · `inpage.js` · `IN_PAGE_CHANNEL_NODE_ID`

**Not Rematch.** These come from **wallet browser extensions** (MetaMask, Binance Wallet, Phantom, Cosmos, Tron, etc.) injecting scripts into every page.

- Safe to ignore for Rematch  
- Confirm: open the same page in a **private window with extensions disabled** — those errors disappear  
- Rematch webapp does **not** use `window.ethereum` for login (Telegram + custodial Circle)

### 2. `Failed to load resource: 404` for `app`

Production is likely still serving the **old** monorepo page at `/rematch` only.  
The mini-app lives at **`/rematch/app`**, which must be deployed from this repo’s `frontend/` folder.

Until deploy is updated:

- `playingsidequest.fun/rematch` → marketing (or broken monorepo shell)  
- `playingsidequest.fun/rematch/app` → **404** if not deployed  

**Fix:** deploy the Next app from `frontend/` so `/rematch/app` exists on the same host.

### 3. React error `#310` + “Application error: a client-side exception”

React #310 = **hooks order / conditional hooks** (or a crash during render).  
We hardened the mini-app (stable Telegram widget, error boundaries, safer challenge page).

If you still see it **only** on production `/rematch` (not local `/rematch/app`):

- That page may still be **old host code**, not this scaffold  
- Redeploy this `frontend/` build  

---

## Quick checks

```bash
# Local (this repo)
cd frontend && npm run dev
open http://localhost:3000/rematch
open http://localhost:3000/rematch/app
```

Production after deploy:

```text
https://playingsidequest.fun/rematch        → marketing OK
https://playingsidequest.fun/rematch/app    → mini-app sign-in (not 404)
```
