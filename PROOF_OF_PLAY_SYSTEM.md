# Proof of Play Content Engine System

## Overview

The Proof of Play Content Engine is a comprehensive system that enables sideQuest to power competitive 1v1 gaming challenges with integrated prediction markets via Base Markets. This creates a complete flywheel:

1. **Challenge Creation**: Players issue public or private 1v1 challenges
2. **Match Execution**: On-chain escrow and verification
3. **Proof of Play**: Immutable blockchain receipts for all matches
4. **Auto-Markets**: Top 10 players' public matches automatically create Base Markets pools
5. **Revenue Share**: 5% spread fee from prediction markets

## Architecture

### Database Schema

#### New Tables

**1. sessions**
- Tracks match series (for tournaments, rivalries)
- Links to multiple bets
- Status tracking: scheduled → active → completed

**2. challenges**
- Public challenge system
- 24-hour acceptance window
- Can be targeted (specific player) or open (anyone)
- Links to bets when accepted

**3. base_markets**
- Prediction pools created on Base Markets
- Auto-generated for Top 10 player public matches
- Tracks liquidity, volume, spread fees
- Market types: match_winner

**4. proof_of_play_receipts**
- Immutable receipts linking on-chain tx to matches
- Verification data (IPFS CIDs for screenshots)
- Cryptographic proof of match outcomes

#### Schema Updates

**profiles table:**
- `public_wins`, `public_losses`, `public_draws` - Public match W-D-L
- `creator_badges` - Array of badges (content_creator, top10, verified)
- `is_content_creator` - Flag for content creators
- `is_verified` - Verified status

**bets table:**
- `challenge_type` - ENUM: private, public
- `is_public` - Boolean for public visibility
- `session_id` - FK to sessions (for match series)
- `status` - Added: EXPIRED

### Core Philosophy

**Private Matches (Couch-Play)**
- Traditional friend matches
- `challenge_type: "private"`
- `is_public: false`
- No auto-markets
- Full privacy

**Public Matches (Competitive Scene)**
- Open challenges to the community
- `challenge_type: "public"`
- `is_public: true`
- Eligible for Base Markets (if Top 10)
- Public stats tracking
- Proof of Play enabled

## Business Logic

### Challenge Types

```typescript
// Private Match (Couch-Play)
{
  challenge_type: "private",
  is_public: false,
  // Friends only, no public visibility
}

// Public Match (Competitive)
{
  challenge_type: "public",
  is_public: true,
  // Listed in /challenges, eligible for auto-markets
}
```

### Top 10 Auto-Market Creation

```
When Top 10 player creates PUBLIC match:
  1. Check: is_top10_player(creator_id) = TRUE
  2. Check: challenge_type = "public"
  3. Check: is_public = TRUE
  4. Create base_market record
  5. Call Base Markets API
  6. Store market_id
  7. Market goes live
  8. Earn 5% spread fee

Revenue Flow:
  - Total volume: $10,000
  - Spread fee: 5% = $500
  - sideQuest share: 100% of spread
  - Payout to winners: $9,500
```

### Public Challenge Flow

```
1. Player A creates public challenge (24h expiry)
2. Challenge listed in /challenges
3. Player B sees and accepts
4. System creates bet with:
   - creator_id = challenge.issuer_id
   - opponent_id = challenge.issuer_id (Player B)
   - is_public = true
   - challenge_type = "public"
5. Challenge status → "accepted"
6. Match proceeds with on-chain escrow
7. Both players notified
```

### Proof of Play Flow

```
1. Match completes, winner determined
2. On-chain payout transaction sent
3. System creates proof_of_play_receipt:
   - bet_id: match ID
   - tx_hash: blockchain transaction hash
   - verification_data: IPFS CID for evidence
4. Receipt is immutable (audit table)
5. Publicly verifiable via:
   - Blockchain explorer (tx_hash)
   - IPFS (verification_data)
   - sideQuest API
```

## API Endpoints

### Sessions
```
POST   /api/sessions              → Create session
GET    /api/sessions/{id}         → Get session
PUT    /api/sessions/{id}/status  → Update status
GET    /api/sessions/player/{id}  → Player sessions
```

### Challenges
```
POST   /api/challenges            → Create challenge
GET    /api/challenges            → List challenges
GET    /api/challenges/{id}       → Get challenge
PUT    /api/challenges/{id}/accept → Accept
PUT    /api/challenges/{id}/decline → Decline
GET    /api/challenges/player/{id} → Player challenges
```

### Base Markets
```
POST   /api/base-markets              → Create prediction pool
GET    /api/base-markets              → List active markets
GET    /api/base-markets/{id}         → Get market
GET    /api/base-markets/bet/{id}     → Get by bet
PUT    /api/base-markets/{id}/resolve → Resolve market
```

### Proof of Play
```
POST   /api/proof-of-play           → Create receipt
GET    /api/proof-of-play/bet/{id}  → Get receipts
```

### Leaderboard
```
GET    /api/leaderboard/top10              → Top 10 players
GET    /api/leaderboard/top10/check/{id}   → Check eligibility
```

## Key Features

### Public Challenge System
- Issue/accept challenges with 24h windows
- Targeted or open to anyone
- $1-$10,000 stake amounts
- Real-time notifications

### Private Matches (Couch-Play)
- Traditional friend matches
- No public visibility
- Full privacy
- Same escrow & verification

### Proof of Play
- Immutable blockchain receipts
- IPFS integration for evidence
- On-chain transaction linking
- Publicly verifiable

### Top 10 Auto-Markets
- Automatic qualification checks
- Prediction pool creation
- 5% spread fee revenue
- Base Markets API integration

### Public Stats & Leaderboards
- Separate public W-L from total
- Creator badges (content_creator, top10, verified)
- Verification status indicators
- Enhanced player profiles

## Revenue Model

**Spread Fee**: 5% (negotiable based on volume)

**Example**: $500K monthly volume = $25K revenue  
**Annual Projection**: $300K+ at scale

**Partnership Split**: 70% sideQuest / 30% Base Markets

## Security & Trust

- Immutable audit trail (all changes logged)
- Multi-layer verification (blockchain, IPFS, AI)
- Anti-fraud measures (24h expiry, escrow, rate limiting)
- Atomic balance updates (no double-spend)
- Foreign key constraints (data integrity)

## Game Expansion

**Current Support**:
- EA FC 25
- NBA 2K25
- Call of Duty
- Mortal Kombat
- FIFA 24

**Easy Expansion**: Add new games by updating game list in frontend and validation in backend. No database schema changes needed.

## Deployment

**Status**: 🟢 Production Ready  
**Risk Level**: Low  
**Est. Time**: ~1 hour  
**Rollback**: 10 minutes

---

**Core Principle**: Private matches stay private. Public matches create opportunities. All matches have proof.