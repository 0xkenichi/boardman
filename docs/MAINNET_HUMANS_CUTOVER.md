# Mainnet cutover: real money for humans, practice for the arena

Boardman moves **human friend challenges** to **Arc mainnet** with real USDC
(naira in and out through Paycrest, Circle wallets, passkey wallets). The
**AI arena, spectator betting and AFM football stay on Arc testnet** with
practice chips. Both run in the same backend, kept apart by **money realms**.

Nothing in this document has been run. Every step that moves money, deploys a
contract or touches the VM is the founder's. Do the steps **in order**.

## 1. How the split works (read once)

| Realm | Chain | Money | What uses it |
|---|---|---|---|
| `humans` | `arc_mainnet` (`BOARDMAN_HUMANS_CHAIN`) | real USDC | friend challenges (WhatsApp, Telegram, web), Paycrest top-up and cash-out, passkey wallets |
| `arena` | `arc` = Arc testnet (`BOARDMAN_ARENA_CHAIN`) | practice chips | AI arena, House, spectator bets and LP, AFM, football-ledger wallet bridge, cups, faucet, Stack API |

Code: `src/backend/services/realms.py`. Every chain in `config/chains.yaml`
declares `network: mainnet|testnet`; a chain without one counts as real.

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
3. Circle credentials follow the blockchain. `ARC`/`BASE` use only
   `CIRCLE_API_KEY_LIVE`, `CIRCLE_ENTITY_SECRET_LIVE` and
   `CIRCLE_WALLET_SET_ID_LIVE`. `ARC-TESTNET` and other test chains use only
   `CIRCLE_API_KEY`, `CIRCLE_ENTITY_SECRET` and `CIRCLE_WALLET_SET_ID`. A key
   from the other environment (`LIVE_API_KEY:` vs `TEST_API_KEY:`) is refused.
   The arena uses Circle (practice play wallets, faucet, AFM); it keeps its
   testnet entity.
4. Real-money play wallets are separate wallets, created with the LIVE entity
   (SCA, so Gas Station can sponsor gas) and stored in `payment_wallets` under
   `arc_mainnet/play`. They never replace the profile's practice address.
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

## 2. Arc mainnet facts (checked 2026-10-19)

