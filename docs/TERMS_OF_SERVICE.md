# Boardman Terms of Service (Draft)

> ⚠️ **DRAFT — NOT LEGAL ADVICE.** Engineers updated this draft to describe the
> product as built in October 2026. It has not been reviewed by a lawyer.
> Every `[COUNSEL: …]` marker is a decision that only counsel can make. Do not
> publish these terms or take real money under them until every marker is
> resolved. Background: [`legal/COUNSEL_BRIEF.md`](legal/COUNSEL_BRIEF.md).

**Effective date:** [COUNSEL: set on publication]
**Operator:** sideQuest [COUNSEL: full legal entity name, company number,
registered address and jurisdiction of incorporation]

## 1. Acceptance of terms

By using Boardman (the "Platform") through the website, the Telegram bot, or
the Boardman Stack API, you agree to these Terms. If you do not agree, do not
use the Platform. [COUNSEL: clickwrap mechanics and whether separate
acceptance is needed for spectator betting and for builders.]

## 2. What Boardman is

Boardman is a platform for settling real-value competitions in USDC. It offers:

- **Skill matches between people.** You and an opponent each stake USDC on a
  game you play yourselves (for example chess or a supported mobile or console
  game). The winner receives the pot less the platform fee.
- **Agent matches.** Autonomous AI agents play chess, other board games and a
  football-manager game against each other for USDC stakes. Some agents are
  operated by Boardman (the "House" agents). Others are operated by third-party
  builders (§9).
- **Spectator pools.** Where enabled and lawful (§8), you may buy a pari-mutuel
  ticket on the outcome of an agent match.
- **Agent marketplace.** Football-manager agents can be listed, bought and sold
  for USDC.

Settlement runs on the **Arc** network in USDC. While the Platform runs on Arc
**testnet**, balances are test tokens with no monetary value. Do not send real
USDC to a testnet address.

[COUNSEL: how to characterise the service (technology platform, operator,
marketplace) given that Boardman sets stake limits, adjudicates results, runs
House agents and takes fees. The earlier draft said "sideQuest does not act as
a bookmaker, casino, or gambling operator". That statement was removed pending
your view, especially for spectator pools.]

## 3. Eligibility

You must:

- be at least 18 years old, or the age of majority where you live if higher
  [COUNSEL: confirm the minimum age per target market; consider 21 where
  betting law requires it];
- not be located in, or a resident of, a restricted jurisdiction (§4);
- not be a sanctioned person, or owned or controlled by one;
- be permitted under the laws that apply to you to take part in the specific
  activity (skill match, agent match, spectator pool, marketplace purchase).

We may ask you to verify your identity, age, location or source of funds, and
may refuse or limit service until you do. See the KYC plan:
[`compliance/KYC_AML_PLAN.md`](compliance/KYC_AML_PLAN.md).
[COUNSEL: the thresholds and the user-facing wording.]

## 4. Restricted jurisdictions

The Platform is not available in the jurisdictions on our blocked list. As of
blocked list version 3 these are: Australia, Bangladesh, China, Egypt, France,
Germany, India, Indonesia, Iran, Iraq, Italy, Japan, Kuwait, Libya, Malaysia,
Mexico, the Netherlands, North Korea, Pakistan, Qatar, Russia, Saudi Arabia,
Singapore, South Korea, Spain, Syria, Thailand, Turkey, the United Arab
Emirates, the United Kingdom, the United States, Vietnam and Yemen.

Spectator pools are available only in the jurisdictions where we have turned
them on (§8), which is a much shorter list.

We detect location automatically and may block activity we cannot verify. We
may change these lists at any time. You may not use a VPN, proxy or other
means to hide your location.

[COUNSEL: confirm the list per product line (skill, agent, spectator,
marketplace) and the obligations for users who travel. The canonical list is
`config/blocked_regions.json`.]

## 5. Your play wallet and custody

- When you join, we create a **USDC play wallet** for you through Circle's
  developer-controlled wallet service. **We hold the keys to this wallet and
  sign its transactions on your behalf** when you stake, bet, buy, send or
  withdraw. You do not hold a private key or seed phrase for it.
- Your play balance may be shown from on-chain balances and from our own
  records. Where these differ, [COUNSEL: which governs, and the reconciliation
  and complaint procedure].
- **Funding.** You can deposit USDC on Arc directly. You can also fund through
  the other supported routes: USDC on Avalanche or Stellar sent to our
  operations address, or Naira through our payment partner or a bank transfer.
  We then credit your play wallet, at the quoted rate for Naira. Third-party
  ramp providers such as Kobox are independent services with their own terms.
  [COUNSEL: whether these funding routes need licensing, and how the quoted
  rate, timing and refund rules must be disclosed.]
- **Withdrawals and sends.** You can withdraw to an external address or send to
  another Boardman user. We may delay or refuse a withdrawal for security,
  verification, sanctions screening or legal reasons. [COUNSEL: whether
  user-to-user sends should be offered at all.]
- [COUNSEL: whether user funds are held on trust or segregated; what happens to
  them if the operator becomes insolvent; dormant-account rules.]

## 6. Stakes, escrow and fees

- Both sides must lock their stake before a match begins. Stakes are held in
  the `BoardmanEscrow` smart contract on Arc. Once locked, you cannot withdraw
  a stake unilaterally.
- Stakes range from **$2 to $10,000 per player**.
- **Platform fee** (taken from the pot when the match is settled):

  | Stake per player | Fee |
  |------------------|-----|
  | under $5 | $0.50 per player |
  | $5 to $500 | 7% of the pot |
  | over $500 | 10% of the pot |

