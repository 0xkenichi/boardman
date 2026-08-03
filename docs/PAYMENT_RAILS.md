# Rematch Payment Rails — Fiat → Play balance (mainnet prep)

**Status:** design for mainnet · testnet stays Circle/USDC address top-up for now  
**Goal:** User sends **fiat** (e.g. Naira) → we convert → **USD/USDC play balance** almost instantly  
**Constraint:** Little or no capital; prefer **low/no KYC** until volume forces full registration  
**Related:** `PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`, `WEBAPP_UX_AND_SECURITY.md`, custodial Circle wallets

---

## 1. User experience (non-crypto)

```
User: “I want to play with ₦x / $y”
  → Rematch shows: pay this amount / reference
  → User pays in fiat (bank / USSD / card / mobile money)
  → We detect payment → convert → credit play wallet (USDC)
  → User sees: Balance $12.50
  → They stake as today
```

**They never need to:**

- Buy crypto on an exchange  
- Understand Arc / gas  
- Bridge tokens  

**Crypto users can still:** send USDC directly to their deposit address (keep forever).

---

## 2. Architecture

```
┌─────────────┐     fiat      ┌──────────────────┐
│ User bank /  │ ───────────► │ Payment rail      │
│ card / MM    │              │ (one account or   │
└─────────────┘              │  virtual accounts) │
                              └─────────┬────────┘
                                        │ webhook / poll
                              ┌─────────▼────────┐
                              │ Rematch backend   │
                              │ map payment →     │
                              │ profile_id        │
                              └─────────┬────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
             Credit ledger        Fund Circle          Platform fee
             (optional)           play wallet USDC     cut
                    │                   │
                    └─────────► Balance $ (stakeable)
```

**Two balances to be careful about (we already learned this):**

| Balance | Use |
|---------|-----|
| **Play wallet on-chain USDC** | What dual-lock escrow spends |
| **Internal ledger** | Only OK if we **also** fund the play wallet or lock from ledger (prefer fund play wallet) |

**Target:** fiat payment → **USDC lands in user’s Circle play address** (or hot wallet transfer in), so stake path is unchanged.

---

## 3. Payment stack options (practical, low capital)

### Tier A — Start this week (almost free)

| Option | How | KYC | Notes |
|--------|-----|-----|--------|
| **Single business/personal bank or fintech account + payment reference** | User pays exact amount + unique ref (e.g. `RM-AB12CD`) | Your account KYC only | Manual or webhook recon; best MVP |
| **Kuda / Opay / PalmPay / Moniepoint business** | Same idea | Business easier long-term | One account, map refs |
| **Crypto P2P desk (ops)** | User pays fiat to your number; you send USDC on Arc | Trust/ops heavy | Only small testnet-adjacent pilots |

**MVP flow:**

1. Bot/web: “Top up $10” → generate `ref = RM-{code}` + amount in ₦  
2. User transfers to **your** account with that ref  
3. Webhook or admin confirms → system sends USDC to their **play address** (Circle transfer or platform gas tank + transfer)  
4. Notify: “Balance updated”  

**Limits:** e.g. $5–$100 per top-up, daily cap — enough to play, low fraud surface.

### Tier B — Simple APIs (when you can pay fees)

| Provider (examples) | Fit | Registration |
|---------------------|-----|--------------|
| **Paystack** | Card / bank (NG) | Business + bank |
| **Flutterwave** | Card / bank / mobile money (multi-Africa) | Business |
| **Korapay** | Collections | Business |
| **Fincra** | Collections + crypto off/on in some products | Business |

These give **virtual accounts** or payment links → webhook `charge.success` → auto credit.

**Still need:** entity that can hold fiat (personal → business as you grow).

### Tier C — Crypto on-ramp widgets (less “send to bank”)

| Option | Fit |
|--------|-----|
| **Onramper / Transak / MoonPay** | Card → crypto to address (fees high; more KYC on user) |
| **Binance Pay / P2P API** | Ops-heavy |

Good later; not the “send Naira to our account” simplicity you want first.

---

## 4. Recommended path for Rematch (no money now)

### Phase F0 — Design + bookkeeping (now)

