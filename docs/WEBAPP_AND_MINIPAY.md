# Rematch Web App & MiniPay

**Status:** plan + existing thin web · Stack API ready for a full app  
**Related:** `docs/WEBAPP_UX_AND_SECURITY.md` (how it works · parity · security · simple UX), `frontend/`, `docs/MOBILE_GAMES.md`, `src/stack/README.md`

**Base URL:** `https://playingsidequest.fun/rematch/...`

---

## Short answers

| Question | Answer |
|----------|--------|
| Can we create a **Rematch webapp**? | **Yes.** Grow `frontend/` into `/rematch/app` on **Rematch Stack** (same rails as Telegram). |
| Same features as Telegram? | **Yes** — challenge, lock, wallet, proof, board. Auth = Telegram so **same account/balance**. |
| Secure? | **Custodial Circle + server BFF** — no seeds in browser, no `STACK_API_KEY` in JS, caps/pause/geo. Details: `WEBAPP_UX_AND_SECURITY.md`. |
| Non-crypto UX? | **Balance $**, Get money, Challenge friend, send final photo — no chain education. |
| MiniPay? | **Yes, later** — same webapp inside MiniPay; Celo optional. |
| API name | Product: Rematch · Platform: **Rematch Stack** |

---

## What you already have (web)

| Path | Today |
|------|--------|
| `/rematch` | Product / how to play |
| `/rematch/leaderboard` | Public board |
| `/rematch/get-usdc` | Fund helper |
| `GET /api/rematch/public` | JSON for leaderboard |

This is a **docs + leaderboard** surface, not full challenge/lock/proof yet.

---

## Target: Rematch Web Mini-App

Phone browser + Telegram WebApp button + desktop.

```
┌─────────────────────────────────────┐
│  Rematch Web (Next.js)                │
│  Login (Telegram Login Widget / OTP) │
│  Wallet · Challenge · Match · Proof   │
└──────────────────┬────────────────────┘
                   │ STACK_API_KEY or user JWT
┌──────────────────▼────────────────────┐
│  Stack API v1                           │
│  /games · /matches · lock · proof       │
└──────────────────┬────────────────────┘
                   │
         Circle / ClawEscrow / Arc
```

### Screens (MVP)

1. **Home** — balance, active match, Challenge  
2. **New challenge** — category (iMessage / Mobile / Console) → game → stake → opponent tag  
3. **My match** — lock, status, upload screenshot  
4. **Wallet** — fund address, refresh (abstract $)  
5. **Board** — public challenges + leaderboard (exists)

### Auth options

| Method | Fit |
|--------|-----|
| Telegram Login Widget | Best first — same profiles as bot |
| Stack key (server-only) | Partner backends, not end users |
| Magic / OTP email | Later |
| MiniPay provider | When shipping MiniPay shell |

### Telegram WebApp

Bot button `web_app` → open `https://playingsidequest.fun/rematch/app`  
Same session as Telegram user via `initData` verification.

---

## MiniPay (Celo) path

[MiniPay](https://docs.celo.org/developer/build-on-minipay) is Opera Mini’s wallet mini-app host (Africa-heavy).

| Step | Work |
|------|------|
| 1 | Ship **webapp** that works in mobile Safari/Chrome first |
| 2 | Detect MiniPay provider (`window.ethereum` / MiniPay docs) |
| 3 | Optional: settle or display on **Celo USDC** as another chain in `chains.yaml` when ready |
| 4 | Submit MiniPay mini-app listing |

**Important:** Arc is still your primary settlement story today. MiniPay does **not** require abandoning Arc — you can:

- **A)** MiniPay as **UX shell only** (users still fund Arc via your flow), or  
- **B)** Add **Celo** as a chain later and abstract multi-chain under one Balance $  

Start with **A** so you don’t block on Celo grants/gas.

---

## Recommended build order

| Phase | Deliverable |
|-------|-------------|
| **M0** | Mobile catalog expanded (Free Fire, COD, Valorant, PUBG, …) — **now** |
| **M1** | Web app MVP: challenge + match status + screenshot upload via Stack v1 |
| **M2** | Telegram WebApp button → same web app |
| **M3** | MiniPay packaging + optional Celo rail |

---

## Why this fits Rematch

- Mobile games are **catalog + screenshot** (no publisher API).  
- Webapp is just another **client** on Stack (like Telegram).  
- MiniPay is another **host** for the same webapp in Africa’s super-app wallet pattern.

---

## Decision log

| Decision | Choice |
|----------|--------|
| Expand mobile titles | Free Fire, COD, Valorant, PUBG + sports + casual 1v1 |
| BR modes | Disabled in catalog |
| Webapp | Yes — extend `frontend/` on Stack v1 |
| MiniPay | Yes after web MVP; shell-first, Celo optional |
| Money abstraction | Users still see Balance $, not chain education |
