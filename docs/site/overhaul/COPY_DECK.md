# Copy deck: every page, every state

Final words for the new site. Designers and developers paste them in as they are. If a line has to change, change it here first.

## How to read this deck

**Variant tags.** They map to the flags in `SITEMAP.md`:

| Tag | Shows when |
|---|---|
| **[P]** | Practice mode: `MONEY_MODE=practice` (today). |
| **[R]** | Real-money mode: `MONEY_MODE=real`. |
| **[N]** | Naira is live: `NAIRA_LIVE=1`. Only possible with [R]. |
| **[K]** | Passkey wallets are on: `PASSKEY_WALLETS=1`. |
| **[W]** | WhatsApp is live: `WHATSAPP_URL` is set. |
| **[W-]** | WhatsApp is not live. |

A line with no tag shows in every mode.

**Channel buttons.** `{CTA}` means the primary channel button:
- [W]: "Start on WhatsApp"
- [W-]: "Start on Telegram"

`{CTA2}` is the other channel, or "Play on the web" when there is only one channel.

**House style:**
- Short sentences. One idea each.
- Say "you" and "your friend". Say "dollars" or "$", "naira" or "₦", "practice money", "your Boardman wallet".
- Talk about Boardman as "we" or "Boardman". The old first-person "I'm the boardman" voice is retired, because it confuses first-time readers.
- **Never** use: robot(s), USDC (except the one practice-money helper step where the faucet shows it), Arc, testnet, chain, escrow contract, on-chain, resolver, custody, non-custodial, gas, the book, the desk, vig, odds, bet (for 1v1 matches), guaranteed, instant, licensed, regulated, risk-free.
- "Escrow" is allowed once per page, always explained: "Boardman holds both stakes until the game ends".
- Numbers use digits. Money is "$10" or "₦1,000". Never "10 USDC".
- **Read-aloud test:** a 16-year-old in Lagos reads it once and can tell a friend what it means.

## The 5-second pitch

> **Play your friends for money. Boardman holds both stakes and pays the winner.**

- Short form (OG and app store): **"Play your friends. Winner gets paid."**
- Shortest form (badges, bio): **"The referee and wallet for games with friends."**

## Global components

### Mode banner (top of every page, one line, dismissible for the session)

- **[P]** `Practice mode` · Play free with practice money. Real money is coming soon. → *How it works* (`/money#practice`)
- **[R]** (no banner; the header shows an `18+` pill instead)

### Header

- Logo: **Boardman**
- Nav: How it works · Money · Safety · Games · FAQ
- Buttons: `Play on the web` · `{CTA}`
- Mobile menu, extra rows: Top players · Help · Play on the web

### Sticky mobile CTA bar

- [W-]: `Start on Telegram`
- [W]: `Start on WhatsApp` | `Telegram`
- Accessible label: "Start playing with Boardman in chat"

### "Next" row (end of every player page)

| Card | Title | Line |
|---|---|---|
| How it works | **How it works** | 4 steps. Two minutes. |
| Money | **Money** | Top up, cash out, fees, limits. |
| Safety | **Safety** | Who holds the money. What if something goes wrong. |
| FAQ | **FAQ** | Straight answers to real questions. |

### Footer

- **Play:** How it works · Money · Safety · Games · FAQ · Top players · Help
- **AI & builders:** AI football league · AI agents' chess table · Build an AI agent
- **Company:** About · Partners · boardman@playingsidequest.fun
- **Legal:** Terms · Privacy · Delete your data
- **Channels:**
  - Telegram bot
  - Telegram community
  - [W] WhatsApp
  - [W-] WhatsApp — coming soon
- **Fine print:**
  - [P] "18+ only. Practice mode: no real money is used yet. Boardman by sideQuest."
  - [R] "18+ only. Real money — play only what you can afford to lose. Boardman by sideQuest."

### Trust strip (reused on Home, Money and Safety: 4 badges, icon plus one line)

1. **Both stakes locked first.** No stake, no game.
2. **Winner paid by the rules.** Not by whoever shouts loudest.
3. **No show? You get it back.** Automatic refunds.
4. **A real person on disputes.** When the photos don't settle it.

## 1. Home (`/`)

**Meta**
- Title: `Boardman — Play your friends. Winner gets paid.`
- Description:
  - [P] "Challenge a friend on EA FC, eFootball, CODM, Free Fire, chess and more. Boardman holds both stakes and pays the winner. Free practice mode now. Real money soon."
  - [R] "Challenge a friend on EA FC, eFootball, CODM, Free Fire, chess and more. Boardman holds both stakes and pays the winner. 18+."

### Hero

- **Eyebrow (pill):**
  - [P] `Practice mode — real money coming soon`
  - [R] `18+ · Real money`
- **H1:** **Play your friends. Winner gets paid.**
- **Subhead:** Boardman holds both stakes until the game ends, then pays the winner. No chasing anybody for money.
- **Buttons:** `{CTA}` · `Play on the web`
- **Under the buttons (small):**
  - [P] Free to try. No card. No crypto needed.
  - [R][N] Top up with naira. Cash out to your bank.
  - [R] without [N]: Real-money stakes from $2 to $25.
- **Hero visual:** a phone showing the chat:
  - "⚔️ @tunde challenged you · EA FC · $10 each"
  - "🔒 Both stakes locked"
  - "🏆 You won · $18.60 paid"

  The example figures are labelled "Example" in small text.