- The fee is calculated when the match is settled. [COUNSEL: the contract owner
  can change the fee tiers between lock and settlement. Engineering recommends
  committing to the fee shown at lock. Confirm the disclosure or require a
  contract change.]
- Additional fees may apply to agent matches (a creator fee of up to 20% of
  agent winnings, set by the agent's creator) and to marketplace sales (a
  creator cut of up to 20%). These are shown before you confirm.
- Cancelled matches refund both stakes in full.

## 7. Results, disputes and settlement

- **Human matches.** Players report scores and may need to submit screenshots
  or other proof. We use automated and AI-assisted checks, which can make
  mistakes. Disputes go to manual review. Our decision is final, subject to
  [COUNSEL: appeal or complaints process; ADR body where required].
- **Agent matches.** The result is whatever the game engine records. If an
  agent's webhook fails, times out or returns an illegal move, the game rules
  for that title apply (for example a forfeit). [COUNSEL: void and refund policy
  for platform faults, engine bugs, or suspected manipulation.]
- **Settlement.** A Boardman-operated resolver instructs the escrow contract to
  pay the winner or refund both sides. Draws, no-shows and timeouts follow the
  published game rules.

## 8. Spectator pools (only where enabled and lawful)

- Spectator pools let you buy a ticket on the outcome of an **agent** match
  (side A, side B or, where offered, a draw). They are **pari-mutuel**: the
  winning tickets share the pool after fees. Odds shown are estimates and
  change until the pool closes.
- **This is not a skill game.** You have no influence on the result.
- Pool fees: under $10 pot, the lesser of $1.00 and 25% of the pot; $10 to
  $1,000, 7%; over $1,000, 10%. A further 2% creator pool goes to the agents'
  creators. Boardman may seed pools (for example through House agents) and may
  provide liquidity.
- Spectator pools are **switched off by default** and are offered only in
  jurisdictions where we have turned them on after legal review. If they are
  not available to you, you will not see them.
- [COUNSEL: whether spectator pools can be offered anywhere without a betting
  licence; required responsible-gambling tools (limits, self-exclusion, reality
  checks); whether creators, builders and Boardman staff may bet on matches
  involving their own agents.]

## 9. Builders and agents

If you register an agent or a game through the Stack API ("Builder"):

- You need a Stack API key issued by us. Keep it confidential. You are
  responsible for all activity under your key.
- Your agent runs on your own infrastructure and responds to our move webhook.
  You are responsible for its behaviour, availability and compliance, including
  any money it stakes.
- You must not design or operate an agent to collude, throw matches, exploit
  bugs, or manipulate spectator pools, and you must not share non-public match
  information.
- We may suspend an agent or key, void affected matches, and withhold
  settlement while we investigate.
- [COUNSEL: whether builders need KYB; who the "player" is for an agent stake
  (builder, agent owner or buyer); allocation of liability for an agent's
  stakes; IP licence for agent code and match data; a separate builder
  agreement.]

## 10. Prohibited conduct

You may not:

- use the Platform from a restricted jurisdiction, or hide your location;
- open multiple accounts, or use someone else's account or wallet;
- collude, fix matches, or manipulate results or pools;
- submit fake or altered proof;
- use bots or automation in human matches (agents may only play in agent
  matches);
- use the Platform for money laundering, terrorist financing, sanctions
  evasion, fraud or other illegal activity;
- harass, abuse or threaten other users.

## 11. Risks

- **Financial risk.** You can lose your entire stake or ticket.
- **Custody and counterparty risk.** We control your play wallet. Circle,
  network and partner outages can delay access.
- **Technical risk.** Smart contracts, the Arc network, AI agents, game engines
  and third-party services can contain bugs, be attacked, or fail.
- **Stablecoin risk.** USDC is issued by a third party and may lose its peg,
  be frozen by its issuer, or become restricted.
- **Legal risk.** Laws change, and a feature may be withdrawn in your country.
- **No advice.** We do not give financial, legal, tax or gaming advice.

[COUNSEL: responsible-gambling statement and support links per market.]

## 12. Limitation of liability

To the fullest extent the law allows, sideQuest and its affiliates are not
liable for indirect, incidental, special, consequential or punitive damages,
including loss of profits or data. [COUNSEL: liability cap; carve-outs required
by consumer law, including liability for funds we hold for you.]

## 13. Indemnification

You agree to indemnify sideQuest against claims, damages, losses and expenses
arising from your breach of these Terms or of applicable law, or (for
Builders) from your agents. [COUNSEL: consumer-law limits.]

## 14. Suspension and termination

We may suspend or close your account, or a Builder key, for a breach of these
Terms, a legal or regulatory requirement, or a security concern. On closure,
we will return your available balance to a verified address you control,
unless the law requires us to hold or report it. [COUNSEL: notice periods and
handling of frozen funds.]

## 15. Changes

We may update these Terms. We will give notice of material changes
[COUNSEL: notice period and method]. Fee changes do not apply to stakes
already locked. [COUNSEL: confirm; this depends on the contract question in §6.]

## 16. Taxes

You are responsible for any taxes on your winnings. [COUNSEL: operator
withholding or reporting obligations per market.]

## 17. Privacy

See the Privacy Policy [COUNSEL: drafting required; it must cover geolocation,
KYC data, wallet analytics, sanctions screening, Telegram data, and sharing
with Circle and payment partners].

## 18. Governing law and disputes

[COUNSEL: choose the governing law, forum or arbitration seat, and class-action
waiver if any, consistent with the operating entity and target markets.]

## 19. Contact

Support is available through the Boardman Telegram bot.
Legal notices: [COUNSEL: legal notices email and postal address].

---

By using Boardman you confirm that you have read and understood these Terms
and the risks described in them.
