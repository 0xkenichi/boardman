# Local chess engines

Binaries live here, gitignored — build on setup:

```bash
# Ethereal (Sheila's engine — different search than Stockfish)
git clone --depth 1 https://github.com/AndyGrant/Ethereal.git engines/Ethereal
make -C engines/Ethereal/src ARCH=arm64 basic   # or a sensible ARCH for the host
```

`scripts/run_house_session.py` and the house webhook boot pass
`BOARDMAN_UCI_ENGINE=engines/Ethereal/src/ethereal` to Sheila's builder
process, so her UCI path uses Ethereal while Raja and Nero keep the
local Stockfish. The generic-agent path (`lichess_uci.find_stockfish`)
honors `BOARDMAN_UCI_ENGINE` per process.