| Fact | Value | Source |
|---|---|---|
| Chain id | **5042** (`0x13b2`); testnet 5042002 | [docs.arc.io connect](https://docs.arc.io/arc/references/connect-to-arc), [chainlist](https://chainlist.org/chain/5042) |
| RPC | `https://rpc.mainnet.arc.io` (public, no key). Others: Blockdaemon, dRPC, QuickNode, Alchemy | [docs.arc.io RPC endpoints](https://docs.arc.io/arc/references/rpc-endpoints) |
| Explorer | `https://explorer.arc.io` (verify API path unconfirmed; Safe's config uses `/api`) | connect-to-arc; [safe config 5042](https://safe-config.safe.global/api/v1/chains/5042) |
| USDC | `0x3600000000000000000000000000000000000000` (ERC-20 interface, 6 decimals; native gas uses 18 decimals, same balance) | [docs.arc.io contract addresses](https://docs.arc.io/arc/references/contract-addresses) |
| CCTP v2 | domain **26**; TokenMessengerV2 `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d`, MessageTransmitterV2 `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` | [Circle CCTP chains](https://developers.circle.com/cctp/cctp-supported-blockchains), [contracts](https://developers.circle.com/cctp/evm-smart-contracts) |
| Circle wallets | blockchain id `ARC`; EOA + SCA; Gas Station supports Arc mainnet | [supported blockchains](https://developers.circle.com/wallets/supported-blockchains), [Gas Station](https://developers.circle.com/wallets/gas-station) |
| Passkey (Modular) | MSCA on Arc mainnet; transport path `/arc` is inferred from the SDK naming rule, **unverified** (`SELF_CUSTODY_MODULAR_PATH` overrides) | [web SDK](https://developers.circle.com/sdks/modular/web-sdk) |
| Gas | paid in USDC; EIP-1559; min base fee 20 gwei (doc says testnet values may change) | [gas and fees](https://docs.arc.io/arc/references/gas-and-fees) |
| Safe | **supported**: safe-deployments v1.4.1 lists `5042` as canonical (Safe `0x41675C09…461a`, SafeL2 `0x29fcB43b…C762`, ProxyFactory `0x4e1DCf7A…ec67`); Safe config has chain `arc` with tx service `https://api.safe.global/tx-service/arc` (no Safe Apps yet) | [safe-deployments](https://github.com/safe-global/safe-deployments/tree/main/src/assets/v1.4.1), [safe config](https://safe-config.safe.global/api/v1/chains/5042) |

Arc quirks that don't affect BoardmanEscrow: PREVRANDAO is 0, no blob txs,
timestamps can repeat, a tx is final once included
([EVM compatibility](https://docs.arc.io/arc/references/evm-compatibility)).

Circle API keys: one key per environment (`TEST_API_KEY:` / `LIVE_API_KEY:`)
([keys](https://developers.circle.com/api-reference/keys)). The entity-secret
registration endpoint is not in Circle's public API reference; the script uses
the SDK's endpoint and has a Console fallback.

## 3. Before you start

* Branch `launch/arc-mainnet-humans` merged and deployed to the VM with
  **`REAL_MONEY_ENABLED=0`**. With it off nothing changes for players: new
  challenges stay practice. Check `GET /api/health/deep` shows
  `money_realms.humans_live: false`.
* Founder decisions stand: custodial Circle wallets plus passkey wallets,
  unaudited escrow at low caps, no licence yet. The PAYCREST.md go-live gate
  still applies.
* Have ready: a hardware wallet or phone wallet for the Safe signers, ~$30 of
  USDC on Arc mainnet for gas (deployer, resolver, Arc relayer), a little ETH
  or Gas Station on Base.

## 4. Steps, in order

### 4.1 Circle LIVE key (done by the founder)
The mainnet API key is created in the Circle Console (Keys > API key, LIVE).
Store it blind: `bash scripts/set_mainnet_humans_env.sh` (only the key
prompt; leave the rest blank). Never paste it in chat.

### 4.2 Circle LIVE entity, wallet set, relayers (on the VM)
```
ssh ubuntu@150.230.112.144
cd ~/boardman && mkdir -p ~/boardman-secrets && chmod 700 ~/boardman-secrets
docker compose run --rm --no-deps -v "$PWD/.env:/run/boardman.env" -v "$HOME/boardman-secrets:/out" \
  boardman-api python scripts/circle_mainnet_setup.py --env-file /run/boardman.env --recovery-dir /out
# read the plan, then the same command with --apply
```
It generates the entity secret on the VM (never shown), registers it, saves
the recovery file, creates wallet set `boardman-humans-mainnet` and the Arc
(EOA) and Base (SCA) relayer wallets, and prints their addresses. If
registration is refused, rerun with `--console` and paste the ciphertext file
into Console > Wallets > Dev Controlled > Configurator > Entity Secret.

Then, from your laptop, download the recovery file, keep two offline copies,
and delete it from the VM:
```
scp ubuntu@150.230.112.144:boardman-secrets/circle_entity_recovery_*.dat .
ssh ubuntu@150.230.112.144 'shred -u ~/boardman-secrets/circle_entity_recovery_*.dat'
```
Fund the Arc relayer with ~20 USDC on Arc mainnet.

### 4.3 Resolver key (on the VM)
```
docker compose run --rm --no-deps boardman-api python scripts/create_mainnet_resolver.py --apply
```
Note the printed address (= `V2_RESOLVER`). Fund it with ~5 USDC on Arc
mainnet. Its name `resolver_arc_mainnet` is set in 4.9.

### 4.4 Safe on Arc mainnet
At app.safe.global, choose network **Arc**, create a Safe (recommended 2-of-3:
founder hardware wallet, founder phone wallet, a trusted backup signer). Create
a second Safe (or use a separate founder wallet) as the **treasury**
(fee recipient). Owner, treasury and resolver must be three different
addresses.

**Fallback** if Safe{Wallet} can't create on Arc that day: use the founder's
own wallet as owner and pass `V2_OWNER_IS_EOA=1` in 4.5. Move ownership to a
Safe later with `transferOwnership(<Safe>)` from that wallet, then
`acceptOwnership()` from the Safe.

### 4.5 Deploy BoardmanEscrow v2 (laptop, once)
Use a **fresh throwaway** deployer key with ~2 USDC on Arc mainnet. Type it
blind, use it once, forget it:
```
cd contracts && ln -s "<repo>/contracts/node_modules" node_modules   # if needed
read -rs MAINNET_DEPLOYER_KEY && export MAINNET_DEPLOYER_KEY
CONFIRM_V2_DEPLOY=1 V2_OWNER_MULTISIG=<Safe> V2_TREASURY=<treasury> V2_RESOLVER=<4.3 address> \
  npx hardhat run scripts/deploy_v2.js --network arcMainnet
unset MAINNET_DEPLOYER_KEY
```
On mainnet the script deploys the escrow **only** (never a SpectatorPool),
checks chain id 5042 and USDC decimals, refuses an owner with no code unless
`V2_OWNER_IS_EOA=1`, sets `maxStakePerPlayer` to $25
(`ESCROW_MAX_STAKE_USDC`), offers ownership to the Safe and writes
`contracts/deployments/boardman_v2_arcMainnet.json` (commit it). Optional:
`npx hardhat verify --network arcMainnet <escrow> <usdc> <treasury> <resolver> 86400 604800`
(if the explorer API refuses, verify in its UI).

### 4.6 Safe accepts ownership
In the Safe: New transaction > Transaction Builder > address = escrow, ABI
method `acceptOwnership()` (paste the ABI from
`contracts/artifacts/.../BoardmanEscrow.json` or enter the method manually) >
sign with the threshold > execute. Fallback owner: call `acceptOwnership()`
from that wallet. Then check, read-only:
```
ESCROW=<escrow> EXPECT_OWNER=<Safe> EXPECT_RESOLVER=<resolver> EXPECT_TREASURY=<treasury> \
EXPECT_MAX_STAKE_USDC=25 npx hardhat run scripts/check_v2_roles.js --network arcMainnet
```
It must print `OK` with `owner` = the Safe and `pendingOwner` = 0x0.

### 4.7 Gas Station policies (Circle Console, LIVE)
* **Arc mainnet:** sponsor only the humans wallet set; allowlist contracts
  USDC `0x3600…0000`, the new BoardmanEscrow, TokenMessengerV2
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
  is live (`SELF_CUSTODY_CHAIN` unset). Players' testnet passkey accounts are
  not carried over: they set up a mainnet one.

### 4.9 Humans-realm settings (still OFF)
`bash scripts/set_mainnet_humans_env.sh`: escrow address,
`resolver_arc_mainnet`, the USDC token ids on ARC and BASE (Console > token
list, or the relayer wallet balances after funding), caps 25/100. Check
`/api/health/deep`: `money_realms.humans_live` is still false (switch off).

### 4.10 Paycrest
`bash scripts/set_paycrest_env.sh` with the two relayer wallet ids from 4.2.
Webhook URL in the Paycrest dashboard. `PAYCREST_SETTLEMENT_CHAIN` stays the
default `arc_mainnet`, `PAYCREST_DELIVERY_CHAIN` `base_mainnet`.

### 4.11 Switch on
```
bash scripts/set_mainnet_humans_env.sh --enable   # REAL_MONEY_ENABLED=1, GEO_FENCE_STRICT=1
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
   report a result; check the winner's payout on explorer.arc.io and the
   fee in `accruedFees` (`check_v2_roles.js` shows the escrow is fine).
4. Try $26: refused with the cap message. Try a 5th $25 stake in a day:
   refused with the daily message.
5. Cash out $1 from A to your bank.
6. Spectator bet on the arena from A: it uses A's practice chips; A's real
   balance does not move.

### 4.13 Tell players
> Boardman now has real-money matches on Arc. Your old balance stays as
> practice chips: keep using it for AI arena bets, AFM and practice matches.
> Real-money matches start from $0; add money with naira to play. Real-money
> limits for now: $25 per match and $100 a day.

## 5. Existing players

Testnet balances, practice play wallets, the football ledger, LP and spectator
positions **stay practice chips** on Arc testnet (no cash value, never
converted, never cashed out). Each player's real-money balance starts at $0
in a new LIVE-entity wallet (or their mainnet passkey account) and is shown
separately (`/api/rematch/web/wallet?realm=humans`). Open practice challenges
finish on testnet.

## 6. Rollback

| Problem | Do |
|---|---|
| Stop new real-money challenges | `bash scripts/set_mainnet_humans_env.sh --disable` (new challenges fall back to practice; open real matches still lock/settle/refund) |
| Stop all money movement | `CLAW_PAUSED=1` (or the admin pause) |
| Stop money into the escrow | Safe calls `pause()`: create/join stop; resolve, cancel, refunds and withdrawals still work |
| Naira rail problem | `bash scripts/set_paycrest_env.sh` (without `--enable`) |
| Resolver key leaked | Safe `pause()`, `create_mainnet_resolver.py --rotate --apply`, Safe `setResolver(new)`, `--promote --apply`, unpause |
| Gas Station overspend | lower or disable the policy in the Console |

Players' money is never stuck: an unresolved locked match becomes refundable
by anyone after `lockTimeout` (7 days), an unjoined one after `openTimeout`
(24 h).

## 7. Monitoring (first two weeks, daily)

* `escrow_reconciliation` now includes `arc_mainnet` (report tagged
  `realm: humans`): DB-locked stakes vs on-chain escrow.
* `stake_caps.totals_by_chain()`: real stakes per chain.
* `scripts/reconcile_paycrest.py --report`: orders vs bridge mints vs credits.
* Balances: resolver (≥ $2), Arc relayer (≥ $5), Gas Station monthly spend.
* `/api/health/deep` `money_realms`; logs for `[realms] REFUSED` (any line is a
  bug or an attack: investigate the same day).

## 8. Known gaps

* Escrow v2 is **unaudited**; the low caps are the mitigation until an audit.
* Custodial on-chain USDC withdrawals of real money to an external address
  are not wired; real money leaves through Paycrest cash-out (or the
  player's own passkey wallet).
* Bot spectator betting has no country signal; on the arena it follows the
  practice kill switch only.
* Arc mainnet modular (passkey) transport path and the entity-secret
  registration endpoint are unverified (fallbacks above).