- [x] Strategy: abstract Balance $  
- [ ] Pick **one** collection account (prefer business fintech when possible)  
- [ ] Schema: `fiat_topups` table  
  - `id`, `profile_id`, `ref`, `amount_fiat`, `currency`, `amount_usdc`, `status`, `provider_tx`, `created_at`  
- [ ] Bot/web button: **Top up with bank** (testnet can mock “mark paid”)  
- [ ] Ops dashboard or admin command: `/credit_topup REF` until webhooks exist  

### Phase F1 — Manual recon MVP (mainnet pilot, tiny limits)

- User generates ref + ₦ amount  
- Pays your account  
- You (or script matching bank alerts) mark paid  
- System **transfers USDC** to their Circle play wallet on Arc  
- Fee: e.g. 1–3% or flat ₦ fee  
- Caps: **$100 / top-up**, **$200 / day / user** until registered properly  

### Phase F2 — Provider webhook

- Paystack/Flutterwave (or similar) payment link or virtual account per user/ref  
- Webhook verifies signature  
- Auto convert at FX rate (Oracle: manual rate table or API)  
- Auto USDC transfer to play wallet  

### Phase F3 — Full compliance

- CAC / business account  
- Higher limits  
- Formal ToS + refund policy  
- Possibly licensed partner for fiat custody  

---

## 5. Conversion & fee model

| Item | Approach |
|------|----------|
| FX | Published rate in app (₦ per $1) updated daily/hourly |
| Fee | Transparent: “You pay ₦X → get $Y play balance” |
| Platform cut | Fee % of fiat or spread on FX |
| Float | You need **some** USDC on Arc to pay users — start small (treasury wallet) |
| Failure | If USDC send fails: keep topup `pending_payout`, retry, support |

**Treasury:** a hot **gas + USDC** wallet you control funds users from. Fiat sits in bank; USDC inventory is separate (rebalance manually at first).

---

## 6. One rail vs many

| Design | Pros | Cons |
|--------|------|------|
| **One shared account + unique ref** | Zero provider cost, simple | Manual recon risk; collisions if ref ignored |
| **Virtual account per user** | Clean matching | Provider fees + registration |
| **Payment link per top-up** | Easy UX | Same |

**Start:** one account + **unique ref + exact amount**.  
**Scale:** virtual accounts or payment links.

---

## 7. Security & fraud

| Risk | Mitigation |
|------|------------|
| Fake “I paid” | Never credit without bank/provider confirmation |
| Wrong ref | Hold in suspense; support match by amount+time |
| Chargeback (cards) | Delay large withdraws; prefer bank transfer first |
| Money mule | Low caps; velocity limits; pause switch |
| Ops theft | Dual control on treasury; audit log every credit |

---

## 8. Testnet vs mainnet

| Network | Funding |
|---------|---------|
| **Testnet (now)** | Circle faucet / send test USDC to play address — **keep** |
| **Mainnet (soon)** | Direct USDC to address **or** fiat payment rail |

Do not mix testnet faucet language with real fiat. Separate `NETWORK=testnet|mainnet` UX.

---

## 9. What to say publicly

> Crypto users: fund your Rematch address with USDC.  
> Everyone else (mainnet): **Top up with bank** — send fiat, we handle conversion, your Balance $ updates.  
> Same stakes. Same matches. No exchange homework.

---

## 10. Immediate actions (no big capital)

1. Open/document **one** collection account + naming convention for refs  
2. Add `fiat_topups` table + bot “Top up” stub (even if admin-credits at first)  
3. Maintain **small USDC treasury** on Arc for credits when you go mainnet  
4. Shortlist **one** NG collection API (Paystack/Flutterwave) for when CAC/business is ready  
5. Keep **direct USDC deposit** forever for crypto-native users  

---

## Decision log

| Decision | Choice |
|----------|--------|
| User sees | Balance $ only |
| Crypto path | Keep deposit address |
| Fiat path | Bank/fintech → convert → USDC to play wallet |
| MVP provider | Single account + payment ref (then Paystack-class) |
| Limits until registered | ~$100 / top-up style caps |
| Escrow | Unchanged dual-lock on USDC |

**Payment rail = the missing door for non-crypto. Stack + catalog = the product. Together they are Rematch V2 money readiness.**
