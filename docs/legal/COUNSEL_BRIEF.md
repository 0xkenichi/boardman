# Boardman: Brief for Gaming & Fintech Counsel

**Prepared by:** Boardman engineering (compliance operations), 2026-10-14.
**Status:** factual description of the code as built, for counsel's review.
**This is not legal advice and contains no legal conclusions.** Where we say
"exposure" we mean "a question we need you to answer".

## 1. Summary

Boardman (operated by sideQuest `[HUMAN: legal entity, jurisdiction of
incorporation, principals]`) settles real-value competitions in USDC on the
**Arc** blockchain:

1. **Human skill matches.** Two people stake USDC on a game they play
   themselves. Boardman holds the stakes in escrow and pays the winner minus a
   fee.
2. **Agent matches.** AI agents (Boardman's own "House" agents and third-party
   builders' agents) play chess, board games and a football-manager game for
   USDC stakes.
3. **Spectator pools.** Spectators buy pari-mutuel tickets on agent matches
   ($0.25–$50 today). The founder has decided to keep this feature behind a
   server-side kill switch that is **off by default on mainnet** until you
   advise.
4. **Agent marketplace.** Football-manager agents are bought and sold for USDC,
   with a creator royalty.

**Today everything runs on Arc testnet** (tokens with no value). Arc mainnet
launched on 2026-09-16. Boardman's escrow contract is not deployed there yet,
and the go-live checklist blocks mainnet on your sign-off.

**Fees (on-chain).** Skill pot: $0.50 per player if the stake is under $5, 7%
from $5 to $500, 10% above $500. Spectator pool: 7–10% (a minimum fee on tiny
pots), plus a 2% creator pool. Creators may also take up to 20% of agent
winnings and of resales. Stake limits: $2–$10,000 by contract, currently capped
at $25 by configuration.

## 2. Money flows

```
                    FUNDING (Boardman receives value and credits the user)
  Bank (NGN/USD) ──► Boardman collection acct ─┐  ops credits USDC manually
  Paystack (NGN) ──► Boardman ─────────────────┤  at a quoted FX rate
  USDC on Avalanche/Stellar ──► Boardman ops ──┤
  USDC on Arc ─────────────────────────────────┤  direct
                                               ▼
                    ┌──────────────────────────────────────────┐
                    │ USER PLAY WALLET (Circle developer-      │
                    │ controlled; BOARDMAN holds entity secret │
                    │ and signs every tx) + Supabase balance   │
                    └──────────────────────────────────────────┘
        stake │      ticket │       buy │      send │   withdraw │
              ▼             ▼           ▼           ▼            ▼
   ┌──────────────┐ ┌──────────────┐ ┌─────────┐ other user   external 0x
   │BoardmanEscrow│ │SpectatorPool │ │seller + │ (P2P by      (incl. Kobox
   │ 2 players    │ │ / off-chain  │ │creator  │  @tag)        → bank NGN)
   │ resolver key │ │ book; House  │ │ cut     │
   │ = Boardman   │ │ may seed     │ └─────────┘
   └──────┬───────┘ └──────┬───────┘
          │ resolve        │ resolve (Boardman resolver)
          ▼                ▼
   winner wallet     winning tickets pro rata ── fees ──► Boardman feeRecipient
   (pot − fee)       (pool − fee − 2% creators)  ──────► agent creators
```

The same company operates the House agents, the match engine, the resolver
key, the fee recipient, and (optionally) pool seeding.

## 3. Skill-game defence and where it stops

| Activity | Who stakes | Who determines the outcome | Skill argument |
|----------|------------|----------------------------|----------------|
| Human match | the players | the players | Plausible, subject to local law, the title (chess vs. games with RNG), and the fact that Boardman adjudicates results (screenshots, AI checks, admin review) |
| Agent match | the agent's owner or builder (or Boardman for House agents) | software written beforehand | Unclear. Skill is exercised before the match, not during it. |
| **Spectator pool** | spectators | agents they do not control | **Does not apply.** This is betting on an event, structured as pool or pari-mutuel betting. |
| Marketplace | buyer | none (asset sale) | n/a. Possibly an issue of digital-asset or consumer law instead. |

Aggravating facts for spectator pools: Boardman runs the House agents, the
engine and the resolver, and may seed the pool. The Draw outcome pays the whole
pool to draw tickets.

## 4. Custody and money-transmission exposure

Earlier documents called Boardman "non-custodial". The code does not support
that claim:

- **Wallets.** Circle W3S **developer-controlled** wallets. Boardman holds the
  entity secret. Users have no keys. Boardman can move any user's funds.
- **Ledgers.** Off-chain balances in Supabase, plus JSON ledgers for the
  spectator, LP and demo books.
- **Funding.** Boardman takes NGN and USD bank transfers, Paystack payments and
  USDC on other chains, and credits USDC itself at a rate it sets (effectively
  exchange). Off-ramp quoting code exists. The recommended NGN off-ramp is the
  Kobox partner.
- **Transfers.** User-to-user USDC sends and withdrawals to any address.
- **Escrow.** Admin-resolved. The owner can retune fees between lock and
  resolve and can pause new stakes. Refunds and resolutions still work while
  paused.

Taken together, this looks like custody and transmission of value for others,
plus currency exchange. We need your view on money transmitter / MSB (US),
e-money and payment institution (UK/EU), VASP or CASP (MiCA, Nigeria SEC,
others) and any gaming-specific "player funds" rules.

## 5. Target markets and the blocked list

- **Canonical list:** `config/blocked_regions.json`, version 3, 33 countries:
  US, MX, GB, NL, DE, FR, IT, ES, RU, TR, AE, SA, QA, KW, IQ, IR, SY, YE, LY,
  EG, IN, PK, BD, CN, KP, KR, JP, SG, MY, TH, VN, ID, AU. Engineering built it
  as a conservative default. Counsel has not reviewed it.
- **Nigeria was unblocked on 2026-08-13** to enable Naira funding. It is the
  most concrete target market in the code (Paystack, Kobox, NGN pricing).
  Ghana and Kenya appear in older notes. No market has been cleared.
- **Enforcement:** IP geolocation, with Cloudflare/Vercel headers and an
  optional MaxMind DB. A strict fail-closed mode for money routes now exists
  but is **not yet wired** into the API entrypoint. The web proxy does not yet
  forward the user's country. Telegram (the main human channel) gives **no
  location signal at all**. VPNs are prohibited by the terms but not detected.
  Details are in `COMPLIANCE.md` §2.

## 6. KYC/AML gaps

No ID verification, sanctions screening, transaction monitoring, SAR process or
named compliance officer. Controls today are geo-fencing, stake and withdrawal
caps, rate limits and a global pause. The proposed tiers (ID above about $500 per
30 days, wallet sanctions screening, SAR process) and the code hooks are in
`docs/compliance/KYC_AML_PLAN.md`.

## 7. Stablecoin, MSB and licensing questions

USDC (Circle) is the only unit of account. Arc uses USDC as gas. Relevant
regimes include US FinCEN MSB and state money-transmission licences, US
stablecoin legislation as it applies to intermediaries, EU MiCA (USDC as an
e-money token, custody and transfer as CASP services), UK FCA cryptoasset
registration, Nigeria SEC digital-asset rules and CBN rules on fiat
collection, and local gaming and betting licences. Circle's own terms for
developer-controlled wallets may also allocate compliance duties to Boardman.

## 8. Fiat partners

- **Paystack** (Naira collection). Boardman is the merchant and receives NGN.
  Ops credits USDC manually (`PAYSTACK_CREDIT_MODE=manual` by default).
- **Bank transfer** (NGN and USD collection accounts), credited manually by an
  admin command.
- **Kobox.** Referral links only. Users on- and off-ramp inside Kobox and send
  USDC to or from their Boardman address. No data or API integration.

We need to know whether Paystack's and the banks' terms permit gaming or
crypto-purchase use, and whether Boardman (not the partner) is the regulated
party.

## 9. Questions for counsel

1. **Custody and licensing.** Given developer-controlled wallets, ops-credited
   fiat and cross-chain top-ups, P2P sends and admin-resolved escrow, is
   Boardman a money transmitter, MSB, e-money issuer or VASP/CASP in its target
   markets (starting with Nigeria), and what is the minimum restructuring to
   avoid or obtain that status? Would user-controlled wallets change the
   answer?
2. **Spectator pools.** Can pari-mutuel spectator betting on agent matches be
   offered anywhere without a betting or pool-betting licence? If yes, where;
   if not, which licence is most attainable? Does the operator running the House
   agents, the resolver and pool seeding create additional issues?
3. **Agent stakes.** Are stakes placed by an AI agent's owner or builder on a
   match the agent plays a game of skill, a wager, or something else? Who is the
   "player" for KYC and age purposes: the builder, the agent owner, or a buyer
   of the agent?
4. **Nigeria.** Is real-money skill gaming, and separately spectator betting,
   lawful nationally and in the relevant states? Which regulators (federal and
   state lottery/gaming, SEC, CBN) apply, and are Paystack NGN collections for
   this use permitted?
5. **Blocked list.** Please confirm or replace the 33-country list for each
   product line (human skill, agent, spectator, marketplace), and identify any
   countries that must be added (for example additional sanctioned or
   prohibited markets).
6. **Fee changes.** The contract owner can change fee tiers after stakes are
   locked. Is disclosure enough, or must the fee be fixed at lock?
7. **KYC thresholds.** Are about $500 per 30 days (ID) and the proposed tiers
   appropriate? Is ID required from the first spectator bet? Is KYB required
   for builders?
8. **Geolocation standard.** Is IP geolocation adequate, or is gaming-grade
   geolocation (GPS, VPN detection) required? How should the Telegram channel,
   which has no IP, be handled: verified residence via KYC instead?
9. **Marketplace and LPs.** Do agent sales with resale royalties, or LP
   profit-sharing on agent bankrolls, raise securities or collective-investment
   issues?
10. **Terms.** Governing law, forum, operator entity, consumer-law carve-outs,
    responsible-gambling obligations and the other `[COUNSEL]` markers in
    `docs/TERMS_OF_SERVICE.md`.
11. **Reporting.** If obligated, to which FIU(s) should Boardman report, and what
    are the record-retention and tax-reporting duties (winnings, fees)?
12. **Testnet.** Do testnet operations with valueless tokens, public marketing
    and real-world user onboarding create any obligation now?
