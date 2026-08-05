# Rematch Payment Rails — Fiat → Play balance (mainnet prep)

**Status:** design for mainnet · testnet stays Circle/USDC address top-up for now  
**Goal:** User sends **fiat** (e.g. Naira) → we convert → **USD/USDC play balance** almost instantly  
**Constraint:** Little or no capital; prefer **low/no KYC** until volume forces full registration  
**Related:** `PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`, `WEBAPP_UX_AND_SECURITY.md`, custodial Circle wallets

---

## 1. User experience (non-crypto)

### Preferred: partner app (Kobox)

```
User wants Naira ↔ USDC or bank cash-out
  → Rematch recommends Kobox (referral / download link)
  → User funds, swaps, withdraws inside Kobox
  → On-ramp: send USDC from Kobox → Rematch play address
  → Off-ramp: withdraw USDC from Rematch → Kobox address → Naira bank in app
```

**Why:** users get a full banking app; we avoid being the only FX desk; rates/liquidity live where they already convert.

### Fallback: Rematch bank desk

```
User: “I want to play with ₦x / $y” (and skips Kobox)
  → Rematch shows: pay this amount / reference to our account
  → User pays fiat → proof → we convert → credit play wallet (USDC)
  → Balance $ updates
```

**Crypto users can still:** send USDC directly to their play address (keep forever).

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
- [x] Collection accounts via env (`FIAT_NGN_*`, `FIAT_USD_*`)  
- [x] Local store: `data/fiat_topups.json` (DB table later)  
- [x] Bot: **Get money** → Naira / USD bank / crypto  
- [x] Admin: `/topups`, `/credit_topup RM-XXXX`, `/reject_topup RM-XXXX`  
- [x] Quote: commercial ₦ rate + fee = max($2 floor, 5% of gross)  

### Phase F1 — Manual recon MVP (mainnet pilot, tiny limits)

- User enters ₦ (or $) amount → bot quotes USDC credit after fee + unique `RM-` ref  
- Pays collection account (Naira 9PSB / USD Lead)  
- User pastes txn id or receipt photo  
- Ops sends USDC to play address → `/credit_topup REF`  
- Caps via env (`FIAT_MAX_*`, `FIAT_MAX_CREDIT_USDC`)  

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

### Locked commercial rates (2026-08)

| Direction | Rate | Meaning |
|-----------|------|---------|
| **On-ramp** (₦ → USDC) | **₦1,520 / $1** | `FIAT_NGN_PER_USD` — what users pay |
| **Off-ramp** (USDC → ₦) | **₦1,500 / $1** | `FIAT_NGN_OFFRAMP_PER_USD` — what we pay out |
| Your real convert | ~₦1,400 / $1 | Kobox / market (not shown to users) |
| Fixed fee | **max($2, 5%)** | Covers Kobox ~1.5 USDC send + ops |

**Why bid ≠ ask:** classic desk spread. User buys “expensive,” sells “cheaper.” Plus $2 floor so small top-ups don’t lose money on send fees.

**Example on-ramp (₦10,000 @ 1520):**  
gross $6.57 − $2 fee → **~$4.57 USDC** credited.

**Example off-ramp ($20 USDC @ 1500):**  
$20 − $2 fee = $18 → **₦27,000** to their bank.

| Item | Approach |
|------|----------|
| FX | Published rates above; update env when market moves hard |
| Fee | Transparent: “You pay ₦X → get $Y” / “Cash out $Y → get ₦Z” |
| Platform cut | FX spread (1520/1500) + floor fee |
| Float | USDC treasury for credits; Naira float for off-ramp payouts |
| Failure | Keep status `pending_payout`, retry, support |

**Treasury:** fiat in collection accounts; USDC inventory separate (rebalance via Kobox).

### Off-ramp (cash out) — product decision

| Path | Who | How |
|------|-----|-----|
| **Recommended** | Kobox (or any wallet) | Rematch **Withdraw → 0x** to their Kobox deposit address → swap/withdraw Naira in Kobox |
| **Already have off-ramp** | Binance / other | Same: withdraw to that 0x |
| **Desk (optional later)** | Rematch ops | Only if we want full bank payout ourselves — not required if Kobox is the rail |

Bot copy: **Cash out via Kobox** + **To 0x (Kobox or any wallet)**.

Env: `KOBOX_REFERRAL_URL`, `KOBOX_PARTNER_NAME`, `KOBOX_ENABLED`.

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

---

## 11. Settlement chains (fees + mainnet direction)

| Chain | Role now | Gas reality | Notes |
|-------|----------|-------------|--------|
| **Arc** | Live **testnet** settlement | USDC-native gas — best UX on testnet | Keep for testnet / Arc path |
| **Base** | Config ready (Sepolia legacy); **mainnet target** | L2 ETH gas — typically **cheapest** for USDC transfers | Prefer for real-money mainnet |
| **Avalanche** | Config ready (Fuji next); mainnet later | AVAX gas — cheap but often **> Base** for simple transfers | Optional second rail |

**Product decision (2026-08):**

1. **Testnet now:** stay on **Arc** (current live path).  
2. **Mainnet real stakes:** default settlement **Base** (low fees).  
3. **Avalanche / Arc mainnet:** enable when float + gas tank + escrow are ready — multi-rail, not either/or.  
4. Users still see **Balance $** — not chain jargon. Ops/backend picks settlement rail.

**Base vs Avalanche (practical):** Base L2 is usually cheaper per USDC transfer than Avalanche C-Chain; Avalanche is still fine if users already hold AVAX/USDC there. Prefer **Base first** for Nigeria mainnet pilots to minimize gas eating small stakes.
