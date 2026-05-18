# Lite Paper: Gaming & Staking
## *Trustless Competition on Chain*

**Version:** 1.0 | **Date:** May 2026 | **Classification:** Public

---

## The Problem

Competitive gaming has a trust problem. When two players agree to a match with real money on the line, there's no neutral party to:
- Hold the funds securely
- Verify the outcome fairly
- Distribute winnings automatically
- Handle disputes without bias

Current solutions require either trusting a centralized platform (which can be hacked, biased, or disappear) or trusting your opponent (which works until real money is involved).

## The Solution: ClawEscrow

sideQuest's gaming system uses a smart contract on Base L2 (Ethereum) to create trustless, transparent, and automated match resolution.

### How It Works

```
Player 1 creates match → Stakes USDC into escrow
         ↓
Player 2 joins match → Stakes matching USDC
         ↓
Match is LOCKED → Both funds secured on-chain
         ↓
Players compete → Off-chain (FIFA, NBA 2K, etc.)
         ↓
Results submitted → AI verifies screenshots
         ↓
Smart contract resolves → Winner paid automatically
         ↓
3% fee deducted → Platform treasury
```

---

## Smart Contract: ClawEscrow

### Contract Specifications

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `FEE_BPS` | 300 (3%) | Platform fee on winnings |
| `MAX_STAKE` | 10,000 USDC | Per-match cap |
| `RESOLUTION_TIMEOUT` | 7 days | Auto-cancel stale matches |
| Network | Base L2 | Low gas, fast finality |
| Token | USDC (Circle) | Stable, regulated |

### Match States

```
OPEN → LOCKED → RESOLVED (winner paid)
  ↓       ↓
  ↓    DISPUTED → RESOLVED (AI mediator decides)
  ↓       ↓
CANCELLED ←──┘ (refunds both players)
```

**OPEN:** Player 1 has staked, waiting for opponent
**LOCKED:** Both players staked, match in progress
**DISPUTED:** Conflict flagged, AI mediator deciding
**RESOLVED:** Winner determined, funds distributed
**CANCELLED:** Match abandoned, funds refunded

### Key Functions

```solidity
// Player 1 creates match and stakes
function createMatch(bytes32 matchId, uint256 stake) external;

// Player 2 joins with matching stake
function joinMatch(bytes32 matchId) external;

// Backend resolver pays winner
function resolveMatch(bytes32 matchId, address winner) external;

// Flag for AI mediation
function flagDispute(bytes32 matchId) external;

// Cancel and refund (timeout or agreement)
function cancelMatch(bytes32 matchId) external;

// Anyone can cancel stale matches after 7 days
function cancelStaleMatch(bytes32 matchId) external;
```

### Security Features

- **ReentrancyGuard:** Prevents recursive call attacks
- **Pausable:** Emergency stop for critical issues
- **Ownable:** Admin functions restricted to deployer
- **SafeERC20:** Safe token transfers (handles non-standard ERC20)
- **Timeout Protection:** Funds can't be locked forever

---

## The Gaming Flow

### 1. Challenge Creation
```
Hero A: "I'll bet 50 USDC I can beat anyone in FIFA"
→ Creates match on ClawEscrow
→ 50 USDC transferred to contract
→ Match status: OPEN
```

### 2. Challenge Acceptance
```
Hero B: "I accept that challenge"
→ Joins match on ClawEscrow
→ 50 USDC transferred to contract
→ Match status: LOCKED
→ Total pot: 100 USDC
```

### 3. Competition
```
Players compete off-chain (console/PC)
Both submit score screenshots via app
AI mediates if scores conflict
```

### 4. Resolution
```
Backend resolver calls resolveMatch()
Winner receives: 97 USDC (100 - 3% fee)
Platform receives: 3 USDC fee
Match status: RESOLVED
```

### 5. Dispute Handling
```
If scores conflict:
→ Match flagged as DISPUTED
→ AI analyzes both screenshots
→ Determines winner with confidence score
→ If confidence < 80%, human review required
→ Winner paid, match RESOLVED
```

---

## AI Score Verification

### How It Works

1. **Screenshot Capture:** Players upload game end-screen
2. **OCR Extraction:** Text recognition extracts score
3. **Pattern Matching:** AI verifies it's a valid game screen
4. **Cross-Reference:** Both players' submissions compared
5. **Confidence Score:** AI assigns certainty level

### Confidence Thresholds

| Confidence | Action |
|-----------|--------|
| > 95% | Auto-resolve immediately |
| 80-95% | Auto-resolve with flag for review |
| < 80% | Escalate to human mediator |

### Supported Games

| Game | Platform | Verification Method |
|------|----------|-------------------|
| EA Sports FC (FIFA) | PS5, Xbox | Score screenshot OCR |
| NBA 2K | PS5, Xbox | Score screenshot OCR |
| Call of Duty | PS5, Xbox | K/D screenshot OCR |
| Fortnite | Multi-platform | Placement screenshot |

---

## Fee Structure

### Standard Fees

| Transaction | Fee | Recipient |
|------------|-----|----------|
| Match Win | 3% of pot | Platform Treasury |
| Flash Quest Entry | 1% | Platform Treasury |
| Early Withdrawal | 5% | Platform Treasury |
| Payout (Winner) | 0% | None |

### Early Adopter Program

The first 1,000 users after mainnet launch receive:
- **3% fee locked forever** (vs. 7% standard)
- Exclusive "Founder" badge
- Priority access to new features
- Governance voting weight bonus

### Minimum Fee Floor

If 3% of a match is less than $0.50, a flat $0.50 fee applies. This ensures micro-matches remain economically viable for the platform.

---

## Risk Management

### Smart Contract Risks

| Risk | Mitigation |
|------|------------|
| Reentrancy Attack | OpenZeppelin ReentrancyGuard |
| Integer Overflow | Solidity 0.8.x built-in checks |
| Oracle Manipulation | Multi-source verification |
| Admin Key Compromise | Multi-sig wallet, timelock |
| Contract Bug | CertiK audit, bug bounty |

### Operational Risks

| Risk | Mitigation |
|------|------------|
| Resolver Goes Offline | 7-day timeout auto-cancel |
| AI Verification Error | Human fallback for low-confidence |
| Network Congestion | Base L2 low gas, fast finality |
| USDC Depeg | Stablecoin monitoring, circuit breakers |

### Insurance Fund

A percentage of platform fees (10%) flows into an insurance fund to cover:
- Smart contract exploits
- AI verification errors
- Resolver failures
- Force majeure events

---

## Future Extensions

### 1. Tournament Brackets
- Multi-round elimination
- Automated bracket generation
- Prize pool distribution (winner-takes-all, top-3, etc.)
- Seasonal tournaments with massive prizes

### 2. Spectator Staking
- Bet on matches you're not playing
- Social proof: "I bet on @HeroKing to win"
- Revenue share with players
- Enhanced engagement and virality

### 3. Cross-Chain Support
- Bridge to other L2s (Optimism, Arbitrum)
- Multi-token support (USDT, DAI)
- Cross-chain reputation portability

### 4. DAO Governance
- Community votes on fee structure
- Treasury allocation decisions
- Game additions/removals
- Dispute resolution policy

---

## Conclusion

The Gaming & Staking system transforms competitive gaming from a trust-dependent activity into a trustless, transparent, and automated protocol. By combining smart contract escrow with AI verification, sideQuest creates a fair playing field where the best player always wins — and gets paid instantly.

**No more "he said, she said." No more ghosting after losing. No more waiting for payouts.**

**Just pure competition, verified and rewarded.**

---

*"Put your money where your mouth is."*
