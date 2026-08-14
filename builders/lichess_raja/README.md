# Equip Raja with lichess-bot

Raja on Boardman stays a `boardman.agent.move.v1` webhook (`:18761/move`).
The same brain now talks UCI the way [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot) does:
a long-lived Stockfish process via [python-chess](https://github.com/niklasf/python-chess).

lichess-bot is **AGPL**. This folder is our adapter only — we do **not** vendor that repo.

## Boardman (already wired)

1. Install Stockfish (GPL) into the repo (binary is gitignored):

   ```bash
   bash builders/lichess_raja/fetch_stockfish.sh
   # or: export STOCKFISH_PATH=/path/to/stockfish
   ```

2. Restart Raja. `GET http://127.0.0.1:18761/health` should show `"uci_ready": true`.
   Move responses include `"engine": "lichess_uci"` when the local binary played.

3. Fallback: if the binary is missing, Raja still uses HybridEngine (remote Stockfish + book).

## Lichess (token in Boardman `.env`)

```bash
# .env
LICHESS_API_TOKEN=lip_...   # scope bot:play

git clone https://github.com/lichess-bot-devs/lichess-bot.git third_party/lichess-bot
pip install -r third_party/lichess-bot/requirements.txt
python3 builders/lichess_raja/run.py
```

`run.py` exports `LICHESS_BOT_TOKEN` (lichess-bot’s env name) from `LICHESS_API_TOKEN`
and does not write the secret into `config.yml`. Account used here:
[myrajafromboardman](https://lichess.org/@/myrajafromboardman) (BOT).

Raja on Lichess and Raja on Boardman share `pick_move` via `raja_uci.py`.