### Trust strip

The four badges, as written in Global components.

### How it works (4 steps, horizontal swipe on mobile)

- **H2:** **4 steps. That's it.**

| # | Title | Line |
|---|---|---|
| 1 | **Challenge** | Pick a friend, a game and a stake. |
| 2 | **Lock** | You both put in your stake. Boardman holds it. |
| 3 | **Play** | Play your game like always. Snap the final screen. |
| 4 | **Get paid** | Report the score. The winner gets the pot. |

- Link: `See every step →` (`/how-it-works`)

### Money in one look

- **H2:**
  - [P] **Practice now. Real money soon.**
  - [R] **Your money, clear and simple.**
- **Three cards:**
  - **Put money in**
    - [P] Get free practice money in the chat.
    - [N] Top up with naira by bank transfer.
    - [R] without [N]: Naira top-ups are coming soon.
  - **Fees**
    - Under $5 each: $0.50 each.
    - $5 and up: 7% of the pot.
    - Draws and refunds are free.
  - **Take money out**
    - [P] Practice money can't be cashed out.
    - [N] Cash out to any Nigerian bank.
    - [R] without [N]: Cash out to naira is coming soon.
- Link: `All the money rules →` (`/money`)

> **Note on the [P] cash-out line.** Practice money has no value, so "can't be cashed out" is true in spirit. The wallet's withdraw function still moves test tokens, so the line does not say "can't be withdrawn".

### Games

- **H2:** **Your game. Your rules.**
- **Body:** If you and your friend can play it and show the final score, you can play it on Boardman.
- **Chips:**
  - EA FC
  - eFootball
  - FC Mobile
  - CODM
  - Free Fire
  - PUBG Mobile
  - NBA 2K
  - 8 Ball Pool
  - Chess
  - Ludo
  - Draughts
  - `+ more`
- Link: `See all games →`

### Flagship strip (one band, below the fold)

- **Eyebrow:** `Flagship game`
- **H2:** **The AI football league.**
- **Body:** Own a club. An AI agent manages it, picks the team and the tactics, every matchday. You watch it play.
- **Practice note:** [P][R] League money is practice money for now.
- **Button:** `Meet the players →` (`/football/players`)

### Top players (live)

- **H2:** **Who's winning.**
- **Rows:** the top 5 from `/api/rematch/public`, each showing @name, wins and streak 🔥.
- **Empty:** "No winners yet this season. Be the first."
- **Error:** "Can't load the table right now. Try again in a minute."
- Link: `Full table →` (`/leaderboard`)

### Closing band

- **H2:** **Got a friend who talks too much?**
- **Body:** Settle it. Boardman holds the money.
- **Buttons:** `{CTA}` · `{CTA2}`

## 2. How it works (`/how-it-works`)

**Meta**
- Title: `How it works · Boardman`
- Description: "Challenge, lock, play, get paid. How Boardman holds both stakes and pays the winner — and what happens if something goes wrong."

### Header

- **H1:** **How Boardman works**
- **Subhead:** Boardman is the referee who holds the money. You play. We make sure the winner gets paid.

### `#start` — Start in 1 minute

1. **Open Boardman in chat.**
   - [W-] Tap Start on Telegram.
   - [W] Tap Start on WhatsApp or Telegram.
   - Or sign in on the web with Telegram.
2. **Add money.**
   - [P] Tap **💧 Get money** for free practice money.
   - [N] Tap **💧 Get money** → **Top up with naira**.
3. **Challenge a friend.** Tap **⚔️ Challenge**. Send them the link.

- Button: `{CTA}`

### The 4 steps (big step cards)

**1 · Challenge**
- Pick your friend, the game, and how much you each put in.
- Stakes run from $2 to $25 each.
- Your friend has 24 hours to accept.

**2 · Lock**
- You both put in the same stake. You go first, then your friend.
- Boardman holds both stakes until the game ends. Nobody can pull their money out halfway.
- [K] Your phone asks for your fingerprint or face to lock your stake.

**3 · Play**
- Play the game your way: on the couch, on your phone, at the game centre.
- Boardman doesn't watch your game. When it ends, **take a photo of the final screen.**

**4 · Get paid**
- You both report the score.
- If you agree, the winner is paid. If you don't, the photos decide (more below).
- The winner gets both stakes minus a small fee. A draw gives both of you your stake back, with no fee.

### `#if-something-goes-wrong` — If something goes wrong

| What happened | What Boardman does |
|---|---|
| Your friend never accepts | The challenge ends after 24 hours. Your stake comes back automatically. |
| Your friend accepts but never locks | Your stake comes back automatically. |
| Nobody reports a score | After 24 hours, both stakes go back. |
| You report with a photo, your friend goes quiet | After 6 hours, our check looks at your photo. If it shows you won, you're paid. If not, a person on our team decides. |
| You report different scores | Our AI checks both photos. If it isn't sure, a person on our team decides. |
| A refund gets stuck | We tell you it's pending, and we keep trying until it lands. |

- Link: `Read more on Safety →`

### Fees (short)

- Under $5 each: **$0.50 each**.
- $5 to $25 each: **7% of the pot**.
- Draws and refunds: **free**.
- **Example:** you each put in $10. The pot is $20. The fee is $1.40. The winner gets **$18.60**.
- Link: `All money rules →`

### Closing CTA

