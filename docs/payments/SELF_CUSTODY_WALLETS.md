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
* **Wallet setup** `/app/wallet/setup?t=<token>` (chat link, or a signed-in
  web session): register passkey → counterfactual address → POST
  `{address, credential_id}` → stored once in `payment_wallets` under
  `<chain>/passkey` (an existing address always wins: never silently
  replaced). The player is told in chat which address was linked.
  Ownership is *proven* by the first confirmed on-chain action from that
  account; until then it only receives deposits.

### Flags

| Variable | Default | Effect |
|---|---|---|
| `SELF_CUSTODY_WALLETS_ENABLED` | `0` | Master switch: routes, setup, approve links |
| `SELF_CUSTODY_REQUIRED` | `0` | `1`: players without a passkey wallet get a setup link instead of the custodial lock |
| `SELF_CUSTODY_CHAIN` | settlement chain | `arc` (testnet) / `arc_mainnet` |
| `SELF_CUSTODY_SPONSOR_GAS` | `1` | `paymaster: true` (Gas Station) on UserOperations |
| `SELF_CUSTODY_APPROVE_TTL_SEC` | `600` | Approve/setup link lifetime |
| `NEXT_PUBLIC_CIRCLE_CLIENT_KEY`, `NEXT_PUBLIC_CIRCLE_CLIENT_URL` | unset | Frontend; without them the page says "not available yet" |

Code: `src/backend/services/self_custody/`, `src/backend/api/self_custody.py`,
`frontend/app/rematch/app/{wallet/setup,approve/[token]}`,
`frontend/lib/selfCustody/`. Tests: `tests/test_self_custody.py` (fake
chain, fake permit key; no network).

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
3. `npm i @circle-fin/modular-wallets-core viem` in `frontend/` (pinned in
   `package.json`; delete `frontend/types/circle-modular-wallets.d.ts` after
   install so the real types apply).
4. Deploy BoardmanEscrow **v2** (audited) on Arc mainnet; set
   `BOARDMAN_ESCROW_VERSION=2` and the resolver key (keystore) for permits.
5. Device test matrix on testnet: iOS Safari, Android Chrome, Telegram iOS /
   Android / Desktop, WhatsApp iOS / Android (open link → "Open in browser" →
   passkey → lock → back to chat). Record results here.
6. Recovery: decide whether to prompt every player to save a recovery phrase
   (Circle recovery module) after their first deposit.

## 7. Open risks

* **Webview passkeys** (above): if "Open in browser" proves too much friction,
  fall back to Circle user-controlled wallets (PIN) for those clients.
* **Recovery**: a player who loses every synced passkey and skipped the
  recovery phrase loses the wallet. Boardman cannot help — by design.
* **Ownership of the registered address** is only proven by the first
  on-chain action; a stolen setup link could register an attacker's address
  for deposits. Mitigations: single-use 10-minute links, chat notice on
  registration, address never replaced silently, stakes/payouts bound to the
  on-chain player. TODO: verify an ERC-1271/ERC-6492 signature at setup.
* **Circle dependency**: the bundler, passkey RP service and smart-account
  implementation are Circle's; an outage blocks locks and withdrawals (funds
  stay safe and are reachable through any ERC-4337 tooling with the passkey).
* **Gas Station cost/abuse**: sponsored ops are Boardman's bill; the policy
  must whitelist targets and cap spend.
* **Legal**: non-custody removes the *custodial wallet* question from the
  go-live gate; it does **not** answer whether skill-staking needs a gaming
  licence, nor the naira-rail transit custody (§4.5). Counsel sign-off is
  still required before real money.
