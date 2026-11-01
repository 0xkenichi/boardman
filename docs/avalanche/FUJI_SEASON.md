# Boardman on Avalanche Fuji: chess season

Recorded 2026-11-01T14:00:57Z on Avalanche Fuji (chain 43113) by
[`scripts/avalanche/fuji_season.py`](../../scripts/avalanche/fuji_season.py).

Raja, Nero and Sheila (Boardman's chess agents) played a double round robin.
Every match was locked in [`BoardmanEscrow` v2](https://testnet.snowtrace.io/address/0xa0626A1744D4817B8b6fE0414a04CB20F6696F09), played in Boardman's engine
and settled on-chain by the resolver. Stakes are Circle test USDC with no cash value.

- Matches settled on-chain: **6** of 6
- USDC locked across the season: **24**
- Platform fees earned: **6 USDC**, swept to the treasury by Boardman's fee sweep ([tx](https://testnet.snowtrace.io/tx/0x8474175886be26542522276780209d106cf3f51a41b85488924869fbff6f2bec))
- Escrow books after the season: balance 0 = locked 0 + fees 0 + owed 0 → **balanced**
- Gas for all season transactions: 0.00298790103323901 AVAX

| # | White | Black | Result | Plies | createMatch | joinMatch | resolveMatch |
|--:|-------|-------|--------|------:|-------------|-----------|--------------|
| 1 | Raja | Nero | black_win | 123 | [0xba0b17bb…](https://testnet.snowtrace.io/tx/0xba0b17bb3f604fa366c12d55065a6345de70eb8838d26e777f6dc7707c279720) | [0x2885a2dd…](https://testnet.snowtrace.io/tx/0x2885a2dd2108e5700b4366ad249709406916fd47629fc30b0e0b89530996748a) | [0x2eb05854…](https://testnet.snowtrace.io/tx/0x2eb05854f8bb66036267bfd9f2a8ba74286b794c405abe796652ff8c96dfd9d9) |
| 2 | Nero | Sheila | black_win | 76 | [0x0e676c39…](https://testnet.snowtrace.io/tx/0x0e676c39d9d01246f7f15fc3b52cdf319cdac490080cd8554939b63f6b512b8b) | [0x47595fb5…](https://testnet.snowtrace.io/tx/0x47595fb5e75d3f120a983054a47d7b5c3caca7fdd1782ed951d8fb3c24c84d51) | [0xb0c93e19…](https://testnet.snowtrace.io/tx/0xb0c93e19c45fc2cbcee105f36be4ddf7c4c44e60504ac8d4a7807f344ac93322) |
| 3 | Sheila | Raja | white_win | 103 | [0x5a0dd522…](https://testnet.snowtrace.io/tx/0x5a0dd522a4d7c0a5c817575ab194a2d02c9991a9386214b573f287448a26b9f3) | [0x343e64f7…](https://testnet.snowtrace.io/tx/0x343e64f71ef72e03479d116a98e789ddc1575398cc08f6fd3c78e260f725eeac) | [0x574086ea…](https://testnet.snowtrace.io/tx/0x574086eadce134d032e5f9353758256622464c2cfca67c04a25dbe8f7c2ac85b) |
| 4 | Nero | Raja | black_win | 40 | [0xb8bda4f5…](https://testnet.snowtrace.io/tx/0xb8bda4f5e6fa2fba0d3054c05aaae6f54650a5a9ce9d1fe1af3358cc7f7ae852) | [0xf24115b8…](https://testnet.snowtrace.io/tx/0xf24115b8b6eb5b7350701790346b4bc1d28bf0f0c737254acdcbbb72dacd9a5c) | [0x20911c66…](https://testnet.snowtrace.io/tx/0x20911c66ce8118735ae9f1604b165008586a26153fe7acf7949bd3180cbac7c7) |
| 5 | Sheila | Nero | white_win | 37 | [0x31711172…](https://testnet.snowtrace.io/tx/0x31711172f914f095dfb947dd565ba43757c90952540a83d118e0a813729d1c7c) | [0x243c1d1b…](https://testnet.snowtrace.io/tx/0x243c1d1b3912bdaa24f45ef3bd3fd3e80e65187de4bfe2c528e42138b41e07ee) | [0x84868329…](https://testnet.snowtrace.io/tx/0x84868329a83254a385eadff209fc4efe79dbb96e368553113ef1217349a0fe5c) |
| 6 | Raja | Sheila | black_win | 51 | [0xf65cb4d7…](https://testnet.snowtrace.io/tx/0xf65cb4d79bc5b69611f6c68dd41b01048b2c6ff9a05ca9aba6aca58d5de2ab03) | [0xf9e62f45…](https://testnet.snowtrace.io/tx/0xf9e62f45c2e136d007827edfaa990862b78c0890df95d16892a26b3746cc70b6) | [0xf9de0b93…](https://testnet.snowtrace.io/tx/0xf9de0b93ab7d30bb6970f6f5412d0c976b0e3c0c7c886bb37802da8db2e8acfc) |

## Standings

Wallet balances include the ops faucet top-ups made before each match (listed in
[`fuji_season.json`](./fuji_season.json)), so they are not net winnings.

| Agent | W | D | L | USDC before | USDC after |
|-------|--:|--:|--:|--:|--:|
| Raja | 1 | 0 | 3 | 1.5 | 2.5 |
| Nero | 1 | 0 | 3 | 4.5 | 1.5 |
| Sheila | 4 | 0 | 0 | 0 | 7.5 |
