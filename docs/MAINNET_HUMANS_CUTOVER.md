# Mainnet cutover: real money for humans, practice for the arena

This runbook moves **human friend challenges** to **Avalanche C-Chain
mainnet** (`avalanche_mainnet`, chain 43114) with real Circle USDC: naira in
and out through Paycrest, Circle wallets, passkey wallets. The **AI arena,
spectator betting and AFM football stay on Avalanche Fuji** with practice
chips. Both run in the same backend, kept apart by **money realms**.

**Status: not started, and gated.** C-Chain mainnet waits for an external
audit of `BoardmanEscrow` v2 and a written opinion from Nigerian counsel
(milestones M2 and M3 in [docs/avalanche/README.md](avalanche/README.md)).
Nothing in this document has been run. Every step that moves money, deploys a
contract or touches the VM is the founder's. Do the steps **in order**.

Some VM helper scripts were written for the Arc configuration and still write
Arc settings. Section 3 lists them. Port them before you start.

## 1. How the split works (read once)

| Realm | Chain | Money | What uses it |
|---|---|---|---|
| `humans` | `avalanche_mainnet` (`BOARDMAN_HUMANS_CHAIN`) | real USDC | friend challenges (WhatsApp, Telegram, web), Paycrest top-up and cash-out, passkey wallets |
| `arena` | `avalanche` = Fuji (`BOARDMAN_ARENA_CHAIN`) | practice chips | AI arena, House, spectator bets and LP, AFM, football-ledger wallet bridge, cups, faucet, Stack API |

Code: `src/backend/services/realms.py`. Every chain in `config/chains.yaml`
declares `network: mainnet|testnet`; a chain without one counts as real.
Real money is live only when `REAL_MONEY_ENABLED=1` **and** the humans chain
has an escrow address.

**Hard invariants** (tested in `tests/test_money_realms.py`):

1. Real money can never fund arena money. Spectator bets and LP deposits on the
   web debit the **practice** play wallet on the arena chain only (chosen: a
   separate practice balance rather than refusing mainnet users, so everyone
   keeps betting with practice chips). The wallet bridge, AFM market, cup pots,
   spectator pool and the agentic signer all refuse a real chain; the signer
   also refuses to broadcast to a real chain id whatever RPC it is pointed at.
2. Practice money can never reach a bank or a real balance. Paycrest is live
   only when its delivery and settlement chains are both mainnet; CCTP legs
   never cross networks; real balances are on-chain USDC only (the
   `play_adjust` overlay, the legacy ledger and old-address scans are
   practice-only).
3. Circle credentials follow the blockchain. `AVAX`/`BASE` use only
   `CIRCLE_API_KEY_LIVE`, `CIRCLE_ENTITY_SECRET_LIVE` and
   `CIRCLE_WALLET_SET_ID_LIVE`. `AVAX-FUJI` and other test chains use only
   `CIRCLE_API_KEY`, `CIRCLE_ENTITY_SECRET` and `CIRCLE_WALLET_SET_ID`. A key
   from the other environment (`LIVE_API_KEY:` vs `TEST_API_KEY:`) is refused.
   The arena uses Circle (practice play wallets, faucet, AFM); it keeps its
   testnet entity.
4. Real-money play wallets are separate wallets, created with the LIVE entity
   (SCA by default, `BOARDMAN_HUMANS_WALLET_ACCOUNT_TYPE`, so Gas Station can
   sponsor gas) and stored in `payment_wallets` under
   `avalanche_mainnet/play`. They never replace the profile's practice address.
