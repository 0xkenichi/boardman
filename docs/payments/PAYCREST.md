# Naira on/off-ramp: Paycrest + CCTP to Arc

Status: **built, off.** Nothing is visible to players until `PAYCREST_ENABLED=1`
**and** `REAL_MONEY_ENABLED=1` **and** `PAYCREST_API_KEY` is set. Paycrest is
mainnet-only, so switching it on means real money. Read the
[go-live gate](#real-money-go-live-gate) first.

Code: `src/backend/services/paycrest/`, `src/backend/services/bridge/`,
`src/backend/api/paycrest.py`, `src/channels/core/flows/naira.py`,
`frontend/app/rematch/app/naira/[token]/`. Tests: `tests/test_paycrest.py`
(fake Paycrest + fake CCTP, no network).

## What the player sees

* **Top up** (chat: *Add money → Naira via Paycrest*, Telegram money menu
  *Top up with naira (Paycrest)*, or `/naira`): amount → quote (rate, fees,
  "this is real money") → a one-time secure page asks for full name, date of
  birth, BVN or NIN and their own bank account for refunds → the chat and the
  page show the virtual account and exact naira amount to transfer → USDC
  lands in the play wallet, with a message at each step.
* **Cash out** (chat: *Withdraw → Cash out to bank*, or `naira`): bank →
  10-digit account → the bank's name for it ("is this you?") → USD amount →
  quote (≈ naira) → the usual one-time withdraw page with the withdrawal PIN
  → messages when it starts, when the bank is paid, or if it comes back.
* BVN/NIN and PINs are never asked for in chat.

## Architecture

```
TOP UP (on-ramp)
 player bank ──NGN──▶ Paycrest virtual account
                         │  (Paycrest provider pays out)
                         ▼
             USDC on Base ──▶ player's Base "in" wallet (Circle dev-controlled, SCA)
                         │  webhook payment_order.settled ─▶ sweep
                         ▼
             CCTP v2: approve + depositForBurn on Base (Fast Transfer, fee ≤ 5 bps)
                         │  Iris attestation
                         ▼
             receiveMessage on Arc (Boardman relayer wallet pays USDC gas)
                         ▼
                 player's Arc play wallet ── stakes / BoardmanEscrow

CASH OUT (off-ramp)
 Arc play wallet ──CCTP burn (Arc, USDC gas)──▶ mint on Base (relayer pays gas)
                         ▼
             player's Base "out" wallet ──▶ POST /v2/sender/orders (crypto→fiat,
                         │                   refundAddress = this wallet)
                         ├── transfer amountToTransfer to providerAccount.receiveAddress
                         ▼
             Paycrest provider ──NGN──▶ player's bank   (webhook settled → done)
             refund? USDC back to "out" wallet ──CCTP──▶ play wallet
```

State lives in the agentic DB (SQLite locally, Postgres in prod;
`supabase/migrations/20261018120000_paycrest_naira.sql`):

* `paycrest_orders`: one row per top-up / cash-out, with an explicit state
  machine (`store.TRANSITIONS`) and a unique `idempotency_key` that is also the
  `reference` sent to Paycrest. Writes are compare-and-set, so replays, late
  webhooks and two workers cannot double-move money or move an order backwards.
  - top-up: `quoted → submitting → awaiting_deposit → processing → settled → bridging → completed`
    (failures `cancelled`, `failed`, `expired`, `refunding → refunded`)
  - cash-out: `confirmed → bridging_out → on_base → submitting → awaiting_settlement → processing → completed`
    (refund `refunded_on_base → refund_bridging → refunded`; anything odd → `needs_review` + ops alert)
* `paycrest_webhook_events`: dedupe by SHA-256 of the raw body.
* `payment_wallets`: each player's Base "in" and "out" wallets (kept separate
  so a sweep never grabs cash-out money; never replaces the play address).
* `bridge_transfers`: every CCTP leg (`pending → approve_submitted →
  burn_submitted → burned → attested → mint_submitted → minted`), tx ids,
  message, attestation, attempts. Each chain call has a deterministic Circle
  idempotency key, so a retry can't execute twice.

Reconciler (`paycrest/reconcile.py`, every 30 s inside the API when live;
`scripts/reconcile_paycrest.py --report|--apply` by hand): advances due
bridge legs, alerts on transfers stuck > 2 h, resolves ambiguous submits by
looking orders up by reference, polls Paycrest for orders whose webhook is
> 5 min late, retries sweeps / cash-out submits / refunds, expires stale quotes.

