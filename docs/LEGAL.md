# Boardman — Legal & Compliance Notes

> ⚠️ **NOT LEGAL ADVICE.** This is an internal working draft written by
> engineers. It does not replace advice from qualified gaming, fintech or
> local counsel. A lawyer must review it before Boardman accepts real money or
> launches publicly. The questions for counsel are in
> [`legal/COUNSEL_BRIEF.md`](legal/COUNSEL_BRIEF.md). The operational facts
> (blocked list, geo-fence, custody, fees) are kept in
> [`../COMPLIANCE.md`](../COMPLIANCE.md), and this file defers to it.

## What Boardman actually does (October 2026)

- **Human skill matches.** Two players stake USDC on a game they play
  themselves (chess, FC Mobile, EA FC and similar), through the Telegram bot,
  the website or the Stack API. Results come from player score reports and
  screenshot proofs, with AI-assisted checks and admin dispute resolution.
- **Agent matches.** Autonomous AI agents (Boardman's own House agents and
  third-party builder agents that connect over a move webhook) play chess and
  other board games, plus an agentic football-manager league, for USDC stakes.
- **Spectator betting.** Spectators bet pari-mutuel on agent matches ($0.25–$50
  tickets, with draw tickets available). LPs can seed pools and agents' creators
  take a cut. This sits behind a planned kill switch that is off on mainnet
  until counsel signs off (see `../COMPLIANCE.md` §5).
- **Marketplace.** AFM manager agents can be bought and sold for USDC, with a
  creator cut paid on resale.
- **Settlement rail.** Arc (testnet today; Arc mainnet is live but Boardman's
  escrow is not deployed there yet). Stakes lock in the `BoardmanEscrow`
  contract. A Boardman-held resolver key pays the winner or cancels and
  refunds.
- **Fees.** Tiered and charged on-chain: $0.50 per player when the per-player
  stake is under $5, 7% of the pot from $5 to $500, and 10% above $500. Spectator
  pools have their own tiers plus a 2% creator pool. Full table in
  `../COMPLIANCE.md` §4.
- **Wallets.** Circle developer-controlled wallets. Boardman holds the entity
  secret and signs for users.

## Custody: why "non-custodial" was wrong

Earlier drafts said Boardman "never takes custody" because stakes sit in a
smart contract. That is not accurate:

- Boardman controls the user wallets (developer-controlled, company-held
  entity secret).
- Boardman keeps off-chain balances (Supabase play balance, spectator and LP
  ledgers).
- Boardman receives funds on funding rails (Avalanche/Stellar ops addresses,
  Naira collections) and credits users itself.
- Boardman's resolver key decides who the escrow pays.

Regulators generally look at substance over architecture. Treat Boardman as
**custodial**, and as a platform that holds and moves value for others, when
assessing money transmission, e-money, VASP and gaming licences.

Even apart from custody, a platform that builds the challenge flow, sets stake
limits, adjudicates outcomes and takes a percentage of the pot may be treated
as an **operator** of real-money gaming in many jurisdictions.

## Skill vs. chance

Skill-based contests get more favourable treatment than games of chance in
many jurisdictions, but the line is not drawn the same way everywhere. Game
mechanics (matchmaking, RNG) can still be argued.

The skill defence only arguably applies where **the person staking is the
person playing**:

- **Human skill matches.** The defence is plausible, subject to local law.
- **Agent matches, staked by the agent's owner or builder.** Unclear. The
  "skill" is the owner's engineering, exercised before the match, not during
  it. Counsel question.
- **Spectator pari-mutuel bets on agent matches.** The defence does **not**
  apply. The bettor has no influence on the outcome. This is wagering on an
  event and is likely to be regulated as betting or pool betting. It is the
  reason for the kill switch.

**Do not rely solely on the skill-game argument.**

## Blocked jurisdictions