- **H2:**
  - [P] **Try it free.**
  - [R] **Ready when you are.**
- **Buttons:** `{CTA}` · `Play on the web`

## 3. Money (`/money`)

**Meta**
- Title: `Money · Boardman`
- Description:
  - [P] "Practice money now, real money soon. Fees, limits, and how naira top-ups and cash-outs will work."
  - [R] "Top up, cash out, fees and limits — in naira and dollars."

### Header

- **H1:** **Money, made simple.**
- **Subhead:** Your balance is kept in dollars. Stakes are in dollars. [N] You top up and cash out in naira.

### `#practice` — Practice mode vs real money

**[P] version**

- **H2:** **Right now: practice mode.**
- **Body:**
  - Everything on Boardman today uses practice money. It's free and has no cash value. You can't win or lose real money yet.
  - Use it to learn how Boardman works with your friends.
- **When real money comes:**
  - Top up with naira.
  - Cash out to your bank.
  - A wallet you control with your fingerprint or face.
  - Limits of $25 a match and $100 a day.
  - We'll say it loudly on every page.
- **Button:** `Get free practice money` → opens `{CTA}`, which goes straight to **💧 Get money**.
- **Secondary link:** `Prefer to do it on the web? →` (`/get-usdc`)

**[R] version**

- **H2:** **This is real money.**
- **Body:**
  - Stakes, wins and fees on Boardman are real dollars.
  - Only play with money you can afford to lose. You must be 18 or older.

### `#top-up` — Put money in

**[N] version**

- **H2:** **Top up with naira.**
- **Steps:**
  1. In chat, tap **💧 Get money** → **Top up with naira**. Choose an amount.
  2. You'll see the rate and the fees before you pay.
  3. Open the one-time secure page. Enter your name, date of birth, BVN or NIN, and your own bank account (for refunds).
  4. Send the exact naira amount by bank transfer to the account shown.
  5. Your dollars land in your Boardman wallet. We message you at every step.
- **Limits:** ₦1,000 to ₦500,000 per top-up. Up to ₦1,000,000 a day.
- **Fees:**
  - Boardman adds **no fee** on top-ups.
  - Paycrest, our naira partner, builds its fee into the rate. A small network fee is shown before you pay.
- **If it fails:** your naira goes back to the bank account you gave.
- **Safety note:** We only ask for your BVN or NIN on the secure page — never in chat.

**[P] or [R] without [N] version**

- **H2:** **Naira top-ups are coming soon.**
- **Body:**
  - You'll top up by bank transfer through Paycrest, our naira partner. You'll see the rate before you pay.
  - [P] For now, grab free practice money in the chat.

### `#cash-out` — Take money out

**[N] version**

- **H2:** **Cash out to your bank.**
- **Steps:**
  1. In chat, tap **💸 Withdraw** → **Cash out to bank**.
  2. Pick your bank and enter your 10-digit account number. We show the account name. Check it's you.
  3. Enter the dollar amount. You'll see about how much naira you'll get.
  4. Confirm on the one-time page with your withdrawal PIN.
  5. We message you when it starts and when your bank is paid.
- **Limits:** $1 to $50 per cash-out. Up to $100 a day, and up to 5 cash-outs an hour.
- **How fast?** We don't promise a time yet. Most of the wait is the bank transfer. We message you at every step.
- **If it fails:** the money comes back to your Boardman balance.
- **Safety note:** Boardman never asks for your PIN in chat. Withdrawal links work once and expire after 10 minutes.

**[P] or [R] without [N] version**

- **H2:** **Cash out to naira is coming soon.**
- **Body:** [P] Practice money can't be cashed out — it has no cash value.

### `#fees` — Fees

- **H2:** **One small fee. Only when someone wins.**
- **Fee table:**

  | Each player's stake | Boardman's fee |
  |---|---|
  | Under $5 | $0.50 from each player |
  | $5 and up | 7% of the pot |

- **Examples** (labelled "Examples"):

  | You each put in | Pot | Fee | Winner gets |
  |---|---|---|---|
  | $2 | $4 | $1.00 | $3.00 |
  | $5 | $10 | $0.70 | $9.30 |
  | $10 | $20 | $1.40 | $18.60 |
  | $25 | $50 | $3.50 | $46.50 |

- **Under the table:**
  - The fee comes out of the pot. The loser never pays more than their stake.
  - **Draws, no-shows and refunds are free.** You get your full stake back.
  - The fee is fixed by the Boardman escrow, the locked pot that holds both stakes. It is the same for everyone.
- **Fine print:** Stakes above $500 each would pay 10%. Today's limit is $25, so this doesn't apply to anyone yet.
- **Calculator (interactive):**
  - Label: "Your stake: $[ 10 ]"
  - Output: "Pot $20 · Fee $1.40 · Winner gets $18.60"

### `#limits` — Limits

- **H2:** **Limits that keep it friendly.**

| | Practice [P] | Real money [R] |
|---|---|---|
| Stake per match | $2 – $25 each | $2 – $25 each |
| Staked per day | — | Up to $100 |
| Withdrawal | $1 – $50, up to $100 a day | $1 – $50, up to $100 a day |
| Naira top-up [N] | — | ₦1,000 – ₦500,000, up to ₦1,000,000 a day |

- **Line:** We may lower limits for your safety. We'll never raise them without updating this page.

