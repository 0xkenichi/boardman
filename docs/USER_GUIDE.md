# ClawStation — User Guide

## How EA FC Challenges Work

### 1. Start a Challenge
Tap `/start` on @ClawStationOfficialBot → **Main Menu**

```
[💰 Wallet] → Check your USDC balance
[⚔️ Challenge] → Start a 1v1 EA FC match
[🏆 Leaderboard] → Top players
[⚙️ Profile] → Your stats & settings
```

### 2. Pick Home / Away
When you challenge someone, **tell us**:
- **Home** = the club you're playing as (e.g. "Real Madrid")
- **Away** = the club you're playing against (e.g. "Barcelona")

This tells the **AI verifier** which side is yours — so when you send a screenshot, the bot knows which team to look for.

*You can change this anytime* — just start a new challenge with a different team.

### 3. Set Your Stake
Tap a USDC amount: `$5` `$10` `$25` `$50` `$100` `$250` `$500` or **Custom**

The stake locks in **ClawEscrow** (smart contract on Base) — safe until the match resolves.

### 4. Pick Your Opponent
- **🔍 Search** → type `@username` to find anyone
- **📤 Invite** → share a link with a friend
- **🌎 Public** → broadcast to all users on the platform

### 5. Confirm & Play
The bot sends an invite with **full details**:
```
⚔️ CHALLENGE INVITE
Game: EA FC
Stake: $25 USDC
Club: [your picked team]
Home/Away: [your side]
Opponent: @[username]
```

Lock it → play → send screenshot → **AI verifies** → payout 🎉

## Wallet & Payouts

**Deposit:** Send USDC to your ClawEscrow address (shown in profile)
**Withdraw:** Your linked wallet receives payouts automatically

### Coin Values
- `$1` = 1 USDC (always — no exchange rate)
- Stakes are in **USDC** not Naira (global settlement)

## PSN / Xbox / Account Linking

Link your **gaming account** so the AI can verify you:
```
/link_psn   → link your PlayStation Network gamertag
/link_xbox  → link your Xbox Live gamertag  
```

This is used **only** for AI verification — the bot checks gamertags match the screenshot before paying out.

## Location / Country

Use `/set_country` to tell opponents where you're playing from:
```
/set_country USA
/set_country UK  
/set_country Nigeria
```

This shows in the **invite** so everyone knows your region.

## Commands Summary

| Command | What it does |
|---------|-------------|
| `/start` | Open bot menu |
| `/challenge` | Start EA FC match setup |
| `/link_psn <gamertag>` | Link PSN for verification |
| `/link_xbox <gamertag>` | Link Xbox for verification |
| `/link_wallet <addr>` | Set your payout wallet |
| `/set_country <code>` | Set your playing region |
| `/balance` | Check USDC wallet |
| `/history` | View recent matches |
| `/profile` | View your stats |
| `/report <match_id>` | Submit match proof |
| `/leaderboard` | Top players by wins |

## What Happens After a Match?

1. **You play** the EA FC match (or any game — just send screenshot)
2. **Send screenshot** → `/report <match_id> <screenshot>`
3. **AI verifies** → the `score_verifier` checks:
   - Does the screenshot show a match?
   - Does the score match your claim?
   - Is your PSN/Xbox gamertag in the screenshot?
4. **Payout** → if verified, the ClawEscrow sends USDC to the **winner**
5. **Refund** → if 15 minutes pass without action, stake goes back to creator

## Web Docs

Full documentation at [playingsidequest.fun/clawstation](https://playingsidequest.fun/clawstation)