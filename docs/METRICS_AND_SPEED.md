# Testnet metrics & bot/tx speed

## Where metrics live

| What | Where | Notes |
|------|--------|--------|
| **Users count** | `profiles` (count) | Via `get_ops_metrics()` |
| **PLAY-active users** | `profiles` where `play_points > 0` | Ops metric |
| **Resolved volume** | `gaming.challenges` status=`resolved` | Dual-lock ≈ `2 × stake` |
| **Volume by chain** | same + `settlement_chain` | Arc / Base / Avalanche |
| **In-escrow estimate** | challenges locked/playing/submitted | Ops only |
| **Platform fees (7%)** | `gaming.escrow_audit` `movement=fee` | Written on resolve |
| **Gas used** | `escrow_audit.metadata.gas_used` | Resolver txs (cancel/resolve); Circle player locks often don’t expose gas units |
| **Wallet credits/debits** | `wallet_credit_audit` / `wallet_debit_audit` | Deposits & withdraws |
| **Lock latency** | `escrow_audit.metadata.elapsed_sec` | Creator lock path |

### Surfaces

1. **Telegram** — `/metrics`, `/stats`, `/board`, or Public board button  
   Shows users, resolved volume, in-play, fees, gas samples, per-chain dual-lock.

2. **HTTP API** (auth required)  
   `GET /api/stack/v1/metrics`  
   Headers: `X-Rematch-Key: $REMATCH_API_KEY`  
   Returns full `ops` + `chain` JSON.

3. **DB direct**  
   - `gaming.escrow_audit` — lock_in, payout, fee, refund rows  
   - `gaming.challenges` — status pipeline  
   - `profiles` — user count  

### Gaps (honest)

- Rematch ops metrics are **in-product only** (Telegram board, stack API JSON, Supabase tables) — not a separate monitoring product.
- **Legacy `bets` / `platform_fees` tables** in `repositories/analytics.py` are older SideQuest paths; Rematch testnet volume is **challenges + escrow_audit**.
- **Player Circle txs (approve/createMatch)** rarely store `gas_used`; Arc often pays fees in USDC via Circle `feeLevel`. We log **elapsed seconds** and store resolver `gas_used` when the admin wallet settles.

---

## Speed: what we did / knobs

### Already in place

- Escrow Circle calls use `asyncio.to_thread` + `wait_for_transaction_async` so **Telegram polling stays alive** during locks.
- Wallet balance watch default **120s** (`WALLET_WATCH_INTERVAL_SEC`) so it doesn’t starve handlers.

### New knobs (env)

| Env | Default | Effect |
|-----|---------|--------|
| `CIRCLE_FEE_LEVEL` | `LOW` | Circle W3S fee tier (LOW/MEDIUM/HIGH). LOW is usually faster/cheaper on Arc testnet. |
| `CIRCLE_TX_POLL_SEC` | `1.0` | Status poll interval (was 2s). Floor 0.5s. |
| `WALLET_WATCH_INTERVAL_SEC` | `120` | Deposit watcher; `0` disables. |

### Still the hard limit

Lock path is **two sequential on-chain txs**: approve USDC → createMatch/joinMatch. You cannot skip waiting for approve confirmation. Typical Arc: **~15–60s** total; Base/Avalanche can be slower + may need gas tank top-up.

### Further improvements (not all done)

1. **Infinite approve** once per escrow spender — skip re-approve if allowance already ≥ stake (saves one full wait).
2. **Webhook mode** instead of polling for Telegram production.
3. **Circle webhooks** for deposit detection instead of balance watch.
4. **Connection pooling** / single Circle client reuse (today per-call construction is light).
5. Cache `get_balance_summary` for 5–10s on /start.

---

## Quick ops checks

```bash
# API (replace key + host)
curl -s -H "X-Rematch-Key: $REMATCH_API_KEY" https://YOUR_HOST/api/stack/v1/metrics | jq .

# Bot
# /metrics  or  /stats
```

Supabase SQL (example):

```sql
-- Fees collected
select sum(amount_usdc) from gaming.escrow_audit where movement = 'fee' and status = 'confirmed';

-- Gas samples from resolver
select metadata->>'gas_used', tx_hash, movement
from gaming.escrow_audit
where metadata ? 'gas_used'
order by created_at desc limit 20;

-- Users
select count(*) from public.profiles;
```