> **Build note.** The numbers come from `lib/siteMode.ts`, never typed into the page. The "$100 a day" stake cap exists only on `launch/arc-mainnet-humans`. Show it only in [R].

### Closing

- **Buttons:** `{CTA}` · `Read Safety →`

## 4. Safety (`/safety`)

**Meta**
- Title: `Safety · Boardman`
- Description: "Who holds the money, how disputes work, automatic refunds, and keeping your account safe."

### Header

- **H1:** **Your money, protected by the rules.**
- **Subhead:** Here's exactly who holds what, and what happens when things go wrong.

### `#who-holds` — Who holds the money?

**During a match (all modes)**

- Both stakes sit in the **Boardman escrow** — a locked pot on a public blockchain.
- It can do only two things:
  - Pay one of the two players.
  - Give both stakes back.
- Nobody can send it anywhere else, not even Boardman.
- **Footnote** (needs a deployed-contract check before launch, see BUILD_PLAN 6.4): "The winner must be one of the two players — written into the escrow code."

**Your wallet between matches**

- **[P] or [R] without [K]:**
  - Boardman looks after your wallet for you, the way a bank app does. Our wallet partner is Circle.
  - That means you're trusting Boardman with your balance. We'd rather say it plainly.
- **[K]:**
  - Your wallet is yours. You open it with your fingerprint or face (a passkey on your phone).
  - Boardman can't move money out of it. Every stake and every withdrawal needs your passkey.
  - Your passkey syncs with your Apple or Google account, so a new phone keeps working.
  - **If you lose every device with your passkey and your recovery phrase, nobody can get the wallet back — not even us.**

### `#disputes` — What if we don't agree on the score?

1. You both report the score. If you agree, the winner is paid.
2. If you don't agree, both of you send a photo of the final screen.
3. Our AI reads the photos. If it's sure, it settles. If it isn't, **a person on the Boardman team decides.**
4. Before the money moves on a disputed match, there's a short window to object.
5. Sending a fake or edited photo breaks our rules. We can close your account for it.

- **Tip:** Always snap the final screen — even if you think your friend will agree.

### `#refunds` — Refunds

Use the same table as How it works §"If something goes wrong".

- **Line:** Draws and refunds are always free. You get your full stake back.

### `#account` — Keep your account safe

- Withdrawals need your **withdrawal PIN** on a one-time page. Links expire after 10 minutes.
- **We will never ask for your PIN, password, BVN or NIN in chat.** Anyone who does is not Boardman.
- [N] We only ask for BVN or NIN on the secure top-up page. We pass it to our naira partner, Paycrest, and **we don't store it.**
- Only trust messages from:
  - our Telegram bot: @myboardmanOfficialBot
  - [W] our WhatsApp number shown on this site

### `#age` — 18+ and playing responsibly

- Boardman is for players **18 and older.**
- [R] Only play with money you can afford to lose.
- [R] Limits are built in: $25 a match, $100 a day.
- If playing for money stops being fun, take a break and talk to someone you trust. [FOUNDER: add a Nigerian support line or organisation here before real money goes live.]

### `#who-we-are` — Who runs Boardman?

- Boardman is made by **sideQuest**, a small team building fair ways to play for something.
- [FOUNDER: one line on where the team is and who the founder is, with a photo.]
- Talk to a person: `Help →`

### Closing

- **Buttons:** `{CTA}` · `Read the FAQ →`

## 5. Games (`/games`)

**Meta**
- Title: `Games · Boardman`
- Description: "EA FC, eFootball, FC Mobile, CODM, Free Fire, PUBG Mobile, chess, Ludo and more. If you can show the final score, you can play it on Boardman."

### Header

- **H1:** **Play what you already play.**
- **Subhead:** If you and your friend can play it and show the final score, Boardman can hold the money.

### Sections

Each section is a grid of game tiles: the name and a small "1v1" or "Custom room" tag.

**`#console` — Console**
- EA FC
- NBA 2K
- Any other console game

**`#phone` — Phone**
- Football: FC Mobile, eFootball
- Shooters: CODM (1v1, TDM, Deathmatch), Free Fire (1v1, Clash Squad), PUBG Mobile (TDM, 1v1), BGMI TDM
- Others:
  - 8 Ball Pool
  - Clash Royale
  - Brawl Stars 1v1
  - Mobile Legends 1v1
  - Wild Rift 1v1
  - Chess
  - Ludo
  - Carrom
  - Tekken
  - Asphalt
  - Rocket League Sideswipe
  - NBA 2K Mobile

**`#imessage` — iPhone (GamePigeon)**
- 8 Ball
- Cup Pong
- Basketball
- Darts
- Sea Battle
- Archers
- Word Hunt
- Anagrams
- 4 in a Row
- Checkers
- Chess
- Mini Golf

**`#table` — On the table**
- Chess
- Ludo
- Draughts
- Monopoly
- Any other board game

### Footnotes and rules

- **Battle royale note:** Battle-royale modes aren't on the list. Boardman needs a clear 1v1 winner.
- **Can't see your game?** Pick "Other" when you make a challenge, as long as you can show the final score.

### `#football` — Flagship card

- **Title:** **The AI football league**
- **Body:** A full league where every club is managed by an AI agent. Own a club, watch the matches, or build your own AI manager.
- **Practice note:** League money is practice money for now.
- **Buttons:** `Meet the players` · `Watch the league`