5. The legacy default chain (`CLAW_DEFAULT_CHAIN`, `BOARDMAN_SETTLEMENT_RAIL`,
   a player's preferred chain) can never be real. Real money is reached only
   per row: every challenge carries its `settlement_chain` and every balance
   check, cap, lock and payout uses it.
6. The mainnet escrow resolver is a keystore entry named by
   `BOARDMAN_RESOLVER_KEY_MAINNET`, never an env private key and never the
   testnet resolver.

**Caps** (`src/backend/services/stake_caps.py`): real-money challenges are
capped at `BOARDMAN_HUMANS_MAX_STAKE_USDC` per player per match (default $25)
and `BOARDMAN_HUMANS_DAILY_STAKE_USDC` per player per rolling 24 h (default
$100). Enforced server-side at both lock chokepoints (custodial and passkey)
with an atomic reservation, and shown in the WhatsApp/Telegram copy when the
stake is picked. The escrow also has an on-chain `maxStakePerPlayer`, set to
$25 at deploy; the Safe raises it with `setMaxStake` after an audit.

**Tagging and reconciliation:** challenges (`settlement_chain`), escrow audit
rows (`metadata.chain`), Paycrest orders (`chain`), bridge legs
(`src_chain`/`dst_chain`), real wallets (`payment_wallets.chain`) and every
real stake (`realm_stakes`, with `realm` and `chain`) say which chain their
money is on. The agentic ledger is arena-only by invariant.

## 2. Avalanche C-Chain facts

From `config/chains.yaml` (`avalanche_mainnet`), `contracts/hardhat.config.js`
and `contracts/scripts/deploy_v2.js`. Circle support checked 2026-11-01.

| Fact | Value |
|---|---|
| Chain id | **43114** (Fuji: 43113) |
| RPC | `https://api.avax.network/ext/bc/C/rpc` (override: `AVALANCHE_MAINNET_RPC_URL`) |
| Explorer | `https://snowtrace.io`. Contract verification goes through Routescan (`npx hardhat verify --network avalancheMainnet …`) |
| USDC | Circle `0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E` (6 decimals) |
| Gas | **AVAX**, not USDC. The platform gas tank (`src/backend/services/gas_tank.py`) tops up a custodial wallet below 0.01 AVAX with 0.05 AVAX, from `ADMIN_PRIVATE_KEY` (or `GAS_TANK_PRIVATE_KEY`). SCA wallets can instead be sponsored by Circle Gas Station |
| CCTP v2 | domain **1**; TokenMessengerV2 `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d`, MessageTransmitterV2 `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64`. Base is domain 6 |
| Circle wallets | blockchain id `AVAX` (Fuji: `AVAX-FUJI`); developer-controlled EOA and SCA; Modular Wallets (MSCA); Gas Station supports Avalanche mainnet and Fuji |
| Passkey (Modular) | transport path `avalanche` (`src/backend/services/self_custody/config.py`; `SELF_CUSTODY_MODULAR_PATH` overrides). Confirm it in the Circle Console before switching passkeys on |
| Hardhat network | `avalancheMainnet`; deploy with `npm run deploy:v2:avalanche-mainnet` |
| Backend env | escrow `BOARDMAN_ESCROW_ADDRESS_AVALANCHE_MAINNET`; Circle USDC token id `CIRCLE_USDC_TOKEN_ID_AVALANCHE_MAINNET`; Paycrest relayer `PAYCREST_AVALANCHE_RELAYER_WALLET_ID` |

Circle API keys: one key per environment (`TEST_API_KEY:` / `LIVE_API_KEY:`).
The entity-secret registration endpoint is not in Circle's public API
reference; `scripts/circle_mainnet_setup.py` uses the SDK's endpoint and has
a Console fallback.

## 3. Before you start

* Both gates are passed: the external audit report is published and its
  fixes are in, and counsel's written opinion allows real-money skill-game
  settlement.
* The build is deployed to the VM with **`REAL_MONEY_ENABLED=0`**. With it off
  nothing changes for players: new challenges stay practice. Check
  `GET /api/health/deep` shows `money_realms.humans_live: false`.
* **Port the Arc-era helper scripts.** Do not run them as they are on this
  build:

  | Script | What it does today | What Avalanche needs |
  |---|---|---|
  | `scripts/set_mainnet_humans_env.sh` | Always writes `BOARDMAN_HUMANS_CHAIN=arc_mainnet` and `BOARDMAN_ARENA_CHAIN=arc`, plus `BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET` and `CIRCLE_USDC_TOKEN_ID_ARC_MAINNET`. Running it would move the arena off Fuji | `BOARDMAN_HUMANS_CHAIN=avalanche_mainnet`, `BOARDMAN_ARENA_CHAIN=avalanche`, `BOARDMAN_ESCROW_ADDRESS_AVALANCHE_MAINNET`, `CIRCLE_USDC_TOKEN_ID_AVALANCHE_MAINNET` |
  | `scripts/circle_mainnet_setup.py` | Entity secret and wallet set (chain-neutral), then relayer wallets on `ARC` and `BASE` | A relayer on `AVAX` → `PAYCREST_AVALANCHE_RELAYER_WALLET_ID`, plus the `BASE` one |
  | `scripts/set_paycrest_env.sh` | Asks for an Arc relayer id (`PAYCREST_ARC_RELAYER_WALLET_ID`) | `PAYCREST_AVALANCHE_RELAYER_WALLET_ID` |
  | `scripts/create_mainnet_resolver.py` | Default entry name `resolver_arc_mainnet` | Pass `--name resolver_avalanche_mainnet`; fund it with AVAX |
  | `contracts/scripts/lib/v2_roles.js` | Treats only `arcMainnet` / `baseMainnet` as mainnets | Pass every `EXPECT_*`, including `EXPECT_USDC`, on `avalancheMainnet` (4.6) |

* Founder decisions stand: custodial Circle wallets plus passkey wallets,
  escrow at low caps, no licence yet. The PAYCREST.md go-live gate still
  applies.
* Have ready: a hardware wallet or phone wallet for the Safe signers, a few
  AVAX on C-Chain for gas (deployer, resolver, Avalanche relayer, gas tank),
  and a little ETH or a Gas Station policy on Base.

## 4. Steps, in order

### 4.1 Circle LIVE key (done by the founder)
Create the mainnet API key in the Circle Console (Keys > API key, LIVE).
Store it blind as `CIRCLE_API_KEY_LIVE` on the VM, with the ported
`set_mainnet_humans_env.sh`. Never paste it in chat.

### 4.2 Circle LIVE entity, wallet set, relayers (on the VM)
```
ssh ubuntu@150.230.112.144
cd ~/boardman && mkdir -p ~/boardman-secrets && chmod 700 ~/boardman-secrets
docker compose run --rm --no-deps -v "$PWD/.env:/run/boardman.env" -v "$HOME/boardman-secrets:/out" \
  boardman-api python scripts/circle_mainnet_setup.py --env-file /run/boardman.env --recovery-dir /out
# read the plan, then the same command with --apply
```
It generates the entity secret on the VM (never shown), registers it, saves
the recovery file, creates wallet set `boardman-humans-mainnet` and the
relayer wallets (`AVAX` EOA and `BASE` SCA once ported), and prints their
addresses. If registration is refused, rerun with `--console` and paste the
ciphertext file into Console > Wallets > Dev Controlled > Configurator >
Entity Secret.

Then, from your laptop, download the recovery file, keep two offline copies,
and delete it from the VM:
```
scp ubuntu@150.230.112.144:boardman-secrets/circle_entity_recovery_*.dat .
ssh ubuntu@150.230.112.144 'shred -u ~/boardman-secrets/circle_entity_recovery_*.dat'
```
Fund the Avalanche relayer with AVAX on C-Chain. It pays the gas for CCTP
mints on Avalanche.

### 4.3 Resolver key (on the VM)
```
docker compose run --rm --no-deps boardman-api python scripts/create_mainnet_resolver.py \
  --name resolver_avalanche_mainnet --apply
```
Note the printed address (= `V2_RESOLVER`). Fund it with a little AVAX on
C-Chain: it pays gas for resolve, cancel and dispute. Its entry name goes into
`BOARDMAN_RESOLVER_KEY_MAINNET` in 4.9.

### 4.4 Safe on Avalanche C-Chain
At app.safe.global, choose **Avalanche**, create a Safe (recommended 2-of-3:
founder hardware wallet, founder phone wallet, a trusted backup signer).
Create a second Safe (or use a separate founder wallet) as the **treasury**
(fee recipient). Owner, treasury and resolver must be three different
addresses.

**Fallback** if a Safe can't be created that day: use the founder's own
wallet as owner and pass `V2_OWNER_IS_EOA=1` in 4.5. Move ownership to a Safe
later with `transferOwnership(<Safe>)` from that wallet, then
`acceptOwnership()` from the Safe.

### 4.5 Deploy BoardmanEscrow v2 (laptop, once)
Use a **fresh throwaway** deployer key with a little AVAX on C-Chain. Type it
blind, use it once, forget it:
```
cd contracts
read -rs MAINNET_DEPLOYER_KEY && export MAINNET_DEPLOYER_KEY
CONFIRM_V2_DEPLOY=1 V2_OWNER_MULTISIG=<Safe> V2_TREASURY=<treasury> V2_RESOLVER=<4.3 address> \
  npm run deploy:v2:avalanche-mainnet
unset MAINNET_DEPLOYER_KEY
```
On mainnet the script deploys the escrow **only** (never a SpectatorPool),
checks chain id 43114 and USDC decimals, refuses an owner with no code unless
`V2_OWNER_IS_EOA=1`, sets `maxStakePerPlayer` to $25
(`ESCROW_MAX_STAKE_USDC`), offers ownership to the Safe and writes
`contracts/deployments/boardman_v2_avalancheMainnet.json` (commit it). It
prints the env line `BOARDMAN_ESCROW_ADDRESS_AVALANCHE_MAINNET=<escrow>`.
Verify the source on Snowtrace:
`npx hardhat verify --network avalancheMainnet <escrow> <usdc> <treasury> <resolver> 86400 604800`.

### 4.6 Safe accepts ownership
In the Safe: New transaction > Transaction Builder > address = escrow, ABI
method `acceptOwnership()` (paste the ABI from
`contracts/artifacts/.../BoardmanEscrow.json` or enter the method manually) >
sign with the threshold > execute. Fallback owner: call `acceptOwnership()`
from that wallet. Then check, read-only:
```
ESCROW=<escrow> EXPECT_OWNER=<Safe> EXPECT_RESOLVER=<resolver> EXPECT_TREASURY=<treasury> \
EXPECT_USDC=0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E EXPECT_MAX_STAKE_USDC=25 EXPECT_ACCEPTED=1 \
  npx hardhat run scripts/check_v2_roles.js --network avalancheMainnet
```
It must print `OK`. `EXPECT_ACCEPTED=1` makes it fail unless `owner` = the Safe
and `pendingOwner` = 0x0 (without it, a not-yet-accepted ownership only prints
a NOTE). Pass every `EXPECT_*` above: the role-check library does not yet
require them, or know the USDC address, on `avalancheMainnet`.

### 4.7 Gas Station policies (Circle Console, LIVE)
* **Avalanche mainnet:** sponsor only the humans wallet set; allowlist
  contracts USDC `0xB97E…a6E`, the new BoardmanEscrow, TokenMessengerV2
  `0x28b5…cf5d`; per-transaction gas cap; monthly spend cap (start ~$50) with
  an alert at 50%.
* **Base mainnet:** USDC `0x8335…2913` and TokenMessengerV2 only; same caps.

### 4.8 Passkey wallets (web)
* Console > Keys: create a **mainnet client key**; Console > Modular Wallets >
  Passkey: allowed domain = the site's domain (the passkey RP ID must match).
* Vercel: `NEXT_PUBLIC_CIRCLE_CLIENT_KEY` = the mainnet client key; keep
  `NEXT_PUBLIC_CIRCLE_CLIENT_URL` default. Redeploy with
  `scripts/deploy_frontend.sh`.
* VM: passkey wallets follow the humans chain automatically once real money
  is live (`SELF_CUSTODY_CHAIN` unset). Players' Fuji passkey accounts are
  not carried over: they set up a mainnet one.

### 4.9 Humans-realm settings (still OFF)
With the ported `set_mainnet_humans_env.sh`: the escrow address
(`BOARDMAN_ESCROW_ADDRESS_AVALANCHE_MAINNET`), `BOARDMAN_RESOLVER_KEY_MAINNET=resolver_avalanche_mainnet`,
the Circle USDC token ids on `AVAX` and `BASE` (Console > token list, or the
relayer wallet balances after funding), caps 25/100, and
`BOARDMAN_HUMANS_CHAIN=avalanche_mainnet` with `BOARDMAN_ARENA_CHAIN=avalanche`.
Check `/api/health/deep`: `money_realms.humans_live` is still false (switch off).

### 4.10 Paycrest
With the ported `set_paycrest_env.sh`: the Paycrest key and secret, and the
two relayer wallet ids from 4.2 (`PAYCREST_AVALANCHE_RELAYER_WALLET_ID`,
`PAYCREST_BASE_RELAYER_WALLET_ID`). Webhook URL in the Paycrest dashboard.
`PAYCREST_SETTLEMENT_CHAIN` stays the configured `avalanche_mainnet`,
`PAYCREST_DELIVERY_CHAIN` `base_mainnet`.

### 4.11 Switch on
```
bash scripts/set_mainnet_humans_env.sh --enable   # ported; REAL_MONEY_ENABLED=1, GEO_FENCE_STRICT=1
bash scripts/set_paycrest_env.sh --enable
```
`/api/health/deep` now shows `humans_live: true`. New friend challenges are
real money; anything already open keeps its practice chain.

### 4.12 First ₦1,000 test (founder, two accounts)
1. Account A: Add money > Naira via Paycrest > ₦1,000. Pay from your own
   bank. Expect the USDC (≈ ₦1,000 / rate, minus fees) in A's **real** balance
   in under 30 min. `python scripts/reconcile_paycrest.py --report`.
2. Top up account B the same way.
3. A challenges B for **$2**; both lock (the challenge says "Real money");
   report a result; check the winner's payout on snowtrace.io and the
   fee in `accruedFees` (`check_v2_roles.js` shows the escrow is fine).
4. Try $26: refused with the cap message. Try a 5th $25 stake in a day:
   refused with the daily message.
5. Cash out $1 from A to your bank.
6. Spectator bet on the arena from A: it uses A's practice chips; A's real
   balance does not move.

### 4.13 Tell players
> Boardman now has real-money matches. Your old balance stays as practice
> chips: keep using it for AI arena bets, AFM and practice matches.
> Real-money matches start from $0; add money with naira to play. Real-money
> limits for now: $25 per match and $100 a day.

## 5. Existing players

Testnet balances, practice play wallets, the football ledger, LP and spectator
positions **stay practice chips** on Fuji (no cash value, never converted,
never cashed out). Each player's real-money balance starts at $0 in a new
LIVE-entity wallet (or their mainnet passkey account) and is shown
separately (`/api/rematch/web/wallet?realm=humans`). Open practice challenges
finish on Fuji.

## 6. Rollback

| Problem | Do |
|---|---|
| Stop new real-money challenges | `bash scripts/set_mainnet_humans_env.sh --disable` (writes only `REAL_MONEY_ENABLED=0`; new challenges fall back to practice; open real matches still lock/settle/refund) |
| Stop all money movement | `CLAW_PAUSED=1` (or the admin pause) |
| Stop money into the escrow | Safe calls `pause()`: create/join stop; resolve, cancel, refunds and withdrawals still work |
| Naira rail problem | `bash scripts/set_paycrest_env.sh` (without `--enable`) |
| Resolver key leaked | Safe `pause()`, `create_mainnet_resolver.py --name resolver_avalanche_mainnet --rotate --apply`, Safe `setResolver(new)`, `--promote --apply`, unpause |
| Gas Station overspend | lower or disable the policy in the Console |

Players' money is never stuck: an unresolved locked match becomes refundable
by anyone after `lockTimeout` (7 days), an unjoined one after `openTimeout`
(24 h).

## 7. Monitoring (first two weeks, daily)

* `escrow_reconciliation` adds the humans chain (`avalanche_mainnet`) once
  real money is live: DB-locked stakes vs on-chain escrow.
* `stake_caps.totals_by_chain()`: real stakes per chain.
* `scripts/reconcile_paycrest.py --report`: orders vs bridge mints vs credits.
* AVAX balances of the resolver, the Avalanche relayer and the gas tank key,
  and the Gas Station monthly spend in the Console.
* `/api/health/deep` `money_realms`; logs for `[realms] REFUSED` (any line is a
  bug or an attack: investigate the same day).

## 8. Known gaps

* The external audit (M2) must be done before this runbook starts. Until then
  the escrow is covered only by the internal October 2026 review
  ([docs/security/AUDIT_2026-10_contracts.md](security/AUDIT_2026-10_contracts.md)).
* The helper scripts in section 3 still target Arc.
* Custodial on-chain USDC withdrawals of real money to an external address
  are not wired; real money leaves through Paycrest cash-out (or the
  player's own passkey wallet).
* Bot spectator betting has no country signal; on the arena it follows the
  practice kill switch only.
* The Avalanche modular (passkey) transport path and the entity-secret
  registration endpoint are unverified (fallbacks above).
* `frontend/lib/selfCustody/wallet.ts` declares USDC as the chain's native
  currency, which was true on Arc. On Avalanche it is AVAX. Fix it before
  passkey wallets go live.
