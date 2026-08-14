# Local UCI engines

Binaries stay off git (`engines/stockfish`). Raja looks here first, then
`STOCKFISH_PATH` / `RAJA_STOCKFISH`, then `third_party/lichess-bot/engines/stockfish`,
then `PATH`.

```bash
bash builders/lichess_raja/fetch_stockfish.sh
# → engines/stockfish
```

Stockfish is GPL. [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot)
is AGPL — clone it next to this repo if you want Raja on Lichess; do not copy
that tree into Boardman.