### Watch card (small)

- **Title:** **Watch AI agents play chess**
- **Body:** Three house AI agents play chess live, around the clock.
  - [P] Back a side with practice money.
  - [R] Practice money only.
- **Button:** `Watch live` (`/arena`)

> **Build note.** Game names come from `config/games/*.yaml` (enabled entries only) and `game_catalog.py`. Generate the grid at build time. Never hand-type it.

### Closing

- **H2:** **Found your game?**
- **Button:** `{CTA}`

## 6. FAQ (`/faq`)

**Meta**
- Title: `FAQ · Boardman`
- Description: "Is it gambling? Who holds my money? How fast is cash-out? Straight answers."

### Header

- **H1:** **Questions? Straight answers.**
- **Subhead:** Can't find yours? `Ask a person →` (`/help`)

The accordion has a group label for each section.

### The basics

**1. What is Boardman?**
The referee and the wallet for games with friends. You and a friend each put in a stake. Boardman holds both stakes while you play. The winner gets paid.

**2. Is this real money?**
- [P] Not yet. Right now it's practice money: free, with no cash value. Real money with naira top-ups is coming soon, and we'll announce it on every page.
- [R] Yes. Stakes, wins and fees are real dollars. You must be 18+.

**3. Do I need crypto?**
- No.
- [P] Practice money is free in the chat.
- [N] You top up with naira by bank transfer and cash out to your bank.
- Under the hood, your balance is held as digital dollars. You never need to buy crypto or manage it.

**4. Do I need to download an app?**
- No. Boardman runs inside Telegram.
- [W] Or WhatsApp.
- You can also sign in on the web at boardman.playingsidequest.fun/app.

**5. Is it on WhatsApp?**
- [W-] Coming soon. For now, use Telegram — it's free on any phone.
- [W] Yes. Tap Start on WhatsApp.

**6. Is this gambling?**
- Boardman is for games **you play yourself**, against a friend.
- Your skill decides the result. Boardman doesn't play against you and doesn't set odds.
- Laws on playing for money are different in each country. We're getting legal advice in Nigeria before real money goes live.
- You must be 18 or older.

> **Review note.** This answer must be re-read by counsel before [R]. Do not add "this is not gambling" or "it's legal": no counsel has cleared it (`docs/LEGAL.md`).

### Money

**7. Who holds my money?**
- During a match, both stakes sit in the Boardman escrow — a locked pot that can only pay one of you, or give both stakes back.
- Between matches:
  - [P] or no [K]: Boardman looks after your wallet for you.
  - [K]: your wallet is yours, opened with your fingerprint or face.
- More on `Safety`.

**8. What are the fees?**
- Under $5 each: $0.50 each.
- $5 and up: 7% of the pot.
- Draws and refunds are free.
- **Example:** $10 each, the winner gets $18.60.

**9. How much can I play for?**
- $2 to $25 per match, each.
- [R] Up to $100 staked a day.

**10. How do I put money in?**
- [P] Tap **💧 Get money** in the chat for free practice money.
- [N] Tap **💧 Get money → Top up with naira**, then pay by bank transfer. ₦1,000 to ₦500,000 per top-up.
- [R] without [N]: Naira top-ups are coming soon.

**11. How fast is cash-out?**
- [N] We don't promise a time yet. Most of the wait is the bank transfer. We message you when it starts and when your bank is paid. If it fails, the money comes back to your balance.
- [P] Practice money can't be cashed out. Bank cash-outs come with real money.

**12. Do you need my BVN?**
- Only for naira top-ups, because our naira partner Paycrest requires it.
- You enter it on a one-time secure page, never in chat. We pass it to Paycrest and don't store it.
- [P] Not needed in practice mode.

**13. What if a refund doesn't arrive?**
- We tell you it's pending and keep retrying until it lands.
- If it's been a while, message us on `Help`.

### Matches

**14. What if my friend loses and doesn't want to pay?**
They can't refuse. Their stake is locked before the game starts. When the result stands, the winner is paid from the pot.

**15. What if my friend lies about the score?**
- That's why you snap the final screen.
- If your reports don't match, our AI checks both photos. If it isn't sure, a person on our team decides.
- Fake photos can get an account closed.

**16. What if my friend doesn't show up?**
- If they never lock their stake, yours comes back automatically.
- If nobody reports a score, both stakes go back after 24 hours.
- If you report with a photo and they go quiet, you can be paid after 6 hours, once our check confirms your photo.

**17. What if it's a draw?**
You both get your full stake back. No fee.

**18. Do I always need to send a photo?**
- If you both report the same score, it can settle without one.
- But always take the photo, because if you disagree, the photo decides.
- Send the final screen only — not the lobby, not mid-game.

**19. Does Boardman watch my game?**
- No. You play however you like.
- Boardman only sees the scores you report and the photos you send.

**20. Which games can I play?**
- Anything 1v1 with a clear final score: EA FC, eFootball, FC Mobile, CODM, Free Fire, PUBG Mobile, NBA 2K, 8 Ball Pool, chess, Ludo, draughts and more.
- `See the full list →`

**21. Can I play someone I don't know?**
- Yes. Post an open challenge and anyone can take it.
- See who's open on `Top players`.

### Account and safety

**22. How old do I need to be?**
18 or older.

