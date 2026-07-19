# Pre-mainnet checklist (free only)

## Done in code
- [x] Max stake $25 / max withdraw $50 / daily withdraw $100
- [x] Rate limits (challenges, locks, withdraws per hour)
- [x] Admin /pause /unpause (set CLAW_ADMIN_TELEGRAM_IDS)
- [x] Double-tap lock protection
- [x] Deposit / withdraw Telegram confirmations
- [x] Faster wallet (preferred chain first)
- [x] Instant callback ack on lock / challenge send
- [x] Free deploy recipes (local, Oracle, Render, Fly)

## You do (still free)
- [ ] Keep bot running: `./gaming/deploy/start_free_local.sh` or Oracle free VM
- [ ] Set your Telegram ID in CLAW_ADMIN_TELEGRAM_IDS (already set for stillkenichi if 6277067771)
- [ ] Test /safety /pause /unpause
- [ ] Closed beta with friends on testnet only
- [ ] Free uptime ping (cron-job.org → health URL when hosted)
- [ ] Never commit .env; rotate tokens if leaked

## Not free / later
- Mainnet USDC gas / liquidity
- Paid contract audit
- Always-on commercial VPS ($5/mo)
