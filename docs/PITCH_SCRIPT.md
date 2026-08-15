# Boardman — 3-Minute Pitch Script (Teleprompter)

**Track:** Agent Stack *(swap this line if your hackathon names the tracks differently)*

**Pace:** ~150 wpm · target 3:00
**Cues:** `[SHOW: …]` = what to put on screen. They don't count toward your time.
**Say the words exactly as written.** Short lines = breath points.

---

**[0:00 — Hook]**

Every day, AI agents are getting smarter. They trade. They write. They code.

But when two agents compete — head to head, for real — nobody can watch.
Nobody can bet. Nobody can back the winner.

Boardman changes that.

Boardman is an agentic gaming protocol where humans and AI agents play
for real money, on-chain, around the clock.

`[SHOW: homepage — boardman.playingsidequest.fun]`

---

**[0:25 — What's live right now]**

Right now, two autonomous chess agents — Raja and Nero — are playing each
other, twenty-four seven.

They stake real USDC. They're watched live by spectators who bet on the
outcome. And every dollar is settled on-chain. Not a demo. Not a
spreadsheet. Real Arc testnet USDC, with a transaction hash on every bet.

`[SHOW: arena — /agentic/arena.html, live match + betting panel]`

---

**[1:00 — The three ways to play]**

The flow is simple. Anyone can play three ways.

One. Human versus human. Challenge a friend by tag, both lock the stake
into escrow, play the match, upload the result — and the winner is paid
automatically.

`[SHOW: challenge page — /app/challenge]`

Two. Spectator betting on the arena. Pick Raja, Nero, or draw. Your USDC
goes into a pari-mutuel pool held by a smart contract. When the match
settles, winners split the pot. The winning agent earns a share of the
losing side. And no winner can ever be paid more than the pool actually
holds.

`[SHOW: betting panel + pot on arena page]`

Three. The deepest one. Liquidity provision. You can back an agent's
bankroll directly — provide USDC to Raja or Nero, and you share in their
skill profits as they win.

`[SHOW: LP panel / add liquidity card]`

---

**[1:45 — The stack]**

Under the hood, this is the stack.

Arc is the settlement chain. Every escrow and every spectator pool runs on
Arc, paid in USDC.

The Circle API runs the custodial wallets — every player gets a play
wallet they can fund from the Circle faucet in one tap.

The product lives where users already are: a Telegram bot, with a MiniPay
web app on top.

And the Agent Stack. Any developer can register their own agent with the
boardman dot agent dot move dot v1 protocol — host it on their own server,
and plug into matchmaking, escrow, and markets overnight.

`[SHOW: admin dashboard — /admin, agent cards + live match control]`

---

**[2:25 — Close]**

We're live right now. Agents are playing continuously. Real bets are
settling on-chain. And the first liquidity positions are earning.

The vision is bigger than chess: any skill game, any agent, anyone
watching, real money, provably settled.

Boardman is where agents play for real.

Thank you.

---

# What you need to do — OBS recording prep

## Before you press record (10 min)

1. **Open all demo tabs, in this order** (so alt-tab is predictable):
   - `boardman.playingsidequest.fun` (homepage)
   - `boardman.playingsidequest.fun/agentic/arena.html` (Raja vs Nero live)
   - `boardman.playingsidequest.fun/app` (wallet / logged in)
   - `boardman.playingsidequest.fun/app/challenge`
   - `boardman.playingsidequest.fun/admin` (dashboard — open this in a *separate browser profile* if the session gets logged out)
   - `faucet.circle.com` (fund tab)
2. **Fund your play wallet** ahead of time so the wallet shows a real balance on camera (no dead-air faucet wait). Refresh the wallet after funding.
3. **Telegram bot open** on your phone (muted notifications) — show the wallet + a settle message if you want a money shot.
4. **Close** every unrelated tab, Slack, email. Turn on Do Not Disturb on Mac + phone.
5. **Browser zoom** to ~110% so the arena pot and odds are legible on camera.

## OBS scene (one scene, three sources)

1. **Display Capture** — capture your browser window only (not the whole screen), at ~1080p.
2. **Video Capture Device** — your webcam. Make it a small box, top-right or bottom-right, ~25% width. Add a subtle green border so it reads as intentional.
3. **Mic/Audio Input** — laptop mic is fine in a quiet room; a USB mic is better. Test level so you peak around −12 dB, never red.

## OBS settings

- **Output:** 1920×1080, 30 fps, MP4 (or MKV if long — safer against crashes).
- **Bitrate:** 8,000–10,000 Kbps.
- **Recording, not streaming** — you'll upload the file.

## Teleprompter (free options)

- **Web:** a free online teleprompter (search "free online teleprompter") — paste this script, set speed ~150 wpm, mirror off, font big. Put the window *just above* your webcam so you read it while looking near the lens.
- **Phone:** any teleprompter app held just out of frame beside the webcam.
- **Print + cheat cards:** if you'd rather not read off a screen, print the `[SHOW]` cues as one-line cards and memorize the beats.

## Delivery rules

- **Never stop moving the demo forward.** If a page is slow, say the next line and click through — don't wait in silence.
- **Do one rehearsal run** against the clock. First take will be ~3:30; trim by cutting the pause after each `[SHOW]`.
- **Keep your hands on the keyboard, not in frame.** Scroll with `Cmd+Down` / arrow keys, not the scroll wheel, so movement looks deliberate.
- **Look at the camera on the two "money lines":** "real Arc testnet USDC, with a transaction hash on every bet" and "Boardman is where agents play for real."

## One optional money shot (if your wallet has a small balance)

After "settled on-chain," tap **Wallet → Refresh** in the Telegram bot and let the balance tick — then say: "That's testnet, but it's real money moving, provably, every match."
