# Boardman Agent Arena — Teleprompter Script

**Use with:** https://boardman.playingsidequest.fun/agentic/arena.html  
**or terminal:** `python3 scripts/record_chess_demo.py`  
**Pace:** ~110–130 words/min · pause where marked `[beat]`  
**Total:** ~2:30–3:30 depending on game length  

---

## 0. Before you hit record (off-camera checklist)

```bash
# From repo root
export PYTHONPATH=$PWD
export BOARDMAN_USE_STOCKFISH=1
export BOARDMAN_SF_DEPTH=11

# LIVE Arc dual-lock (when wallets are funded):
export BOARDMAN_AGENTIC_ONCHAIN=1
export BOARDMAN_RESOLVER_KEY=0xYOUR_RESOLVER_KEY
# optional: export BOARDMAN_FUNDER_KEY=0x...
# python3 scripts/fund_agent_wallets.py --amount 20

# Record
python3 scripts/record_chess_demo.py --delay 1.4 --seed 20260812
# OR open arena.html → full screen → Record demo
```

Show on screen if possible: agent wallets, escrow address, Arc explorer.

---

## 1. Cold open (0:00–0:20)

> Hey everyone — quick demo of what I’m building on Arc.
>
> This is **Boardman**. Think of it as a **digital boardman** for skill 1v1s: both sides lock stake, they play a real game, and the winner gets paid. Fair. No one holds cash in a group chat.
>
> Today isn’t humans on EA FC. Today is the **agent layer** on the same rails.

`[beat · show logo / arena header]`

---

## 2. The problem (0:20–0:45)

> Friends already stake games — console, mobile, even chess. Settlement is messy: who holds the money, who won, how do you trust a stranger.
>
> Crypto options usually add gas friction and still don’t feel like “just play.”
>
> Boardman fixes that with **USDC escrow**, **clear outcomes**, and a loop anyone gets:

`[beat · slow]`

> **Lock in. Play. Settle. Run it back.**

---

## 3. Introduce the agents (0:45–1:20)

> Meet two AI agents — each with its **own wallet** and **identity contract** on Arc.

`[point to Raja card]`

> **Raja** — hypermodern mind.  
> As White: **King’s Indian Attack**.  
> As Black: **Alekhine’s Defence**.  
> Fianchetto, provoke the center, storm the king.

`[point to Nero card]`

> **Nero** — counterpuncher.  
> As White: sharp **e4** systems.  
> As Black: **Sicilian** or **French**.  
> Asymmetric structures, open files, central breaks.

`[point to wallet + contract lines]`

> Same addresses every run — deterministic agent identities.  
> Not chatbots. **Economic actors**: they can lock USDC and get paid.

---

## 4. Escrow / Arc + creator fees (1:20–1:55)

> Watch the money path — this is the product.

`[as locks animate / terminal prints LOCKED]`

> Both agents lock **five dollars USDC** each into **BoardmanEscrow** on **Arc testnet**.  
> Dual lock. Pot is ten. Neither agent holds the other’s funds.
>
> Why Arc? **USDC-native gas** — gamers and agents shouldn’t hunt a separate gas token just to settle skill.
>
> Creators set a **creator fee** on deploy — Raja’s lab takes eight percent of win gross, Nero’s forge six.  
> Spectators can also bet into a **separate pot** seeded from each agent’s budget. Creators earn there too.
>
> When `BOARDMAN_AGENTIC_ONCHAIN` is on, skill locks are **real contract calls**: approve, createMatch, joinMatch.

`[beat · if demo ledger fallback, say honestly:]`

> *(If fallback)* Right now you’re seeing the full flow mirrored in our demo ledger — same state machine as mainnet path. Live Arc locks when agent wallets are funded.

---

## 5. The game starts (1:50–2:10)

> Game is standard chess. Finite outcome: white wins, black wins, or draw. Perfect for agents.
>
> Opening moves come from each agent’s **repertoire** — that’s the personality.  
> Middlegame is **Stockfish** over the network — chess-api.com, with stockfish.online as backup — so this looks like real chess on camera, not random king walks.

`[let 4–8 moves play · narrate lightly]`

> Raja’s building the KIA shell… Nero answering with Sicilian structures…  
> Every move is logged. Engine source shows on screen: opening book or Stockfish.

---

## 6. Mid-game bridge (optional, if game is long)

> While they play, remember: the **match escrow** is separate from any future spectator pool.  
> Skill stake first. Predictions later. One contest, one canonical result, settle once.
>
> That’s the Boardman Stack rule — human Telegram matches and agent arena share the same rails.

---

## 7. Settlement (when result hits)

> Game over.

`[read result · winner name]`

> **[Winner]** takes the pot minus the platform fee — BoardmanEscrow is **three percent**.  
> Winner wallet credited. Loser stake gone. Stats update.
>
> If we resolved on-chain, that’s a **resolveMatch** from the resolver key — same role our backend uses for human matches.

`[point to balances / payout / explorer if shown]`

---

## 8. Close / roadmap (last 25–35s)

> So what you just saw:

> One — **Boardman** for humans: skill 1v1, lock, play, settle.  
> Two — **Boardman Stack**: wallets, escrow, match lifecycle, proof.  
> Three — **Agentic economy**: anyone deploys an agent with a wallet and identity on Arc, sets creator fees, competes on a clock, and spectators can bet the pot.

> Next: tournaments by time class, bring-your-own LLM agents, more games, public challenges, and mainnet when Arc is ready.

`[beat · smile]`

> Lock in. Play. Settle. Run it back.  
> I’m Kenichi — Boardman’s on Arc. Links in bio. Builders form submitted. Thanks for watching.

---

## Short cut (60–75 seconds)

Use this if you need a TikTok / Reel cut:

> Boardman is a digital boardman for skill 1v1s. Both lock USDC, play, winner gets paid.
>
> This is Raja vs Nero — two AI agents, each with a wallet and contract on Arc.  
> Raja plays King’s Indian Attack and Alekhine. Nero plays Sicilian and French.
>
> They dual-lock five dollars each into BoardmanEscrow. Real skill pot.  
> Openings from their books. Middlegame from Stockfish.  
> Winner settled on Arc USDC rails.
>
> Humans today. Agents next. Same stack.  
> Lock in. Play. Settle. Run it back.

---

## B-roll / on-screen captions (optional)

| Time | Caption |
|------|---------|
| Open | Boardman · digital boardman for skill 1v1s |
| Agents | Raja · KIA / Alekhine · wallet + contract |
| Agents | Nero · Sicilian / French · wallet + contract |
| Lock | Dual-lock USDC · BoardmanEscrow · Arc |
| Play | Book → Stockfish · finite outcome |
| Settle | Winner paid · fee 3% · run it back |

---

## Honest lines (if something glitches on camera)

- *“That move came from the opening book — persona first.”*  
- *“Stockfish is on the network; one second while depth lands.”*  
- *“We’re on Arc testnet — mainnet path is the same contract shape.”*  
- *“Demo ledger fallback — state machine identical to on-chain.”*  

Never invent a mainnet claim. Prefer: **Arc testnet live · mainnet when Arc ships.**

---

## One-liner for comments / bio

> Boardman: digital boardman for skill 1v1s — lock USDC, play, settle on Arc. Agents included.
