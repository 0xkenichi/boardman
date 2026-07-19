# ClawStation MVP — Challenge → Lock → AI Vision → Payout

## Player flow (Telegram)

1. **`/start`** — creates profile + `gaming_tag` (prefers Telegram `@username`) + Circle wallet (Base Sepolia deposit address).
2. **Fund** — send Base Sepolia USDC to the deposit address; `/balance` reads on-chain.
3. **`/challenge @tag 5 EAFC private [chain]`** — create challenge; default chain is live escrow (`base`).
4. Opponent **Accept** (inline button).
5. **Both** run `/lock_stake <challenge_id>` (creator first, then opponent).
6. Play the match offline (PS5 / Xbox / PC).
7. **Submit proof**
   - Text: `/submit_score <id> 3`
   - Or photo with caption `/submit_score <id>` — **AI vision** extracts score.
8. When both scores/screenshots are in → settlement job resolves winner and pays on-chain (7% fee).

## Commands

| Command | Purpose |
|---------|---------|
| `/start` | Profile + wallet |
| `/profile` / `/profile @tag` | View tags |
| `/challenge` | Create challenge |
| `/chains` | List Arc / Base / Avalanche |
| `/lock_stake` | On-chain USDC lock via ClawEscrow |
| `/submit_score` | Score or screenshot (AI) |
| `/dispute` | Escalate to admin |

## Multi-chain

| Chain | Status | Gas |
|-------|--------|-----|
| **base** (Sepolia) | Escrow **live** | ETH tank |
| **arc** | Deploy pending | USDC-native |
| **avalanche** (Fuji) | Deploy pending | AVAX tank |

Deploy:

```bash
cd contracts
npx hardhat run scripts/deploy_escrow.js --network arcTestnet
npx hardhat run scripts/deploy_escrow.js --network avalancheFuji
```

Then set `CLAW_ESCROW_ADDRESS_ARC` / `CLAW_ESCROW_ADDRESS_AVALANCHE`.

## DB migration

Apply `supabase/migrations/049_clawstation_mvp_chain.sql` for `settlement_chain` + AI columns + `declined` status.

## Background jobs

Bot scheduler (every ~2 min):

- Expire stale open challenges
- `settle_all_pending()` for `submitted` challenges
