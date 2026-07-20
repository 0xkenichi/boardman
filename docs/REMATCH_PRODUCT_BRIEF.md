# ReMatch — Product brief (refined)

**Brand:** ReMatch (product) · sideQuest (parent)  
**Status:** Live testnet · Telegram bot  
**Last updated:** 2026-07-20  
**Related:** `BRAND_REMATCH.md`, `AIRDROP_MECHANISM.md`, `PHASES_1_2_3_SAFE_DESIGN.md`, `GRANTS_AND_CHAIN_STRATEGY.md`

---

## What ReMatch is right now

ReMatch is a **Telegram-based 1v1 staked gaming platform** that lets users challenge friends to console matches (currently focused on **EA FC**), lock **USDC** stakes on testnets, and compete with **automated settlement**.

### Core experience

1. Challenge a friend via Telegram bot  
2. Both players lock USDC and select Home or Away  
3. Play the match  
4. Submit a photo of the final score  
5. **AI vision** reads and validates the result  
6. One-sided reporting can trigger payout when rules allow (e.g. no-show + proof)  
7. **One active match at a time** until resolved  

### Anti-abuse & retention

- **PLAY points** — reward good behaviour, penalize no-shows / ghosting  
- Chain weights: **Arc 1.5× · Avalanche 1.25× · Base 1.0×**  
- Higher mult for **new Telegram rivals** vs endless same-friend rematches  
- Short **match codes** (full UUID only for support / dispute)  
- Pre-lock cancel path (design / partial); post-lock final unless mutual cancel (roadmap)  

### Live chains (testnet)

Arc Testnet · Base Sepolia · Avalanche Fuji  

### Positioning

Independent product under **sideQuest**, focused on competitive, fair, social staked gaming — not a casino, not a generic DeFi app.

**Site:** https://playingsidequest.fun/rematch  

---

## Gaps (current)

| Area | Current state | Needed | Priority |
|------|---------------|--------|----------|
| Verification | AI vision on photo | Higher accuracy + low-confidence manual fallback | **High** |
| Proof options | Photo only | Video proof / stronger verification | **High** |
| Game support | Primarily EA FC | 2–3 more popular titles | **High** |
| User trust | Flow rules | Reputation score + visible history | Medium |
| Matchmaking | Friend-only | Public/open challenges + filters | Medium |
| Engagement | PLAY points | Leaderboards, stats, rivalries, streaks UI | Medium |
| Onboarding | Functional bot | Clear tutorials, rules, dispute process | Medium |
| Chain coverage | 3 testnets | Mainnet (Arc first) + explore TON later | **High** |
| Metrics & traction | Early | Usage data, volume, feedback | **High** |
| Branding | Rematch live | Stronger visual identity & marketing | Medium |

---

## Improvement ideas

### High-impact / quick wins

1. AI confidence scoring + **manual review fallback** when low  
2. Short **video proof** option  
3. In-bot **rules & tutorial** flow  
4. Simple **reputation** on profile  
5. **Match history + stats**  

### Medium-term

- Expand games (2K, Madden, eFootball…)  
- Public challenges + filters  
- Leaderboards / rival systems  
- Small tournaments / brackets  
- Polish wallet & network switching  

### Strategic

- Mainnet on Arc (then Avalanche / Base)  
- Optional TON for Telegram-native rails  
- Light sideQuest integration (result → quest proof) without losing independence  
- Dedicated landing + marketing assets  

---

## Roadmap

### Short-term (1–3 months)

- Reliable AI (+ video proof)  
- Meaningful **testnet** usage & feedback  
- Branding + independent positioning  
- Ecosystem grants (Circle/Arc, Avalanche, Base)  

### Medium-term (3–9 months)

- Mainnet + real USDC volume  
- More games + public matchmaking  
- Community / retention features  
- Clear monetization (fees, premium)  

### Long-term vision

Go-to social, fair platform for staked 1v1 and small-group console gaming on Telegram — smooth UX, strong anti-abuse, rewarding competition. Sustainable independent product with light sideQuest synergy.

---

## Funding & airdrop honesty

PLAY points are **not** a guaranteed token. Airdrops depend on seasons and funding.  
If grants/runway fail, points remain a free score only. See `AIRDROP_MECHANISM.md`.

---

## What we can work on **now** (prioritized build queue)

See next section in session notes / keep this table as the execution queue:

| # | Work item | Why now | Effort |
|---|-----------|---------|--------|
| 1 | **Testnet volume campaign** (Arc-first, bot banners, invite friends) | Proof for grants + mainnet story | S |
| 2 | **Metrics dashboard** (settles, wallets, USDC volume by chain) | Grant applications | S–M |
| 3 | **Cancel UX** (pre-lock free, post-lock mutual) | Trust gap called out in brief | M |
| 4 | **In-bot rules + tutorial** (`/howto` polish + first-run) | Onboarding gap | S |
| 5 | **Match history / stats** on profile | Trust + retention | M |
| 6 | **AI fallback** when confidence low → hold + dispute queue | Verification high priority | M |
| 7 | **Public board + 24h lock** | Matchmaking gap | M |
| 8 | **Game packs** (NBA 2K, Madden) | Game support high | M |
| 9 | **Mainnet Arc plan** + deploy when ready | Strategic | L |
| 10 | **Grant submits** (Circle Questbook, Team1 mini) | Funding | S |

**Everything new still reuses today’s 1v1 match engine.**