The canonical list is **`config/blocked_regions.json`** (version 3, 33
countries), enforced by the geo-fence. The current list and the change process
are in [`../COMPLIANCE.md`](../COMPLIANCE.md) §1. In short: US, MX, GB, NL,
DE, FR, IT, ES, RU, TR, AE, SA, QA, KW, IQ, IR, SY, YE, LY, EG, IN, PK, BD,
CN, KP, KR, JP, SG, MY, TH, VN, ID and AU.

**Rationale (engineering's reasons, not counsel's):**

- **United States.** A 50-state patchwork. Some states have fantasy or skill
  exemptions, but compliance is expensive. There is also federal money-
  transmission and UIGEA exposure.
- **India.** PROGA 2025 broadly bans real-money online gaming (pending court
  challenge and full notification).
- **China, Russia, much of the Middle East, North Korea, Syria, Yemen.** Strict
  or outright prohibitions, and in several cases sanctions.
- **UK and EU members listed.** Local gambling or gaming licences are generally
  required for real-money services.
- **Australia, Singapore, Thailand, Vietnam, Japan, South Korea, Malaysia,
  Indonesia.** Restrictive or licensing-heavy regimes.

**Nigeria is not blocked.** It was removed on 2026-08-13 so that Naira funding
(Paystack, Kobox) could be used. Nigeria has federal and state-level lottery
and gaming regulators, and its crypto/VASP regime (SEC Nigeria, CBN) is still
changing. **Nigeria needs specific local counsel review before mainnet. It is
not a "safer" market by default.**

## Candidate markets (not cleared)

No market has been cleared by counsel. The product targets jurisdictions where
peer-to-peer skill competitions may be tolerated. Each one needs local review
of gaming law, of money-transmission/VASP law (because of custody), and of
betting law (if spectator betting is enabled there). Engineering has no
evidence for which markets those are, and earlier lists in this file were
guesses. They have been removed.

## Required user-facing disclaimers

Before a user can create or accept a challenge, or place a spectator bet, they
should explicitly confirm (final wording by counsel):

1. **Jurisdiction:** "I am not located in, and not using a VPN to appear outside,
   a restricted jurisdiction."
2. **Legal compliance:** "My participation complies with the laws that apply to
   me."
3. **Nature of the product:** human skill match, agent match, or spectator bet,
   each described accurately. Do **not** call spectator betting a skill
   competition.
4. **Risk:** "I may lose my entire stake or bet."
5. **Age:** "I am at least 18 years old, or the legal age where I live if
   higher."
6. **Custody:** "Boardman controls my play wallet on my behalf."

## KYC/AML

There is none today. The proposed thresholds (an ID check above about $500 per
rolling 30 days, sanctions screening on every deposit and withdrawal address,
and a SAR process) and the code hooks are in
[`compliance/KYC_AML_PLAN.md`](compliance/KYC_AML_PLAN.md).

## Housekeeping before mainnet

These are tracked with checkboxes in
[`MAINNET_GOLIVE_CHECKLIST.md`](MAINNET_GOLIVE_CHECKLIST.md) §4:

- Counsel review of the Terms of Service, Privacy Policy and the counsel brief.
- Smart contract audit of `BoardmanEscrow.sol` and `SpectatorPool.sol`.
- Resolver and owner key custody (hardware signer, MPC or multisig).
- Incident response plan for disputes, hacks and contract bugs.
- Tax reporting obligations in operating and target jurisdictions.
- Stablecoin, MSB and VASP licensing analysis per country.
- Insurance or a capital reserve for operational risk.

## Useful references

- India PROGA 2025: broad real-money gaming ban (under legal challenge)
- US UIGEA 2006: federal payment prohibition, with state-by-state regulation
- FinCEN guidance on convertible virtual currency (2019): custodial wallets and
  money transmission
- EU MiCA: crypto-asset service providers and e-money tokens (USDC)
- UK Gambling Commission: crypto gambling guidance
- Netherlands Kansspelautoriteit: strict enforcement against unlicensed
  operators

## Draft Terms of Service

See [`TERMS_OF_SERVICE.md`](TERMS_OF_SERVICE.md).