## Verified facts (docs read 2026-10-18)

Paycrest ([docs](https://docs.paycrest.io),
[OpenAPI v2](https://docs.paycrest.io/openapi-v2.yaml),
[Sender API guide](https://docs.paycrest.io/implementation-guides/sender-api-integration.md)):

* Base URL `https://api.paycrest.io/v2`, header `API-Key`; KYB required
  before API access (1–3 business days, app.paycrest.io)
  ([quickstart](https://docs.paycrest.io/quickstart.md),
  [compliance](https://docs.paycrest.io/concepts/compliance-security.md)).
* One endpoint for both directions: `POST /v2/sender/orders`; direction by
  `source.type`/`destination.type`. On-ramp: `amountIn: "fiat"`,
  `source.refundAccount {institution, accountIdentifier, accountName}`,
  `source.kyc` **required**; response `providerAccount` is a virtual bank
  account with `amountToTransfer` and `validUntil`. Off-ramp: `source
  {network, refundAddress}`, `destination.recipient {institution,
  accountIdentifier, accountName, memo}`; deposit must equal
  `amountToTransfer` (= amount + senderFee + transactionFee) before
  `validUntil`.
* On-ramp KYC since Oct 2026: person `fullName`, `birthDate` (18+),
  `idDocument {type, number, issuerCountry}`; for NGN a BVN or NIN (11
  digits, issuer NG); the bank-resolved refund-account name must match
  `fullName` or the order is refused (400, field `Source`)
  ([changelog](https://docs.paycrest.io/resources/changelog.md)).
* Statuses: `initiated, deposited, pending, fulfilling, fulfilled, validated,
  settling, settled, cancelled, refunding, refunded, expired`; webhooks
  `payment_order.<status>` plus `payment_order.compliance_hold` (deposit from
  a third-party account; ends `settled` or `refunded` with `refundReason`
  `payer_mismatch | payer_unverified`)
  ([lifecycle](https://docs.paycrest.io/concepts/transaction-lifecycle.md)).
* Webhook signature: `X-Paycrest-Signature` = hex HMAC-SHA256 of the raw body
  keyed with the **API Secret**; compare lowercase hex in constant time.
  Non-2xx retried with backoff for 24 h. Delivery logs/replay:
  `GET /v2/sender/webhooks`, `POST /v2/sender/webhooks/{id}/retry`.
* `GET /v2/rates/{network}/{token}/{amount}/{fiat}?side=buy|sell` (public);
  `GET /v2/institutions/NGN`; `POST /v2/verify-account` returns the account
  name or `"OK"`; `GET /v2/sender/orders/{id}`.
* Minimum order $0.50; Paycrest's fee is in the rate (0.5% per the brief —
  not restated on the pages read); optional sender fee
  (`senderFee`/`senderFeePercent`); `transactionFeePayer: sender|customer`.
* Networks include Base (USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`);
  **Arc is not supported** ([stablecoins](https://docs.paycrest.io/resources/supported-stablecoins.md)).
  "Paycrest is not a licensed financial institution"; senders own their user
  KYC/KYB.

Circle CCTP v2 ([supported chains](https://developers.circle.com/cctp/concepts/supported-chains-and-domains),
[contracts](https://developers.circle.com/cctp/references/contract-addresses),
[interfaces](https://developers.circle.com/cctp/references/contract-interfaces),
[Arc CCTP guide](https://docs.arc.io/integrate/exchanges/cctp-bridging.md)):

* Arc is a CCTP domain: **26** (mainnet listed; Fast Transfer as a source is
  N/A because standard attestation is already fast). Base: **6**, Fast
  Transfer supported.
* Mainnet TokenMessengerV2 `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d`,
  MessageTransmitterV2 `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` (same on
  Base and Arc). Testnet `0x8FE6…2DAA` / `0xE737…E275`.
* `depositForBurn(amount, destinationDomain, mintRecipient(bytes32),
  burnToken, destinationCaller(bytes32), maxFee, minFinalityThreshold)`,
  1000 = fast, 2000 = standard; `destinationCaller = 0` lets anyone relay
  `receiveMessage(message, attestation)`. Iris: `GET /v2/messages/{srcDomain}?transactionHash=`,
  fees `GET /v2/burn/USDC/fees/{src}/{dst}` (bps per finality).

Circle Gas Station ([docs](https://developers.circle.com/wallets/gas-station)):
EVM needs **SCA** (ERC-4337) wallets; works with developer-controlled
wallets; Base and Arc mainnet listed; billed to the developer's card at
**gas + 5%**.

### Uncertain — verify before go-live

1. **BVN placement.** The OpenAPI schema says NGN on-ramp KYC sends BVN as
   `idDocument.type = "BVN"`; the Oct 2026 changelog says "BVN in `taxId`, or
   NIN in `idDocument`". We send `idDocument` (`BVN` or `nationalID`). Test
   one order with Paycrest support; switch in `models.KycPerson.to_api`.
2. **Rate side.** We use `side=buy` for on-ramp, `sell` for off-ramp.
3. **`GET /v2/sender/orders` paging params** (`page`, `pageSize`) used to
   find an order by reference after an ambiguous submit — taken from v1.
4. `validUntil` length for on-ramp virtual accounts and refund timing are not
   documented; we read `validUntil` per order.
5. Paycrest documents no idempotency header; we rely on our unique
   `reference` + lookup before resubmitting.
6. CCTP fast-transfer fee from Base and whether Arc → Base standard transfers
   carry a fee: read live from Iris at burn time; we cap at
   `bridge.max_fee_bps` (5) and fall back to standard if higher.
7. Circle W3S: blockchain label `BASE` for Base mainnet, USDC token UUID on
   BASE and ARC (set `CIRCLE_USDC_TOKEN_ID_BASE_MAINNET`,
   `CIRCLE_USDC_TOKEN_ID_ARC_MAINNET`), and whether SCA and EOA wallets can
   share our existing wallet set.
8. Mainnet Circle wallets reuse the testnet address? `ensure_user_wallet`
   fast-paths to `gaming_deposit_address`; confirm the Arc mainnet play
   wallet mapping before the first mint (go-live gate item 1).

## Flags and config

| Setting | Where | Default |
|---|---|---|
| `PAYCREST_ENABLED` | env | off |
| `REAL_MONEY_ENABLED` | env | off |
| `PAYCREST_API_KEY`, `PAYCREST_API_SECRET` | env (blind, `scripts/set_paycrest_env.sh`) | unset |
| `PAYCREST_ARC_RELAYER_WALLET_ID`, `PAYCREST_BASE_RELAYER_WALLET_ID` | env | unset (mints wait, then alert) |
| `PAYCREST_BASE_GAS_MODE` | env override of `gas.base_mode` | `gas_station` |
| `rails.paycrest_ngn` | `config/funding_rails.yaml` | `enabled: false`; limits, fees, bridge, gas |
| `base_mainnet`, `cctp` | `config/chains.yaml` | `enabled: false` |

Limits (per player, `funding_rails.yaml`): top-up ₦1,000–₦500,000 per order,
₦1,000,000 per 24 h; cash-out $1–$300 per order, $500 per 24 h. Cash-outs also
pass every existing withdraw check (`safety.py` pause, `CLAW_MAX_WITHDRAW_USDC`
= $50 per transfer today, daily cap, link hold, geo-fence, PIN).

### KYC: pass-through (chosen) vs encrypted storage

Paycrest needs the KYC on **every** on-ramp order. We chose **pass-through**:
the page posts it once, the backend validates it, sends it to Paycrest in the
same request and keeps nothing (no column exists; a test dumps every table and
checks no BVN or birth date is there). We keep only the ID *type*, the masked
refund account and Paycrest's order id. Cost: players retype BVN/NIN per
top-up. A "remember me" option would store it AES-GCM-sealed with an
HKDF-derived key (the `keystore.py` approach) — more convenience, more
liability (NDPA), so not built.

Bank account numbers for cash-outs are stored in the order (needed to place
the Paycrest order after the bridge) and masked everywhere else.

### Gas and costs

* **Gas Station (default):** Base "in"/"out" wallets are created as SCA, so
  Circle sponsors approve/burn/transfer gas. Cost: Base gas (typically cents
  per tx) + 5%, billed monthly to the Circle Console card. Set a Gas Station
  policy for Base mainnet limited to the USDC contract and TokenMessengerV2.
* **Hot wallet (`PAYCREST_BASE_GAS_MODE=hot_wallet`):** EOA wallets; before
  each Base tx `gas_tank.ensure_native_gas` tops up from `ADMIN_PRIVATE_KEY`
  (0.0001 ETH per top-up, `chains.yaml base_mainnet`). Cheaper per tx, but a
  hot key and ETH float to manage.
* **Arc:** gas is USDC. Cash-out burns are paid by the player's play wallet
  (we keep $0.05 back); mints by the Boardman Arc relayer wallet — keep it
  funded (a low-balance alert is a go-live item; not built yet).
* Per top-up, roughly: Paycrest network fee (shown before paying) + CCTP fast
  fee ≤ 5 bps + ~3 Base txs of sponsored gas. Per cash-out: ~2 Arc txs (player)
  + 1 Base mint (relayer) + 1 Base transfer + Paycrest fee. Estimates — measure
  on the first live orders.

## Founder setup (in order)

1. **Paycrest KYB** at app.paycrest.io (Sender account; 1–3 business days).
2. **API key + secret**: dashboard → Settings. Run
   `bash scripts/set_paycrest_env.sh` (no `--enable`): both are typed blind
   and written to the VM `.env`; the rail stays off.
3. **Webhook URL** in the Paycrest dashboard:
   `https://boardman-api.playingsidequest.fun/webhooks/paycrest`
   (answers 404 until the rail is on; Paycrest retries for 24 h).
4. **Circle**: in the Console enable Gas Station for **Base mainnet**
   (policy: USDC + TokenMessengerV2 only, a monthly cap); create two
   developer-controlled relayer wallets (Arc mainnet, Base mainnet) and fund
   them (Arc: ~$20 USDC; Base: SCA with Gas Station, or a little ETH); capture
   the USDC token UUIDs for BASE and ARC; re-run the script with the relayer
   wallet ids.
5. **Dry run with dust**: with the go-live gate cleared and caps lowered
   (e.g. ₦2,000 / $2), run `bash scripts/set_paycrest_env.sh --enable`
   (type `REAL MONEY`), do one top-up and one cash-out yourself, and check
   `scripts/reconcile_paycrest.py --report`.

## REAL-MONEY GO-LIVE GATE

All of these must be true, with evidence, before `--enable`. This adds to
`docs/MAINNET_GOLIVE_CHECKLIST.md`; it does not replace it.

1. **Wallet custody.** Today every wallet (play, Base in/out, relayers) is a
   Circle **developer-controlled** wallet: Boardman holds the keys, i.e. the
   product is custodial. Either accept and license that (counsel, item 5) or
   migrate: Circle **user-controlled** wallets where the player's PIN signs
   (Circle's PIN/challenge flow), Boardman keeping only a relayer for gas.
   Migration outline: create user-controlled wallets per player behind a
   flag → show both balances → player-signed sweep from the old wallet →
   stakes and cash-outs only from the user-controlled wallet → retire the
   developer wallets. Also decide the Arc **mainnet** play-wallet mapping (do
   not let `ensure_user_wallet` reuse a testnet address silently).
   **Update 2026-10-18:** the founder chose passkey self-custody (Circle
   Modular Wallets on Arc), built behind `SELF_CUSTODY_WALLETS_ENABLED` — see
   [SELF_CUSTODY_WALLETS.md](SELF_CUSTODY_WALLETS.md). Top-ups then mint to
   the player's own account; the Base transit wallets remain custodial for
   minutes and bank cash-outs from passkey wallets are not wired yet.
2. **Escrow on Arc mainnet.** BoardmanEscrow v2 contracts are **unaudited**:
   external audit, deploy from a dedicated key, verify source, smoke tests
   (see MAINNET_GOLIVE_CHECKLIST §3).
3. **Agent wallet rotation.** Rotate every agent/house wallet key that ever
   lived in a laptop or `.env` (`scripts/rotate_agent_wallets.py`) before
   real money flows through them.
4. **Multisig owner.** Escrow ownership and fee recipient on a multisig;
   resolver and relayers as separate low-balance keys with alerts.
5. **Licence / counsel.** Nigerian counsel sign-off on: taking naira via a
   third party, custodial USDC wallets, skill-staking legality, CBN/SEC
   (VASP) position, NDPA data handling, terms of service and refund policy.
   Paycrest says it is not a licensed institution.
6. **KYC.** Paycrest's per-order KYC covers the payer for on-ramps; decide
   (with counsel) Boardman's own KYC tier for cash-outs and stakes, and
   sanctions screening. Confirm the BVN field placement (uncertain #1).
7. **Caps.** Start with low per-order and daily caps (lower than the
   defaults above), a beta cohort, and `safety.py` pause tested end to end.
8. **Ops.** Relayer and Gas Station balance alerts, a daily reconciliation of
   Paycrest settled orders vs bridge mints vs play-wallet credits, a runbook
   for `needs_review` orders, and someone on call for the first two weeks.
