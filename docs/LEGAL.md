# ClawStation — Legal & Compliance Notes

> ⚠️ **NOT LEGAL ADVICE.** This document is a working draft for internal planning
> only. It is not a substitute for advice from a qualified gaming, fintech, or
> international counsel. You must have a lawyer review this before accepting
> real money or launching publicly.

## What ClawStation actually does

- Peer-to-peer skill-based gaming competitions.
- USDC stakes are held by the **ClawEscrow smart contract** on Base — sideQuest
  never takes custody of player funds.
- A 7% platform fee is deducted from the winning pot.
- Outcomes are verified by player-submitted scores + optional AI screenshot
  verification.
- An admin resolver can call `resolveMatch`, `flagDispute`, or `cancelMatch` on
  the contract.

## Why non-custodial helps (but is not enough)

Non-custodial escrow reduces **custodian / money-transmitter** exposure because
sideQuest does not hold user funds. However, courts and regulators generally
look at the **substance** of the activity, not just the technical architecture.

A platform that:
- builds the challenge flow,
- sets stake sizes,
- adjudicates outcomes,
- takes a percentage of the pot,
- and facilitates real-money matches between users

may still be treated as an **operator / facilitator / marketplace** in some
jurisdictions, regardless of whether settlement happens on-chain.

## Skill vs. chance

Skill-based games are treated more favorably than games of chance in many
jurisdictions, but the distinction is not universal. EA FC / EA Sports FC is
predominantly skill-based, but game mechanics (matchmaking, RNG elements) can
still be argued by regulators.

**Do not rely solely on the "skill game" argument.** It is one factor among
many.

## High-risk jurisdictions — currently blocked

The following countries are blocked by the geo-fence (`gaming/config/blocked_regions.json`):

AU, BD, CN, EG, FR, DE, IN, ID, IR, IQ, IT, JP, KW, LY, MY, MX, NL, KP,
PK, QA, RU, SA, SG, KR, ES, SY, TH, TR, AE, GB, US, VN, YE

**Rationale:**
- **United States:** 50-state patchwork; fantasy/skill exemptions exist in some
  states but compliance is expensive and risky without counsel.
- **India:** PROGA 2025 imposes a broad ban on real-money online gaming
  (pending Supreme Court challenge and full notification).
- **China, Russia, Middle East, North Korea, Syria, Yemen:** strict or outright
  prohibitions on gambling/wagering.
- **EU (UK, Netherlands, Germany, France, Italy, Spain):** generally require
  local gambling or gaming licenses for real-money services.
- **Australia, Singapore, Thailand, Vietnam, Japan, South Korea:** restrictive
  or licensing-heavy regimes.

## Safer initial markets (still not zero risk)

Jurisdictions where skill-based P2P competitions may be more tolerated, subject
to local counsel confirmation:

- Most of Latin America outside Mexico (e.g., Brazil, Argentina, Colombia —
  check locally)
- Parts of Africa (e.g., Kenya, Ghana, Nigeria — evolving regulation)
- Parts of Eastern Europe and Southeast Asia not listed above
- Caribbean / certain offshore-friendly jurisdictions

**This list is provisional.** Laws change.

## Required user-facing disclaimers

Before any user can create or accept a challenge, they must explicitly agree to:

1. **Jurisdiction confirmation:** "I am not located in a prohibited
   jurisdiction."
2. **Legal compliance:** "My participation complies with all applicable local
   laws."
3. **Skill-based nature:** "I understand this is a peer-to-peer skill
   competition, not a gambling service operated by sideQuest."
4. **Risk disclosure:** "I may lose my entire stake. Only wager what I can
   afford to lose."
5. **Age confirmation:** "I am at least 18 years old (or the legal age in my
   jurisdiction)."
6. **No operator warranty:** "sideQuest provides technology only and does not
   guarantee outcomes, payouts, or uninterrupted service."

## Recommended KYC/AML thresholds (before mainnet)

- Identity verification for cumulative stakes above a conservative threshold
  (e.g., $500 USD equivalent per 30 days).
- Source-of-funds checks for large or suspicious activity.
- Sanctions screening (OFAC, UN, EU lists).
- Suspicious activity reporting process.

## Housekeeping before mainnet

- [ ] Lawyer review of Terms of Service, Privacy Policy, and Cookie Policy.
- [ ] Smart contract audit of ClawEscrow.sol.
- [ ] Resolver key custody plan (hardware signer / MPC / multi-sig).
- [ ] Incident response plan for disputes, hacks, and contract bugs.
- [ ] Tax reporting obligations in operating and target jurisdictions.
- [ ] Stablecoin / MSB licensing analysis per country.
- [ ] Insurance or capital reserve for operational risks.

## Useful references

- India PROGA 2025 — broad real-money gaming ban (under legal challenge)
- US UIGEA 2006 — federal payment prohibition; state-by-state regulation
- EU Gambling Directive and national licensing regimes
- UK Gambling Commission — crypto gambling guidance
- Netherlands Kansspelautoriteit — strict unlicensed enforcement

## Draft Terms of Service

See `gaming/docs/TERMS_OF_SERVICE.md` for a starting template.
