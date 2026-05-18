# Gaming Vertical

This folder is the single home for paused SideQuest gaming work.

It owns everything related to Telegram bot gaming, 1v1 staking, gaming quests, console-style game sessions, GameX Pro-adjacent experiments, proof-of-play, game verification, gaming-token/blockchain escrow notes, and paused WhatsApp follow-up for the gaming bot surface.

## Current Product Direction

- Primary focus is Social Quest + City Quest.
- Gaming is paused, not deleted.
- Telegram bot gaming comes before WhatsApp if bot work resumes.
- Telegram and WhatsApp bot work should remain available in the repo, but both are paused for now.

## Source Code

- `src/backend/` contains paused backend source for Telegram bot gaming and game-session flows.
- `src/backend/bot/` contains Telegram bot handlers, keyboards, and trust/safety commands for gaming bot flows.
- `src/backend/routes/gaming.py` contains the paused gaming API route implementation.
- Thin compatibility shims remain in `backend/` so existing imports and route registration do not break while the vertical is paused.

## Documentation

- `PROOF_OF_PLAY_SYSTEM.md`
- `docs/lite_papers/02_gaming_staking.md`
- `docs/api/` for blockchain, Circle escrow, and game coverage docs
- `docs/guides/` for Base Sepolia, testnet, and match-type guides
- `docs/architecture/BLOCKCHAIN_SECURITY_AUDIT.md`

## Shared Code Left Outside Gaming

Some gaming-adjacent files remain outside `gaming/` because they are shared with active Social Quest or City Quest flows, route registration, webhooks, wallet services, database access, or package/runtime entrypoints. See `REORG_REPORT.md` for the full risk list.
