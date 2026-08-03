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
- Chains: **Arc Testnet only** (live) · Avalanche Fuji next · Base Sepolia legacy  

### Rematch Stack (platform)

Infrastructure under the bot so **other builders** can ship new experiences on the same rails (wallets, escrow, match lifecycle, proof, PLAY).

| | |
|--|--|
| Design | [`docs/REMATCH_STACK.md`](docs/REMATCH_STACK.md) |
| Package | `src/stack/` |
| HTTP | `GET /api/stack/v0/health` · `/catalog` · `/chains` · `/public/board` |
| Builders | [`src/stack/README.md`](src/stack/README.md) |

## Repo layout

This repository is the **Rematch product codebase** (bot, gaming backend, escrow, public web, contracts) **and** the **Rematch Stack** platform layer.

```
src/bot/                 Telegram Rematch experience
src/backend/             Settlement, Circle, matches, public API
src/stack/               Rematch Stack (builder-facing façade + API)
frontend/                Next.js /rematch pages + public API route
frontend/public/         rematch-logo assets
contracts/               ClawEscrow (Hardhat) + deployments
docs/                    Product, ops, REMATCH_STACK.md
deploy/                  Hosting configs
```


On playingsidequest.fun, `/rematch` is a thin redirect to the Telegram bot.  
Host the real docs/leaderboard from `frontend/` in this repo (see `frontend/README.md`).

## Status

Live product · shipping weekly · multi-chain testnets · mainnet path in progress.

## Strategy & 24/7 deploy

| Doc | Content |
|-----|---------|
| [`docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`](docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md) | **Canonical** 1v1 / public / mobile / fiat / Arc decisions — do not forget |
| [`docs/IMESSAGE_AND_CHANNELS.md`](docs/IMESSAGE_AND_CHANNELS.md) | iMessage games catalog · multi-channel · phone/API |
| [`docs/MOBILE_GAMES.md`](docs/MOBILE_GAMES.md) | FC Mobile, Free Fire, COD, Valorant, PUBG, … |
| [`docs/WEBAPP_AND_MINIPAY.md`](docs/WEBAPP_AND_MINIPAY.md) | Webapp + MiniPay overview |
| [`docs/WEBAPP_UX_AND_SECURITY.md`](docs/WEBAPP_UX_AND_SECURITY.md) | Webapp parity · security · simple UX |
| [`docs/V1_TO_V2_RELEASE.md`](docs/V1_TO_V2_RELEASE.md) | **V1 summary · upgrades · V2 offer · content kit** |
| [`docs/PAYMENT_RAILS.md`](docs/PAYMENT_RAILS.md) | Fiat top-up → USDC play balance (mainnet prep) |
| [`docs/AKASH_DEPLOY.md`](docs/AKASH_DEPLOY.md) | Always-on bot on Akash (CPU) |
| `Dockerfile.akash` · `deploy/akash/deploy.yml` | Image + SDL |
| `config/games/imessage.yaml` | GamePigeon / iMessage catalog |
| `config/games/mobile.yaml` | FC Mobile, Free Fire 1v1, COD DM, … |

## License / contact

© sideQuest · Rematch  
Grants / builders: open an issue or contact via Telegram bot support.

