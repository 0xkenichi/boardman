# Rematch × MiniPay — Proof of Ship (Celo Research Tech Build)

**Status:** MiniPay shell live on Rematch web  
**Program:** [Build With Celo: Proof-of-Ship](https://www.celopg.eco/programs/proof-of-ship-s1)  
**Docs:** [Build on MiniPay](https://docs.celo.org/developer/build-on-minipay)

---

## What we shipped

Rematch is a **1v1 skill-match product** (dual-lock USDC, screenshot settle) that already runs on Telegram + web. For Celo / MiniPay we ship the **same mini-app inside MiniPay** as a host — Africa distribution without forking the product.

| Surface | URL |
|---------|-----|
| **MiniPay entry** | https://playingsidequest.fun/rematch/app?host=minipay |
| **MiniPay landing** | https://playingsidequest.fun/rematch/minipay |
| **Local** | http://localhost:3000/rematch/app?host=minipay |
| Telegram (same accounts) | https://t.me/ClawStationOfficialBot |

---

## Technical checklist (PoS)

| # | Requirement | Rematch |
|---|-------------|---------|
| 1 | HTTPS mini-app URL | ✅ Vercel `playingsidequest.fun` |
| 2 | Opens in MiniPay browser | ✅ `?host=minipay` + `window.ethereum.isMiniPay` |
| 3 | Provider detect | ✅ `lib/minipay.ts` → `isMiniPay` |
| 4 | Connect accounts | ✅ `eth_requestAccounts` when in MiniPay |
| 5 | Show chain / address | ✅ MiniPayHost card (Celo chain id) |
| 6 | Useful product (not hello world) | ✅ Challenge, wallet, match, proof, live rooms |
| 7 | Stablecoin UX | ✅ Balance $ abstract; Celo USDC rail next |
| 8 | Mobile-first | ✅ PWA + phone layout |

---

## Architecture (shell-first)

```
MiniPay (Celo wallet host)
   │  window.ethereum.isMiniPay
   ▼
Rematch Web Mini-App  (/rematch/app?host=minipay)
   │  BFF  REMATCH_API_KEY
   ▼
Rematch API  (Telegram bot same DB)
   │
   ▼
Circle custodial play wallet  (Arc today)
   + MiniPay address shown for host identity
```

**Phase A (now):** MiniPay = UX shell + wallet identity.  
**Phase B (next):** Optional Celo USDC settle in `chains.yaml` (`celo` already listed).

---

## Demo script for judges

1. Open MiniPay → paste  
   `https://playingsidequest.fun/rematch/app?host=minipay`
2. Banner: **Running in MiniPay · Celo** — Connect / refresh address  
3. Sign in (Telegram or demo) → see Balance $  
4. Challenge friend **or** Live rooms group for public games  
5. Match flow: lock → play → upload final screen  

---

## Code map

| File | Role |
|------|------|
| `frontend/lib/minipay.ts` | Detect + connect MiniPay |
| `frontend/components/rematch/MiniPayHost.tsx` | In-app Celo/MiniPay card |
| `frontend/app/rematch/minipay/page.tsx` | Listing / PoS landing |
| `config/chains.yaml` | `celo` + `celo_alfajores` entries |

---

## Submit notes

- **Project name:** Rematch by sideQuest  
- **One-liner:** 1v1 skill matches with dual-lock USDC, inside MiniPay for Africa.  
- **Repo:** rematch (this monorepo)  
- **Contact:** Telegram bot + playingsidequest.fun/rematch  

Register / update monthly ship logs on the Proof-of-Ship program page.

---

## Next (optional for higher scores)

1. Celo USDC balance read on MiniPay address  
2. Escrow contract on Celo (or Circle on Celo if available)  
3. MiniPay app discovery listing submission  
4. Phone-number social invite mapping (MiniPay strength)
