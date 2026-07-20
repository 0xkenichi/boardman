# Rematch

**Lock in. Play. Settle. Run it back.**

Rematch is a Telegram app for **1v1 console skill matches** with **USDC escrow**. Players challenge friends, lock stakes, play (EA FC first), and settle with **AI screenshot proof**.

Built by [sideQuest](https://playingsidequest.fun).

## Play

| | |
|--|--|
| **Bot** | [t.me/ClawStationOfficialBot](https://t.me/ClawStationOfficialBot) |
| **Site** | [playingsidequest.fun/rematch](https://playingsidequest.fun/rematch) |
| **Leaderboard** | [playingsidequest.fun/rematch/leaderboard](https://playingsidequest.fun/rematch/leaderboard) |
| **Get USDC** | [playingsidequest.fun/rematch/get-usdc](https://playingsidequest.fun/rematch/get-usdc) · [Circle faucet](https://faucet.circle.com/) |

## How it works

1. Open the bot → **Get USDC** → fund your wallet  
2. **New challenge** a friend → they Accept  
3. Both **Lock** stake  
4. HOME / AWAY → play on console → submit full-time photo  
5. Winner paid in USDC · both earn PLAY score  

## Stack

- **Telegram** bot (button-first UX)  
- **Circle** developer-controlled wallets · USDC  
- **ClawEscrow** dual-lock / resolve  
- **AI vision** for scoreline from FT screenshots  
- Chains: **Arc** (default), Avalanche Fuji, Base Sepolia  

## Repo layout

This repository is the **Rematch product codebase** (bot, gaming backend, escrow integration, docs).

```
src/bot/           Telegram bot
src/backend/       Settlement, Circle, matches
docs/              Product & ops notes
deploy/            Hosting configs
```

Parent monorepo (full sideQuest app):  
https://github.com/playingsidequest-dotplay/sideQuest  
Branch: `rematch`

## Status

Live product · shipping weekly · multi-chain testnets · mainnet path in progress.

## License / contact

© sideQuest · Rematch  
Grants / builders: open an issue or contact via Telegram bot support.

