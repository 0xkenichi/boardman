# What we need from you (multi-rail) + how to get it

This is the ops checklist for **Path A** (Stellar + Avalanche funding → Arc play balance).

---

## Already working (no action)

| Item | Status |
|------|--------|
| Arc play wallets + BoardmanEscrow | Live (testnet) |
| Abstract play balance + stake gate | Live |
| Get money: Naira / Paystack / Kobox / crypto | Live |
| Avalanche funding instructions | Live (uses Boardman ops `0xFA93…`) |
| Stellar Horizon watcher code | Live (needs your Stellar address) |
| `/rails_status` admin command | Live |
| `/topups` shows `rail_paid` | Live |

---

## What we need from you

### 1) Stellar ops receive account (required for “Fund with USDC (link)”)

**What:** A Stellar **public key** (starts with `G…`) that receives USDC.  
**Env:**

```bash
BOARDMAN_OPS_USDC_STELLAR=G...
STELLAR_NETWORK=testnet          # use public when you go live
BOARDMAN_STELLAR_MEMO_PREFIX=BM
STELLAR_WATCH_ENABLED=1
```

**How to get it (testnet — 10 minutes):**

1. Install [Freighter](https://www.freighter.app/) browser wallet **or** use [Laboratory](https://laboratory.stellar.org/).
2. Create an account on **Testnet**.
3. Copy the **public key** (`G…`).
4. Fund testnet account: [Friendbot](https://laboratory.stellar.org/#account-creator) (free XLM for fees).
5. Trust / receive **USDC** on testnet (issuer may differ; for public mainnet USDC issuer is Circle’s).
6. Paste public key into `.env` as `BOARDMAN_OPS_USDC_STELLAR=G...`
7. Restart the bot.
8. In Telegram: `/rails_status` → Stellar should say **Configured: yes**.

**How to get it (public / production):**

1. Freighter or hardware wallet → **Public network**.
2. Fund with a little **XLM** (for fees).
3. Add **USDC** trustline (Circle USDC on Stellar).
4. Never paste the **secret key** (`S…`) into chat, git, or Discord — only the **G…** public key goes in env for receive-only watching.  
   (If the bot must *send* later, use a separate signing setup / KMS — not for now.)

**Optional:** Create the keypair with:

```bash
# one-off offline (example with stellar-sdk in Python later)
# Or Laboratory → "Create Account" → save secret offline, put only G… in env
```

---

### 2) Avalanche ops address (optional — already defaults)

**What:** `0x` address that receives USDC on Avalanche (Fuji test / C-Chain main).  
**Default:** `BOARDMAN_OPS_USDC_ADDRESS` (same Boardman ops wallet).  
**Override if you split wallets:**

```bash
BOARDMAN_OPS_USDC_AVALANCHE=0xYourAvalancheReceiveAddress
```

**How to get Fuji USDC for testing:**

1. MetaMask → add Avalanche Fuji.  
2. Fuji faucet for AVAX (gas).  
3. Circle faucet / test USDC for Fuji if available.  
4. Send small USDC to ops `0x` with ref in notes when testing player flow.

---

### 3) USDC float on Arc (makes credits fast)

**What:** Keep ~$50–$200 USDC on Boardman ops Arc address so you can credit players without waiting for Kobox every time.

**How:**

1. Kobox / CEX → withdraw USDC to ops `0xFA93…` on **Arc** (when mainnet live).  
2. Testnet: Circle faucet / internal faucet to ops + players.  
3. After Paystack or Stellar `rail_paid`: send from float → player play address → `/credit_topup RM-XXXX`.

---

### 4) Admin Telegram IDs (for deposit alerts)

```bash
CLAW_ADMIN_TELEGRAM_IDS=your_telegram_numeric_id
```

**How to get your Telegram id:** message `@userinfobot` or check bot logs when you `/start`.

Without this, Stellar detection still marks top-ups `rail_paid` but you won’t get a DM.

---

### 5) Not needed yet (later upgrades)

| Item | When |
|------|------|
| Stellar **secret** key in bot | Only if bot auto-sends USDC (we don’t) |
| CCTP API keys / Circle bridge | Auto Avalanche → Arc |
| SEP-24 anchor partnership | In-app Naira↔USDC via Stellar anchor UI |
| Avalanche BoardmanEscrow deploy | If you want native Avax stakes (USDC gas first) |

---

## What the bot does after you add Stellar G…

1. Player: **Get money → Fund with USDC (link)** → gets address + **memo**.  
2. Player sends USDC with that memo.  
3. Horizon watcher (every ~90s) sees payment → status **`rail_paid`**.  
4. You + player get a Telegram ping.  
5. You send Arc USDC to their **play address**.  
6. `/credit_topup RM-XXXX` (if you track fiat ledger) / or they just see on-chain balance.

---

## Commands you’ll use

| Command | Who | Purpose |
|---------|-----|---------|
| `/rails_status` | Admin | Config check |
| `/topups` | Admin | Includes rail_paid queue |
| `/credit_topup RM-XXXX` | Admin | Mark credited after Arc send |
| `/reject_topup RM-XXXX reason` | Admin | Reject |

---

## Security

- **Never** commit `.env` or paste `S…` Stellar secrets / private keys.  
- Ops receive addresses are public (like a bank account number).  
- Rotate Freighter / MetaMask if a machine is compromised.  
- Prefer a dedicated “Boardman receive only” Stellar account (not your personal bag).

---

## One-message checklist for you

```
[ ] Create Stellar testnet account (Freighter / Laboratory)
[ ] Fund with Friendbot XLM
[ ] Copy G… public key → BOARDMAN_OPS_USDC_STELLAR in .env
[ ] STELLAR_NETWORK=testnet
[ ] CLAW_ADMIN_TELEGRAM_IDS=your id
[ ] Restart bot
[ ] /rails_status → Stellar configured: yes
[ ] Test: Get money → Fund with USDC (link) → send small USDC + memo
[ ] Confirm rail_paid + admin ping
[ ] Keep small Arc USDC float for credits
```

When that’s green, Stellar Path A is live for real deposits. Avalanche stays manual-ref until we add the transfer log watcher (needs only the ops 0x you already have).
