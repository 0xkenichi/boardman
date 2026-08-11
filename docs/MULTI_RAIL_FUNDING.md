# Multi-rail funding (Path A + abstract balance)

**Product rule for players:** one **play balance**. They never pick a chain to stake.

**Product rule under the hood:** all **stakes** lock on the **settlement rail = Arc** (USDC gas + `BoardmanEscrow`). Other networks are **funding rails** only until they support both USDC gas and dual-lock escrow.

---

## Why

| Rail | Fund? | Stake / escrow? | Gas | Notes |
|------|-------|-----------------|-----|--------|
| **Arc** | ✅ play address | ✅ | USDC | Settlement home |
| **Stellar** | ✅ ops + memo | ❌ | tiny / asset UX | Path A payments; not EVM |
| **Avalanche** | ✅ ops 0x + ref | ❌ for now | AVAX | Convert → Arc; later escrow if USDC gas |
| **Paystack / bank** | ✅ ₦ | ❌ | n/a | Ops credits Arc |
| **Kobox** | ✅ self-serve | ❌ | n/a | User sends USDC to play address |

If Avalanche (or anything) later has **USDC gas + BoardmanEscrow**, set `can_stake: true` and `usdc_gas: true` in `config/funding_rails.yaml` and deploy escrow there. Until then: **always convert to Arc before lock**.

---

## Config

| File | Role |
|------|------|
| `config/funding_rails.yaml` | Rails, labels, convert policy |
| `config/chains.yaml` | EVM/settlement chain params + bridge stub |
| `src/backend/services/funding_rails.py` | Abstract balance, stake gate, deposit copy |

### Env

```bash
BOARDMAN_SETTLEMENT_RAIL=arc
BOARDMAN_OPS_USDC_STELLAR=G...          # Stellar public key
BOARDMAN_STELLAR_MEMO_PREFIX=BM
STELLAR_NETWORK=testnet                 # or public
BOARDMAN_OPS_USDC_AVALANCHE=0x...       # optional; else BOARDMAN_OPS_USDC_ADDRESS
BOARDMAN_OPS_USDC_ADDRESS=0xFA93...     # Arc/EVM ops
```

---

## Player UX

**Get money**
- Paystack ₦  
- Kobox  
- Bank ₦ / USD  
- **USDC on Stellar** (memo = top-up ref)  
- **USDC on Avalanche** (ref in note / screenshot)  
- Crypto → **play address** (Arc)

**Wallet**
- Shows **Play balance: $X** (ready to stake)  
- Not “Arc / Stellar / Avalanche balances” unless something is stuck on another address  

**Lock stake**
- Requires play balance ≥ stake on **Arc**  
- Clear shortfall → Get money (any rail)

---

## Ops flow (manual convert — now)

1. User starts Stellar/Avalanche top-up → bot creates `RM-XXXX` + deposit instructions  
2. User sends USDC to ops on that rail  
3. Ops sees alert / `/topups`  
4. Ops moves value into user’s **Arc play address** (bridge or Kobox or CEX)  
5. `/credit_topup RM-XXXX` if ledger/fiat path; or on-chain send alone if user already sees balance  

Later: Horizon watcher (Stellar) + CCTP/bridge (Avalanche → Arc) with `bridge.auto_convert_to_settlement: true`.

---

## Code hooks

```python
from gaming.src.backend.services.funding_rails import (
    get_abstract_balance,
    ensure_stake_ready,
    settlement_rail_id,
    funding_instructions_html,
)

# Before lock
ready = await ensure_stake_ready(profile_id, stake_usdc)
if not ready.ok:
    show ready.message_html  # no chain jargon
```

---

## Shipped upgrades (next batch)

| Feature | Status |
|---------|--------|
| Stellar Horizon watcher (memo → `rail_paid`) | ✅ code; needs `BOARDMAN_OPS_USDC_STELLAR` |
| `/rails_status` + `/topups` rail_paid queue | ✅ |
| Soft player labels (link / alt, not chain names) | ✅ |
| Avalanche auto Transfer watcher | ⏳ manual ref for now |
| Auto Arc credit from float | ⏳ still `/credit_topup` after send |

**Ops checklist:** [`OPS_WHAT_WE_NEED.md`](./OPS_WHAT_WE_NEED.md)

## What we are *not* doing yet

- BoardmanEscrow on Stellar (not EVM)  
- BoardmanEscrow on Avalanche (needs USDC-gas UX + deploy)  
- Auto SEP-24 anchor widget (Phase 2)  
- Auto CCTP bridge (Phase 3)

---

## Dinner / partner one-liner

> Boardman is multi-rail for **funding** (Naira, Stellar USDC, Avalanche USDC) and single-rail for **play** (Arc USDC + escrow). Players see one balance; we convert into play money before stakes.
