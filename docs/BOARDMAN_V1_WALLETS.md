# Boardman V1 wallets & launch (Sept 16, 2026)

**Product:** Boardman by sideQuest (formerly Rematch by sideQuest)  
**Launch target:** **2026-09-16** (with **Arc mainnet**)  
**Base / Avalanche:** later  

---

## Ops money (now → launch)

### Paystack → you (manual)

1. Paystack pings you (email + optional webhook Telegram).  
2. You open Kobox → **swap ₦ → USDC**.  
3. Send USDC to the player’s **Boardman play address** (shown on paid alert).  
4. Bot: `/credit_topup RM-XXXX`.  

**No float yet** = fine. SLA = “when you’re online after the Paystack ping.”  
When you can, build a small USDC float so credits are faster.

### Designated ops wallet

Use a **fresh Kobox / Boardman-only** deposit address for:
- Receiving any platform USDC you hold  
- Sending top-up credits to players  
- Eventually fee cuts  

Put it in env when ready:

```bash
BOARDMAN_OPS_USDC_ADDRESS=0x...
BOARDMAN_FEE_RECIPIENT=0x...   # same or separate
```

---

## Compromised wallet — what to do

**Treat the old key as burned.** Do not reuse it for Boardman.

| Task | Who | Notes |
|------|-----|--------|
| Create **new** EOA (MetaMask / hardware) | You | Boardman-only |
| Create **new** Kobox receive address | You | For ₦↔USDC ops |
| Move any remaining assets off old wallet | You | Only if you still control the key |
| Deploy **new ClawEscrow V1** with new feeRecipient | Dev | Keep V0 addresses archived |
| Update env + `chains.yaml` | Dev | After you send new addresses |

**We cannot send funds from the old wallet without its private key.**  
If the key is leaked, assume funds may already be gone; only move what you still control ASAP.

### Current archived V0 (do not use for Boardman mainnet)

| Role | Address | Notes |
|------|---------|--------|
| Escrow (Arc / Fuji shared in config) | `0xFC44a06295d4fC58420027932A6FcB3C13D83859` | V0 |
| Escrow Base Sepolia | `0xDb76714390ccE1729558DF3c9EC4f45A1690dE78` | V0 |
| Fee / resolver | `0x39EcF94ed35451A67006dcCE4A467aecdfAB6940` | V0 |
| Deployer | `0xB2CCcac46cE93C2ac27fDBF7248938CC57F29424` | V0 |

Fill V1 when you create them:

| Role | V1 address |
|------|------------|
| Boardman deployer / admin EOA | _TBD_ |
| Fee recipient (platform cut) | _TBD_ |
| Ops treasury (USDC credits) | _TBD_ (Kobox) |
| ClawEscrow Arc mainnet | _TBD after deploy_ |

---

## What the Boardman wallet needs (checklist)

### 1) Ops / Kobox (you use every day)
- [ ] Fresh Kobox account/address **only for Boardman**  
- [ ] Naira in for Paystack settlement  
- [ ] Ability to buy/swap USDC and send on **Arc** (mainnet from Sept 16)  
- [ ] Screenshots/logs of each send (ref RM-XXXX)

### 2) Deployer EOA (contract admin)
- [ ] New private key in secure password manager / hardware wallet  
- [ ] Fund with gas on Arc mainnet for deploy + admin txs  
- [ ] Never use on a compromised machine

### 3) Fee recipient
- [ ] Can be same as ops treasury or a separate cold-ish address  
- [ ] Set at **ClawEscrow V1 deploy** (`feeRecipient`)

### 4) Circle (player wallets)
- [ ] Circle wallet set for Boardman (can be existing set if not compromised)  
- [ ] Player **play addresses** stay per-user Circle wallets — not your ops wallet  

---

## Contract plan

| Version | Action |
|---------|--------|
| **V0** | Keep deployment JSON + `CONTRACTS.md` as archive; freeze |
| **V1** | New deploy from clean deployer; `feeRecipient` = Boardman fee wallet |
| Networks at launch | **Arc mainnet** first |
| Later | Base, Avalanche |

Deploy when V1 addresses are ready:

```bash
# after setting PRIVATE_KEY (new deployer) + fee recipient in script/env
npx hardhat run scripts/deploy_escrow.js --network arcMainnet  # when network configured
```

---

## Website focus until Sept 16

**Waitlist** on https://boardman.playingsidequest.fun/  
Promote that URL everywhere. Full play app soft-opens / hard-opens **Sept 16** with Arc.

---

## Paystack email

Paystack dashboard email notifications are enough for manual ops.  
Webhook Telegram is optional extra (`/api/rematch/paystack/webhook`).  
No need for custom email pipeline unless you want it later.
