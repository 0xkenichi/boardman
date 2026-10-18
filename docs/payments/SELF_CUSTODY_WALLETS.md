# Self-custody passkey wallets on Arc

Status: **built, off.** Nothing changes for any player until
`SELF_CUSTODY_WALLETS_ENABLED=1`. With the flag off every route answers 404,
chats keep the in-chat "Yes, lock it" and the PIN withdraw page, and the
custodial Circle developer-controlled wallets keep working exactly as today.

Founder decision (2026-10-18): copy BlinkBox's custody model. Each player
holds their own wallet, approved with a passkey on their phone; the bot only
*prepares* transactions; Boardman never holds the keys.

Research read on 2026-10-18. Facts carry a link; anything not confirmed by
a primary source is marked **(unverified)**.

## 1. Research

### Circle Modular Wallets (passkey smart accounts)

* **Arc is supported, mainnet and testnet.** Circle's supported-blockchains
  table lists Arc (`ARC` / `ARC-TESTNET`) with **MSCA** in the *Modular*
  column (also Arbitrum, Avalanche, Base, Monad, OP, Polygon, Unichain; *not*
  Ethereum mainnet or Solana).
  [developers.circle.com/wallets/supported-blockchains](https://developers.circle.com/wallets/supported-blockchains)
* **What it is.** User-controlled ERC-4337 smart accounts (Circle's MSCA,
  ERC-6900 modules, EntryPoint v0.7). "Users control their keys with passkeys
  (WebAuthn)"; the app never holds keys.
  [wallets/modular](https://developers.circle.com/wallets/modular),
  [account types](https://developers.circle.com/wallets/account-types),
  [key features](https://developers.circle.com/wallets/modular/key-features)
* **SDK.** Web: `@circle-fin/modular-wallets-core` with `viem`
  (`viem/account-abstraction`). Flow, verbatim from the quickstart:
  `toPasskeyTransport(clientUrl, clientKey)` →
  `toWebAuthnCredential({transport, mode: WebAuthnMode.Register | Login, username})` →
  `toModularTransport(\`${clientUrl}/arcTestnet\`, clientKey)` →
  `createPublicClient` → `toCircleSmartAccount({client, owner: toWebAuthnAccount({credential})})` →
  `createBundlerClient({account, chain, transport})`. The quickstart uses
  `arcTestnet` from `viem/chains`.
  [create a modular wallet](https://developers.circle.com/wallets/modular/create-a-modular-wallet),
  [web SDK](https://developers.circle.com/sdks/modular/web-sdk)
* **Client key.** Console → Keys → *Client Key*; the passkey domain
  (Console → Wallets → Modular Wallets → Passkey) must match the client
  key's web domain. Client URL `https://modular-sdk.circle.com/v1/rpc/w3s/buidl`.
  The client key ships to the browser (it is domain-bound, not a secret).
  [create a modular wallet](https://developers.circle.com/wallets/modular/create-a-modular-wallet)
* **Address.** "Deterministic, so you can read it before the account is
  deployed onchain" (counterfactual; deployed on the first UserOperation).
  Same address on every chain: **(unverified)** for modular wallets — Circle
  documents unified EVM addressing only for its developer-controlled API
  ([unified addressing](https://developers.circle.com/w3s/unified-wallet-addressing-evm)).
  We never assume it: the Base address is read separately (see §4.5).
* **Batching.** `sendUserOperation({calls: [...]})` runs several calls
  (e.g. USDC `approve` + the contract that spends it) atomically under one
  passkey signature.
  [batch and parallel user operations](https://developers.circle.com/wallets/modular/batch-and-parallel-user-operations)
* **Bundler.** UserOperations go to Circle's bundler over JSON-RPC via the
  modular transport; the app watches `getUserOperationReceipt` /
  `waitForUserOperationReceipt` and must resubmit failures itself.
  [web SDK](https://developers.circle.com/sdks/modular/web-sdk)
* **Gas.** Two options:
  1. *Gas Station* (`paymaster: true`): Boardman sponsors gas under a Console
     policy, billed to the developer card at gas + 5 %. Arc mainnet and
     testnet listed. [gas station](https://developers.circle.com/wallets/gas-station)
  2. *No paymaster on Arc*: Arc's native gas token **is** USDC (18-decimal
     native accounting, same balance as the 6-decimal ERC-20 at
     `0x3600…0000`), so the smart account can pay its own prefund from the
     player's USDC. [Arc gas and fees](https://docs.arc.io/arc/references/gas-and-fees.md)
  *Circle Paymaster* (users pay gas in USDC on ETH-gas chains, +10 %) lists
  Arbitrum, Avalanche, Base, Ethereum, OP, Polygon, Unichain — **not Arc**,
  and Arc does not need it. [paymaster](https://developers.circle.com/paymaster)
  Default here: `SELF_CUSTODY_SPONSOR_GAS=1` (Gas Station) so a player with
  exactly $5 can stake $5; set 0 to let players pay Arc gas (~$0.001/tx
  design target).
* **Recovery.** Optional. `registerRecoveryAddress` adds a backup EOA signer
  derived from a BIP-39 mnemonic the *player* keeps; `executeRecovery` binds
  a new passkey later. Must be set up while the passkey still works; passkey
  *and* mnemonic lost = funds lost; recovery adds a passkey, it does not
  remove a stolen one. [passkey recovery](https://developers.circle.com/wallets/modular/set-up-passkey-recovery)
  Passkeys themselves sync through iCloud Keychain / Google Password Manager,
  which covers "new phone" for most players.
* **Pricing.** Circle Wallets bill per monthly active wallet: first 1,000
  free, then $0.05 → $0.02 per MAW by tier; $0.01 rebate per MAW holding ≥ 10
  USDC. Arc is not in the published chain list for that table and the pages
  disagree by region — **confirm with Circle sales**.
  [circle.com/wallets](https://www.circle.com/wallets)

### Circle User-Controlled Wallets (PIN / social login, MPC)

* Arc mainnet and testnet supported (EOA and SCA).
  [supported blockchains](https://developers.circle.com/wallets/supported-blockchains)
* The player approves with a Circle PIN or social login inside Circle's Web
  SDK iframe/UI; the app must create a Circle *user* and obtain a user token
  server-side for each session (more backend coupling, Circle owns the UX).
* Fits a chat link (web page) as well as passkeys do, and has no WebAuthn
  webview problem, but the PIN is one more secret and the UX is Circle's.
  Kept as the **fallback** if passkeys fail in the field.

### MoonPay PayBox (BlinkBox's wallet)

* Consumer product launched 2026-07-29; passkey per transaction ("Always
  Ask") or rules-based autonomy; keys on Sodot MPC/TEE infrastructure.
  Chains: Solana, Ethereum, Base, Arbitrum, Polygon, Hyperliquid, Tempo,
  Robinhood Chain — **no Arc**.
  [The Block](https://theblock.co/post/410032/moonpay-paybox-chatgpt-claude),
  [Finovate](https://finovate.com/moonpay-lets-ai-agents-transact-with-paybox/)
* **No public third-party developer SDK found** (`@paybox-sh/sdk`, an MCP at
  `api.paybox.sh/mcp` were named in the brief; neither is documented
  publicly — **(unverified)**). Using it would mean moving real-money play
  to Base and redeploying the escrow there.

### Passkeys inside Telegram / WhatsApp

* Android `WebView` only does WebAuthn when the *host app* opts in
  (`WebSettingsCompat.setWebAuthenticationSupport`, Credential Manager).
  [developer.android.com](https://developer.android.com/identity/sign-in/credential-manager-webview)
  We have no evidence Telegram or WhatsApp opt in.
* Generic guidance: embedded webviews "may restrict WebAuthn"; the fix is
  the system browser / Custom Tabs / `ASWebAuthenticationSession`.
  [mojoauth](https://mojoauth.com/blog/known-broken-passkey-combinations-and-workarounds.md)
* Telegram documents that its *own* passkeys use RP ID `telegram.org`; that
  restriction is about Telegram login, not our domain.
  [core.telegram.org/api/passkeys](https://core.telegram.org/api/passkeys)
* Mini Apps can call `openLink(url, {try_browser})` to leave the webview.
  [telegram-mini-apps docs](https://docs.telegram-mini-apps.com/platform/methods)
* **Verdict: unverified per client, so the page never assumes.** It feature-
  detects (`PublicKeyCredential` + `isUserVerifyingPlatformAuthenticatorAvailable`)
  and sniffs the in-app browser (`Telegram`, `WhatsApp`, `FBAN/FBAV`, `wv`);
  in a webview it shows **"Open in your browser"** (copy link + an
  `intent://` link on Android), and only offers the passkey button where it
  can work. Device matrix to test before launch: §6.

## 2. Decision

**Circle Modular Wallets on Arc**, passkey-owned, with Gas Station
sponsorship. Arc is supported on both networks, so real money stays on Arc
and the existing escrow; it is the closest copy of BlinkBox (passkey per
action, bot prepares, user approves). Fallbacks, in order: Circle
user-controlled wallets on Arc (PIN), then PayBox on Base (would move real
money and the escrow to Base).

## 3. How it works

```
chat: "Lock my stake"                         chat: "Withdraw 20 to 0x…"
   │ backend: intent (lock_create|lock_join|withdraw) + calls + one-time token
   ▼
https://<site>/app/approve/<token>   (opened in the phone's browser)
   │ page shows EXACTLY what is signed: "Lock 5.00 USDC into escrow match
   │ ABC123 on Arc" / "Send 20.00 USDC to 0x…", the contract and calldata
   │ player taps Approve → passkey (Face ID / fingerprint)
   │ browser: Circle smart account → sendUserOperation({calls}) → bundler
   │ waits for the receipt → POST {tx_hash, user_op_hash, echoed amount/match}
   ▼
backend: claims the token (single use), records the hash, then CONFIRMS
ON CHAIN: tx receipt status 1 + the escrow's own MatchCreated / MatchJoined
log (address = configured escrow, matchId, player = the player's account,
stake) or the USDC Transfer log. Only then: challenge → creator_locked /
locked, escrow_audit row, notices. A watcher also scans for those logs, so
a closed tab still confirms; a client that lies confirms nothing.
```

* **Lock (creator).** v2 escrow: `[USDC.approve(escrow, stake),
  escrow.createMatch(matchId, player2, stake, deadline, resolverSig)]` in one
  UserOperation. The permit is EIP-712 signed server-side by the resolver key
  (`onchain.sign_create_permit`, same key as settlement) and binds player1 =
  this smart account, player2 = the opponent's escrow address (their passkey
  account if they have one, else their Circle wallet), stake, a 10-minute
  deadline. On a v1 escrow (today's testnet deploy) the call is
  `createMatch(bytes32,uint256)`; the version comes from
  `BOARDMAN_ESCROW_VERSION` or the on-chain probe.
* **Lock (opponent).** `[USDC.approve(escrow, stake), escrow.joinMatch(matchId)]`.
  Routed to the passkey only if the address bound as player2 is their passkey
  account (a player who sets up a passkey *between* the two locks finishes
  that match on the old wallet).
* **Payout.** `resolveMatch(matchId, winner)` only pays a recorded player,
  so winnings always go back to the account that staked — the smart account
  for passkey players. Settlement asks `self_custody.locked_address()` first.
  Refunds (`cancelMatch`, `refundExpired`) also go to the recorded players.
* **Withdraw.** `[USDC.transfer(dest, amount)]` from the player's account.
  No PIN (the passkey is the factor). Boardman's pause and caps are not
  applied — it is the player's money; the geo check stays at the chat.
  Locks *do* keep Boardman's rules (pause, stake limits, lock rate): those
  gate entry into a Boardman match, not the wallet.
* **Approve links** reuse the withdraw-link store (`channel_tokens`, purpose
  `sc_approve`; setup links `sc_setup`): 256-bit token, SHA-256 at rest,
  10-minute TTL, single use (claimed on submit), a newer link supersedes the
  open one, 5 per hour per player. The intent (`self_custody_intents`) binds
  profile, account, action, amount, match and the exact calls; the page
  echoes amount and match back and a mismatch burns the link.
* **Confirmation** (`intents.confirm`): the receipt must have status 1 *and*
  a log from the configured escrow (or USDC) contract with this match id,
  this account and this stake. A hash without that event is ignored (the
  watcher keeps scanning logs); a reverted one fails the intent; one tx can
  confirm one intent (unique index). The watcher runs every 20 s inside the
  API while the flag is on and expires prepared intents 30 min after expiry.
* **A UserOperation that reverts inside a landed bundle** is caught on the
  page (`success: false`): nothing is reported, the link stays open.
* **Wallet setup** `/app/wallet/setup?t=<token>` (chat link, or a signed-in
  web session): signed proof of control, then the player's "Yes" in chat,
  then stored in `payment_wallets` under `<chain>/passkey`. Changing it
  also needs a fresh web sign-in and a 24 h cool-down. Details and threat
  model: §3.1.

### 3.1 Setup proof, chat confirmation and wallet changes

```
page: create passkey (prompt 1) → counterfactual address A
  POST /setup/challenge {A}            ← one-time EIP-191 text, 10 min, single use
page: check the text names A and this chain id, then
  smart.signMessage(text) (prompt 2)   ← Circle MSCA: ERC-1271 over a replay-safe
                                          hash; viem wraps it in ERC-6492 while A is
                                          not deployed
  POST /setup {A, credential_id, challenge_id, signature}
backend: challenge belongs to this profile + this link (or this session),
  is open, unexpired, same chain + chain id, same A → claim it (once) →
  eth_call(ERC-6492 universal validator init code ‖ abi(A, hash, sig)) == 0x01
  → request "pending_confirm" (30 min); the link is spent
every chat of the player (Telegram + WhatsApp, notify all_channels):
  "Is this your new wallet? 0xA…  [Yes, it's mine] [No]"
Yes (from a chat of THIS profile) → active: payment_wallets row inserted
No / no answer → declined / expired: nothing linked
```

**The challenge** (`proof.message_for`) is plain text, so the stored copy is
exactly what is verified:

```
boardman.playingsidequest.fun wants you to prove you own this wallet.

Link this wallet to my Boardman account.

Wallet: 0x…            (checksummed A)
Account: <profile id>
Chain ID: 5042002
Purpose: setup | change
Nonce: <128-bit hex>
Issued At / Expiration Time: <UTC>
```

It is stored with the profile, the SHA-256 of the setup link (or none for
a web session), the chain key and EVM chain id, and expires with the link
TTL (`SELF_CUSTODY_APPROVE_TTL_SEC`). A newer challenge supersedes older
unsigned ones; 20 per player per hour.

**Verification is in Python** (`self_custody/proof.py`,
`chain.Web3Reader.is_valid_signature`): one read-only `eth_call` with no
`to`, whose data is viem 2.57.7's `erc6492SignatureValidatorByteCode`
followed by `abi.encode(address, bytes32, bytes)` — exactly what viem's
`verifyMessage` sends. The validator deploys a counterfactual account from
the ERC-6492 factory data in the call's scratch state, then asks its
ERC-1271 `isValidSignature`; for a deployed account it asks directly. A
revert or `0x00` = invalid; a transport error = "try again" (the challenge
is spent, the link is not). Chosen over verifying in the Next BFF and
passing an attestation: one place decides, it is next to the store it
guards, and pytest covers it; nothing from the browser is trusted but the
signature. `frontend/lib/__tests__/setupProof.test.mjs` pins the bytecode,
the calldata and the EIP-191 hash to viem's; the Python tests assert the
same vectors.

**Refused** (tests in `tests/test_self_custody.py`): no/unknown challenge,
malformed or forged signature (link burned), a signature over another
challenge, a reused challenge (any outcome, including RPC failure), an
expired one, another profile's challenge or link, a session challenge used
with a link (and vice versa), another address than the challenge names, a
changed chain id, an address linked to another profile.

**In-chat confirmation** (`channels/core/flows/scw.py`, buttons
`v1|scw|y|<nonce>` / `v1|scw|n|<nonce>`): the nonce is 128 bits, only its
SHA-256 is stored, it expires (`SELF_CUSTODY_CONFIRM_TTL_SEC`, 30 min),
works once, and is accepted only from a chat whose principal is the
request's profile — a forwarded prompt tapped by anyone else is refused
("That request isn't yours"). Any of the player's chats may answer, so no
per-chat binding (unlike the lock approvals). A newer proven request
supersedes older waiting ones. If the prompt did not arrive (WhatsApp
outside the 24 h window has no `wallet_confirm` template), *wallet* in the
chat shows "Waiting for your confirmation" with **Confirm new wallet**
(fresh nonce; old buttons die) and **Cancel**.

**Changing a linked wallet** (lost passkey): the page offers it only to a
signed-in web session whose sign-in (`iat` of the session cookie, kept
across sliding renewals, sent as `X-Boardman-Auth-Iat`) is at most
`SELF_CUSTODY_REAUTH_SEC` (15 min) old; a chat link alone is not enough.
Then the same proof (`Purpose: change`), the same chat prompt (showing old
and new address) on all chats, and after *Yes* a cool-down of
`SELF_CUSTODY_CHANGE_COOLDOWN_SEC` (24 h): the old account stays the active
one (stakes, withdrawals, the escrow's player address), new naira top-ups
mint to the custodial play wallet instead of either passkey account
(`routing.deposit_account`), and every chat gets "Wallet change scheduled"
with **Cancel the change**. When the time has passed the next read swaps
`payment_wallets` in one transaction, only if the active address is still
the one the change was made against. Payouts follow the escrow's recorded
player, so the new account receives winnings only for matches it locked
itself after it became active.

**Threat model**

| Threat | Result |
|---|---|
| Setup link stolen / forwarded; attacker completes setup with *their* passkey | Valid proof for the attacker's address only; it waits in `pending_confirm`; the player's chat shows that address and the player taps No (or it expires). The attacker cannot answer from their own chat. Nothing is routed to it meanwhile. |
| Page or BFF submits an address the passkey does not control | Signature check fails on chain; link burned. |
| Replay of an old signature / challenge | Challenges are single use, expire in 10 min and name profile, link, chain and nonce. |
| Signature from another chain or a forked deployment | Chain id is in the text and the MSCA's replay-safe hash binds `block.chainid` and the account address; a changed chain id is refused before the RPC call. |
| Attacker holds the player's web session and wants to swap the wallet | Needs a sign-in < 15 min old, a passkey proof, the player's *Yes* in chat; then 24 h in which every chat can cancel and no new money reaches the new address. |
| Attacker holds the player's chat (SIM swap, unlocked phone) | **Residual.** For a player with no passkey wallet yet, they can link *their own* wallet (a first setup needs no web sign-in and no cool-down); later naira top-ups would mint to it. Every other chat of the player is told. A change of an existing wallet additionally needs the web sign-in and the 24 h window. Consider requiring the web sign-in for first setup too once most players have one. |
| RPC down or lying | Down: "try again", nothing linked. A lying RPC could accept a forged proof, but the player's chat Yes is still required. |
| Player taps Yes on someone else's address | Mitigated by copy ("only if it matches the page"), the full address in the prompt, and the page showing the same address. Residual social-engineering risk. |

### Flags

| Variable | Default | Effect |
|---|---|---|
| `SELF_CUSTODY_WALLETS_ENABLED` | `0` | Master switch: routes, setup, approve links |
| `SELF_CUSTODY_REQUIRED` | `0` | `1`: players without a passkey wallet get a setup link instead of the custodial lock |
| `SELF_CUSTODY_CHAIN` | settlement chain | `arc` (testnet) / `arc_mainnet` |
| `SELF_CUSTODY_SPONSOR_GAS` | `1` | `paymaster: true` (Gas Station) on UserOperations |
| `SELF_CUSTODY_APPROVE_TTL_SEC` | `600` | Approve/setup link and setup challenge lifetime |
| `SELF_CUSTODY_CONFIRM_TTL_SEC` | `1800` | How long a proven wallet waits for the chat "Yes" |
| `SELF_CUSTODY_CHANGE_COOLDOWN_SEC` | `86400` | A changed wallet is unused (old one active, top-ups to the play wallet) this long |
| `SELF_CUSTODY_REAUTH_SEC` | `900` | Max age of the web sign-in a wallet change needs |
| `SELF_CUSTODY_ESCROW_ADDRESS`, `SELF_CUSTODY_RPC_URL` | chains.yaml | Overrides for the chain read by the watcher |
| `SELF_CUSTODY_MODULAR_PATH` | `arcTestnet` / `arc` | Circle modular transport path (mainnet name **unverified**) |
| `BOARDMAN_ESCROW_VERSION` | on-chain probe | `2` → v2 `createMatch` with resolver permit; `1` → v1 call |
| `NEXT_PUBLIC_CIRCLE_CLIENT_KEY`, `NEXT_PUBLIC_CIRCLE_CLIENT_URL` | unset | Frontend; without them the page says "not available yet" |

Code: `src/backend/services/self_custody/` (config, store, calls, chain,
proof, wallets, setup, intents, routing, notices), `src/backend/api/self_custody.py`,
`src/channels/core/flows/{match,balance,scw}.py`, `src/channels/core/actions/withdraw.py`,
`src/channels/telegram/passkey.py`, `frontend/app/rematch/app/{wallet/setup,approve/[token]}`,
`frontend/app/api/rematch/app/{wallet/setup,wallet/setup/challenge,approve/[token]}`,
`frontend/lib/selfCustody/` (`proof.ts`, `setupBff.ts`).
Migrations: `supabase/migrations/20261018130000_self_custody_intents.sql`,
`supabase/migrations/20261018150000_self_custody_wallet_requests.sql`.
Tests: `tests/test_self_custody.py` (fake chain whose ERC-1271 answer is a
real ECDSA check, test resolver key, no network, no bundler) and
`frontend/lib/__tests__/{passkeyEnv,setupProof}.test.mjs`.

Support can still link an address by hand with `wallets.link_unverified`
(no proof, no chat step): only after an out-of-band check, never from a
player path.

Not built yet: the "Move my balance" button (§5), the naira cash-out
intent (§4.3), a passkey-recovery prompt, a chat notice when a changed
wallet becomes active (it happens on the first read after the cool-down;
the "scheduled" notice already gave the time), and WhatsApp templates for
`wallet_confirm` / `wallet_update` (outside the 24 h window those are
skipped on WhatsApp; the player finds the prompt under *wallet*).

## 4. Paycrest (naira) with self-custody

1. **On-ramp (built).** Unchanged up to Base: Paycrest pays USDC to the
   player's Boardman Base "in" wallet (developer-controlled **transit**, minutes);
   the CCTP mint on Arc now targets the player's **passkey account** when they
   have one (`paycrest.wallets.arc_destination`). CCTP's `mintRecipient` can
   be any address ([CCTP interfaces](https://developers.circle.com/cctp/references/contract-interfaces)).
2. **Refunds (built).** A cash-out refund bridged home mints to the same
   destination.
3. **Off-ramp (stubbed).** Needs the player to sign, on Arc,
   `[USDC.approve(TokenMessengerV2, x), depositForBurn(x, 6, mintRecipient =
   Boardman Base "out" transit wallet, …)]`; the existing reconciler then
   continues from the `burned` state. `calls.cctp_burn_calls()` builds the
   calls; wiring the intent into `paycrest/offramp.py` is **TODO**. Until then
   a passkey player asking for *Cash out to bank* is told to withdraw USDC to
   an exchange instead.
4. **Fully non-custodial naira (not built).** Paycrest delivering straight to
   the player's own Base smart account needs (a) the same counterfactual
   address on Base **(unverified)** or a second registration, (b) a Base
   UserOperation for the burn (Gas Station or Circle Paymaster on Base), and
   (c) a Paycrest `refundAddress` the player controls. Do this once (a) is
   confirmed with Circle.
5. Even with transit wallets, Boardman briefly holds naira-rail USDC. Counsel
   must know (go-live gate item 5 in `PAYCREST.md`).

## 5. Migration of existing custodial players (opt-in)

1. Flag on for a beta cohort (`SELF_CUSTODY_WALLETS_ENABLED=1`,
   `SELF_CUSTODY_REQUIRED=0`). Wallet menu offers **Set up a passkey wallet**.
2. After setup, *new* stakes and withdrawals use the passkey. Matches already
   locked custodially settle and refund to the custodial wallet (the escrow
   pays recorded players).
3. **Move my balance**: a one-time, player-initiated transfer from the
   Circle developer wallet to their passkey address. It is a normal
   withdrawal whose destination is pinned to their registered account
   (`withdrawals.perform_withdrawal`, existing checks, chat notice). **TODO:**
   the dedicated button; today the player can do it with the PIN withdraw
   page and their own address.
4. When ≥ 95 % of active balances moved: `SELF_CUSTODY_REQUIRED=1`; custodial
   wallets become receive-only (sweep remaining dust on request), then retire.
5. Nothing is moved without the player's action; nothing is deleted.

## 6. Founder steps

1. Circle Console → Keys → **Client Key** for `boardman.playingsidequest.fun`
   (and a separate one for a preview domain); set the passkey domain under
   Wallets → Modular Wallets → Passkey. Put the key in Vercel as
   `NEXT_PUBLIC_CIRCLE_CLIENT_KEY` (plus `NEXT_PUBLIC_CIRCLE_CLIENT_URL`).
2. Console → Gas Station → **policy for Arc** (testnet first): only the USDC
   contract and BoardmanEscrow as targets, per-op and monthly caps.
3. `npm i @circle-fin/modular-wallets-core viem` in `frontend/` and commit
   `package.json` + `package-lock.json` (not done here: no registry access).
   Until then `next.config.js` aliases both to `lib/selfCustody/sdkMissing.ts`
   so the build passes and the pages say "not available yet";
   `frontend/types/circle-modular-wallets.d.ts` is a fallback type shim
   (real types win once installed) — re-run `tsc` after installing, the
   adapter (`lib/selfCustody/wallet.ts`) was typed against the shim.
4. Deploy BoardmanEscrow **v2** (audited) on Arc mainnet; set
   `BOARDMAN_ESCROW_VERSION=2` and the resolver key (keystore) for permits.
5. Device test matrix on testnet: iOS Safari, Android Chrome, Telegram iOS /
   Android / Desktop, WhatsApp iOS / Android (open link → "Open in browser" →
   create passkey → sign the setup proof → "Yes" in chat → lock → back to
   chat). Also confirm on Arc testnet that a real counterfactual account's
   signature passes `proof.verify` (only exercised against viem's bytes and
   a fake chain here). Record results here.
6. Recovery: decide whether to prompt every player to save a recovery phrase
   (Circle recovery module) after their first deposit.

## 7. Open risks

* **Webview passkeys** (above): if "Open in browser" proves too much friction,
  fall back to Circle user-controlled wallets (PIN) for those clients.
* **Recovery**: a player who loses every synced passkey and skipped the
  recovery phrase loses the wallet. Boardman cannot help — by design.
* **Wallet linking** (§3.1): proven at setup with an ERC-1271/ERC-6492
  signature over a one-time challenge and confirmed by the player in chat;
  a stolen setup link alone links nothing. Residual: whoever controls the
  player's chat can link their own wallet as a *first* wallet; changes need
  a fresh web sign-in and wait 24 h. Two passkey prompts at setup (create,
  then sign) are untested on the device matrix (§6.5).
* **Circle dependency**: the bundler, passkey RP service and smart-account
  implementation are Circle's; an outage blocks locks and withdrawals (funds
  stay safe and are reachable through any ERC-4337 tooling with the passkey).
* **Gas Station cost/abuse**: sponsored ops are Boardman's bill; the policy
  must whitelist targets and cap spend.
* **Legal**: non-custody removes the *custodial wallet* question from the
  go-live gate; it does **not** answer whether skill-staking needs a gaming
  licence, nor the naira-rail transit custody (§4.5). Counsel sign-off is
  still required before real money.