**23. Someone messaged me asking for my PIN. Is that you?**
- **No.** Boardman never asks for your PIN, password, BVN or NIN in chat.
- Only trust @myboardmanOfficialBot [W] and our WhatsApp number on this site.
- Report it on `Help`.

**24. I lost my phone. Is my money gone?**
- [P] or no [K]: Your wallet is tied to your Telegram account, not your phone. Log in to Telegram on your new phone. Withdrawals still need your PIN.
- [K]: Your passkey syncs with your Apple or Google account, so sign in on the new phone. If you lose every device with the passkey and your recovery phrase, nobody can recover the wallet.

**25. Can I play from outside Nigeria?**
- In most countries, yes. A few countries are blocked by law.
- You must still be 18+ and follow your local rules.

### The other stuff

**26. What's the AI football league?**
- Our flagship game: a football league where every club is managed by an AI agent.
- Own a club and let your AI manager pick the team, or just watch.
- League money is practice money for now.

**27. Why are there AI agents on Boardman?**
- AI agents play under the same rules as people, so they're a good way to show the system working around the clock.
- You can watch them play chess. If you build AI, you can enter your own.
- They never play in your matches.

**28. Who's behind Boardman?**
- sideQuest, a small team.
- [FOUNDER: one line plus the founder's name.]
- `About →`

## 7. Help (`/help`)

**Meta**
- Title: `Help · Boardman`
- Description: "Talk to a real person on Telegram, WhatsApp or email."

### Header

- **H1:** **Talk to a real person.**
- **Subhead:** Stuck on a match, a refund or a top-up? We read every message.

### Cards

**Telegram (primary)**
- **Title:** **Message us on Telegram**
- **Body:** The fastest way for anything with money in it. Send us your match code and what happened.
- **Button:** `Open Telegram` (goes to the support handle)
- **Founder input needed:** the bot has no Help button today (`src/bot/keyboards.py`). Supply a support Telegram handle for this button. Until one exists, link the community group and change the body to "Ask in the community — the team reads it."

**`#whatsapp` — WhatsApp**
- [W-]
  - **Title:** **WhatsApp — coming soon**
  - **Body:** We'll put the official number here. Until then, any "Boardman" WhatsApp is not us.
- [W]
  - **Title:** **Message us on WhatsApp**
  - **Body:** Our only official number is shown on this button.
  - **Button:** `Open WhatsApp`

**Email**
- **Title:** **Email**
- **Body:** boardman@playingsidequest.fun — for support, press and partnerships.
- **Button:** `Send an email`

**Community**
- **Title:** **Join the community**
- **Body:** Find players, post challenges, chat with the regulars.
- **Button:** `Join on Telegram`

### Form

- **Title:** **Leave a message**
- **Fields:**
  - "Your email"
  - "What happened? (add your match code if you have one)"
- **Button:** `Send`
- **Success:** "Got it. We'll reply by email."
- **Error:** "That didn't send. Check your connection and try again, or email us."
- **Validation:**
  - "Enter an email we can reply to."
  - "Tell us a little about what happened."

### Response time

[FOUNDER: commit to a response time, e.g. "within 24 hours", or leave this line out. Don't publish one we can't keep.]

### Quick links

- Top questions: "Who holds my money?" · "What if my friend lies about the score?" · "How fast is cash-out?"
- Each link opens the matching `/faq#…` anchor.

## 8. Play — web app (`/app`)

These are wording changes only. Flows and code stay as they are, and the edits land after the security branches merge.

### Signed out

- **H1:** **Play your friends. Winner gets paid.**
- **Body:** Sign in with Telegram. It's the same account and the same balance as the Boardman bot.
- **Buttons:** `Continue with Telegram` · `Use a wallet instead` (small)
- **Unknown-account warning:** "Open the Boardman bot once and tap Start, then come back here." Button: `Open the bot`
- **Remove from public view:** the "BotFather /setdomain…" hint (dev builds only).

### Signed in — balance card

- **Label:**
  - [P] "Your balance · practice money"
  - [R] "Your balance"
- **Empty:**
  - [P] "No practice money yet." Button: `Get free practice money`
  - [N] "No money yet." Button: `Top up with naira`
- **Score line:** "Your PLAY score: 120 · for bragging rights, not cash"

### Action grid

- `Challenge a friend`
- `My matches`
- `Wallet`
- `Watch AI agents play chess`

### Challenge wizard

| Step | Title | Help text |
|---|---|---|
| 1 | **Who are you playing?** | "Type their @username. They need to have opened Boardman once." |
| 2 | **How much each?** | "$2 to $25. You both put in the same amount." |
| 3 | **Where are you playing?** | Tiles: Console · Phone · iPhone (GamePigeon) · On the table |
| 4 | **Which game?** | Empty: "No games here yet. Pick 'Other' or try another group." |
| 5 | **Check and send** | "After you both lock: play, then send a photo of the final screen." |

- **Button:** `Send challenge`. While busy: "Sending…"
- **Error:** "Couldn't send the challenge. Check the username and try again."

### My matches

- **Empty open:** "No open matches. Challenge a friend or enter a match code."
- **Empty history:** "No finished matches yet."
- **Code box placeholder:** "Match code, e.g. AB12CD"

### Match page

- **Status labels:**
  - Waiting for your friend
  - Waiting for stakes
  - Ready — go play
  - Waiting for scores
  - Checking photos
  - A person is checking
  - Paid
  - Refunded
  - Refund pending
- **Buttons:** `Accept` · `Lock my stake` · `Send the final score` · `Refresh`

### Upload

- **H1:** **Send the final score**
- **Body:** "A photo of the final screen only — not the lobby, not mid-game."
- **Caption placeholder:** "e.g. 2-1, or W / L"
- **Success:** "Got it. We'll pay out once the scores check out."
- **Error:** "Pick a photo of the final screen first."

### Wallet

- **Address line:**
  - [P] "Practice money address — don't send real money here."
  - [R] Wording depends on the real-money funding network. [FOUNDER and engineering: confirm.]

### Withdraw, top-up, approve and setup pages

Keep the current wording, with these changes:
- Replace "USDC" with "dollars ($)".
- Keep every safety line:
  - "Links work once and expire after ten minutes."
  - "Boardman never asks for your PIN in a chat."
  - "This is real money."

## 9. Top players (`/leaderboard`)

- **Meta title:** `Top players · Boardman`
- **H1:** **Top players**
- **Subhead:** Wins, streaks and open challenges. [P] Practice-mode season.
- **Tabs:** `Top players` · `Open challenges`
- **Empty top:** "No winners yet. Be the first."
- **Empty open:** "No open challenges right now. Post one."
- **Error:** "Can't load the table right now. Try again in a minute."
- **CTA:** `{CTA}`

## 10. Get practice money (`/get-usdc`, [P] only, noindex)

- **H1:** **Get free practice money**
- **Body:** Practice money is free and has no cash value. You'll get it from Circle's free test faucet.
- **Steps:**
  1. Copy your Boardman address below.
  2. Open the faucet.
  3. Choose **Arc Testnet** and **USDC** — that's the practice money.
  4. Paste your address and tap Send.
  5. Back in the chat, tap **🔄 I funded — refresh**.
- **Buttons:** `Copy my address` · `Open the faucet`
- **No address in the link:** "Open this page from the chat: tap 💧 Get money in the Boardman bot."
- **Limit note:** "The faucet limits how often you can ask. If it says wait, try again later."
- **[R] state:** "Practice money is only for the AI agents' chess table now. Real matches use real money." → `Money rules`

## 11. AI agents' chess table (`/arena`)

Restyle the page. Copy changes:

- **H1:** **Watch AI agents play chess**
- **Subhead:** Raja, Nero and Sheila — three house AI agents — play live, around the clock. The games run on our server, so leaving the page doesn't stop them.
- **Bet card title:**
  - [P] **Back a side — practice money**
  - [R] **Back a side — practice money only.** Real-money betting is off.
- **Offline:** "The table is resting. Back soon. No bets are taken while it's down."
- **Between games:** "No game right now — here's the last one. The next one is warming up."

## 12. AI football league (`/football` and `/football/*`)

Only the shell changes. Copy changes:

- **Back link in the slim header:** `← Boardman`
- **`/football` H1:** **A football league run by AI managers.** Subhead: **Watch, own a club, or build the manager.**
- **Practice line on every money surface:** "League money is practice money for now."
- **`ManagerMarket` "funded with Naira" line:**
  - [N]: keep it.
  - Otherwise: "your play balance".

## 13. Builders (`/builders`)

- **Restyle only.** Technical words are fine here.
- **Fix:** rename "llms.txt — for robots" to "llms.txt — for AI agents" if any copy of it remains.
- **H1:** **Build an AI agent for Boardman**
- **Subhead:** Your agent plays. Boardman handles the table, the rules and the money.

## 14. Partners (`/partners`, new)

- **H1:** **Partner with Boardman**

**Game centres**
- **Title:** **Run a game centre?**
- **Body:** Get your own Boardman QR code. Players who start from your centre are linked to you. We're signing our first centres in Lagos.
- **Button:** `Talk to us` (mailto)

> **Build note.** Do not publish a revenue share percentage until the founder confirms it. The 1.5% in `config/partners.yaml` is a default on demo entries.

**`#minipay` — MiniPay**
- **Title:** **Boardman on MiniPay**
- **Body:** Open Boardman inside the MiniPay app.
- **Button:** `Open in MiniPay` (`/app?host=minipay`)
- **Remove:** the Proof-of-Ship checklist (move it to `docs/`).

**Everyone else**
- **Title:** **Brands, creators, tournaments**
- **Body:** Write to boardman@playingsidequest.fun.

## 15. About (`/about`)

- **H1:** **Every game needs a boardman.**
- **Body:**
  - In every neighbourhood, there's someone who holds the money so everybody plays hard and everybody gets paid.
  - Boardman does that job for games with friends — on your phone, your console or the table.
  - It holds both stakes, follows the rules, and pays the winner.
- **Who's behind it:** sideQuest. [FOUNDER: names, photo, city.]
- **Buttons:** `How it works` · `{CTA}`

## 16. System pages

### 404

- **H1:** **This page doesn't exist.**
- **Body:** The link may be old. Your money is safe — nothing moves from a missing page.
- **Buttons:** `Go home` · `{CTA}`

### Error

- **H1:** **Something broke on our side.**
- **Body:** Nothing moved because of this. Your stakes and balance are safe.
- **Buttons:** `Try again` · `Go home`
- **Small:** "Error code: {digest}"

### App error

- **H1:** **Something went wrong.**
- **Body:** Try again, or carry on in the chat.
- **Buttons:** `Try again` · `Open the bot`

### Offline (PWA)

- **H1:** **You're offline.**
- **Body:** Check your data or Wi-Fi. Nothing moves while you're offline.

### Loading

Show skeletons, not text. If text is needed, use "Loading…".

## 17. Social and OG copy

| Page | OG title | OG description |
|---|---|---|
| Home | Play your friends. Winner gets paid. | Boardman holds both stakes and pays the winner. [P] Free practice mode now. |
| How it works | How Boardman works | Challenge. Lock. Play. Get paid. |
| Money | Money on Boardman | Fees, limits, top-ups and cash-outs. |
| Safety | Is Boardman safe? | Who holds the money, and what happens if something goes wrong. |
| Games | Play what you already play | EA FC, eFootball, CODM, Free Fire, chess, Ludo and more. |
| FAQ | Boardman FAQ | Straight answers to real questions. |

**WhatsApp/Telegram share text (Home):**

> Bet you can't beat me on Boardman 😤 Boardman holds the money, winner gets paid. boardman.playingsidequest.fun

The word "Bet" in this share text is casual slang, not a betting claim. If counsel prefers, use "Think you can beat me?" instead.

## Facts the copy relies on

Re-check these when the code changes. Each fact cites the code that proves it.

| Claim in copy | Source of truth |
|---|---|
| Fee: $0.50 each under $5, 7% of the pot from $5 to $500, 10% above. Taken from the pot, so the loser never pays more than their stake. | `contracts/contracts/core/BoardmanEscrow.sol:80-88, 355-374, 574-586`; mirror in `src/stack/agentic/economy/fees.py:25-36` |
| Draws, cancels and refunds are free | `BoardmanEscrow.sol` `_cancel` 549-559; `fees.py:120` |
| Winner must be one of the two players | `BoardmanEscrow.sol:368` (`InvalidWinner`) |
| Stakes $2–$25 each | `src/backend/services/safety.py:23-24` (`CLAW_MIN/MAX_STAKE_USDC`) |
| Withdrawals $1–$50, $100 a day, 5 an hour | `safety.py:25-30` |
| Real money: $25 a match, $100 a day staked | `src/backend/services/stake_caps.py` on `launch/arc-mainnet-humans` (not on main) |
| Naira top-up ₦1,000–₦500,000 per order, ₦1,000,000 a day. Cash-out $1–$300 per order (Paycrest) and $500 a day; the stricter withdrawal cap of $50 and $100 a day applies. Boardman adds a 0% fee. | `config/funding_rails.yaml:104-133`; `docs/payments/PAYCREST.md` |
| BVN or NIN asked only on a one-time page, passed through, not stored | `docs/payments/PAYCREST.md` "What the player sees", "KYC: pass-through" |
| Failed top-up refunds to the bank; failed cash-out returns to the balance | `PAYCREST.md` architecture (refund account; refund → play wallet) |
| Challenge expires after 24h; creator refunded by the sweep | `src/channels/core/actions/matches.py:136,144`; `src/bot/jobs/expiry.py` `sweep_stale_creator_locks` |
| No report means both refunded at 24h; a silent opponent means the reporter is paid at 6h if the AI is confident, otherwise a dispute | `src/backend/services/match_report.py:29,31,39,297-337` |
| Matching scores settle without photos; otherwise photos, AI, then admin | `match_report.py:33, 240-249`; `clawstation_settlement.py` |
| Refund pending is told to the player and retried | `src/bot/jobs/expiry.py` (`_REFUND_PENDING_TOLD`) |
| Practice money comes from Circle's faucet via `/get-usdc` | `src/backend/services/circle_faucet.py:126`; `frontend/app/rematch/get-usdc/page.tsx` |
| Passkey wallets: Boardman can't move funds, recovery is the player's job | `docs/payments/SELF_CUSTODY_WALLETS.md`; `frontend/app/rematch/app/wallet/setup/page.tsx:185-195` |
| Wallets are custodial today | `docs/LEGAL.md:34-52`; `docs/site/HOMEPAGE_CLAIMS.md` |
| 18+ | `docs/TERMS_OF_SERVICE.md:50` |
| Fake proof can close an account | `TERMS_OF_SERVICE.md:190, 226` |
| Some countries blocked | `config/blocked_regions.json` (33 countries; NG not blocked) |
| Agent spectator betting is off on mainnet | `src/backend/services/spectator_policy.py:47-87` |
| Telegram bot `@myboardmanOfficialBot`; bot buttons "💧 Get money", "⚔️ Challenge", "💸 Withdraw", "🔄 I funded — refresh" | `frontend/lib/telegramBot.ts:6`; `src/bot/keyboards.py:74-78, 564, 760` |
| Game list | `config/games/{mobile,imessage,physical}.yaml`; `src/backend/services/game_catalog.py` |

## Claims we must not make

1. "Instant", "seconds" or "minutes" for payouts or cash-outs.
2. Licensed, regulated, approved, legal, or "not gambling".
3. "Non-custodial" or "you hold the keys" outside [K].
4. "Real money", "win cash" or naira features in [P].
5. KYC-verified players.
6. A list of banks or a naira rate.
7. A WhatsApp number before [W].
8. A daily stake cap in [P].
9. "Settled on-chain in under 1s".
10. Any X, Instagram or TikTok handle until the founder supplies one.
11. Testimonials we don't have.
