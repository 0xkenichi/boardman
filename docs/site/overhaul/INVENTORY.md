# Site inventory: every route today, and what happens to it

This covers `frontend/app/**`, the rewrites and redirects in `frontend/next.config.js`, `frontend/proxy.ts`, and the HTML in `frontend/public`. It was checked against `origin/main` @ `70a7c64` and the live site (`curl` GET, 2026-10-20). The facts behind the money and trust copy are in `docs/site/HOMEPAGE_CLAIMS.md` and in the "Facts the copy relies on" table at the end of `COPY_DECK.md`.

**Verdicts:**
- **Keep**: same URL, redesigned and rewritten.
- **Merge**: the content moves into another page, and the old URL gets a 308 redirect.
- **Move**: same URL, but it leaves the player nav and lives in the builder, partner or legal group.
- **Kill**: the route is removed and gets a 308 redirect.
- **Utility**: same URL, not in the nav, reached from chat links or the app.

## How the site is wired today

- `/` is rewritten to `/v2` (`next.config.js` beforeFiles). The homepage has its own nav and footer inside `components/rematch/v2/BoardmanV2.tsx` and does not use the shared shell.
- `/how-it-works`, `/questions`, `/about`, `/games`, `/builders`, `/arena`, `/terms`, `/privacy`, `/data-deletion`, `/leaderboard`, `/get-usdc`, `/minipay` and `/contact` are rewritten to `/rematch/*`. They render inside `app/rematch/layout.tsx` with `RematchNav` and `RematchFooter`, and most use `BookShell`.
- `/app/*` is rewritten to `/rematch/app/*`, the web app.
- `/rematch/*` 308-redirects to the clean path. Static icons, the manifest and `sw.js` stay under `/rematch`.
- `/football/*` is a separate portal with its own `PortalNav`. Every page except `/football/players` is noindex, none of them are in the sitemap, and none link back to the main site.
- `proxy.ts` only adds no-store and noindex headers to `/admin`.
- These legacy redirects already exist and stay: `/agentic/*.html`, `/metrics`, `/stack`, `/docs`, `/hub` and `/catalog`.
- **Navigation today, three different ones:**
  - Homepage: How it works, Humans, Arena, The Book, Flagship, Builders.
  - `RematchNav`: Home, How it works, Games, Arena, Questions, Builders. The drawer adds Play, The board, Fund, About, Contact and the bot.
  - `PortalNav`: 9 football links.
- **Fonts and look:** Big Shoulders, Instrument Serif and Space Mono on cream paper (`#f2eee2`) with ink green. The root layout also loads Inter and JetBrains Mono, so up to five families ship.

## Player-facing marketing pages

| URL (source) | What it says today | Problems | Verdict |
|---|---|---|---|
| `/` (`app/v2/page.tsx` → `components/rematch/v2/BoardmanV2.tsx` 707 lines, `BoardmanLifecycle.tsx`, `FootballHand.tsx`) | **Hero:** eyebrow "A BOARDMAN RUNS THE TABLE · EST. MMXXVI"; H1 "Lock in. Play. Settle. agents too."; first-person lede "I'm the boardman… I hold both stakes"; TESTNET note; CTAs Open the app, See the board, The football league; waitlist form.<br>**Sections:** live "Slip" (house chess table); ledger strip (fees and escrow address); AFM flagship (616-player cards, ticker); 4-stage pinned "THE MATCH" scroll; 01 Humans; 02 Arena (agents' chess and betting); 03 The Book (fee slider); 04 Builders (code sample); CTA band "Paper first."; footer with chain ID. | Takes about 30 seconds to understand. Four audiences on one page. Agents and football take as much space as the actual product. Jargon throughout: escrow, Arc, USDC, resolver, chain 5042002. No naira, no WhatsApp, no "how do I start". Heavy page: live polling, a pinned scroll section, three font families. | **Keep URL, rebuild from scratch.** Retire the `/v2` rewrite name once the new home ships (see BUILD_PLAN). |
| `/how-it-works` (`app/rematch/how-it-works/page.tsx`, 85) | "Like the grown-up at the table who holds everyone's money." Four cards: LOCK, PLAY, PROVE, PAID. Practice-money CTA. | Good plain-words base. Still uses escrow, contract, Arc testnet and "transaction". No money in or out, no timers, no channels. | **Keep, rewrite.** Absorbs `/app/how-to-play` content and the refund timers. |
| `/questions` (`app/rematch/questions/page.tsx`, 85) | 10 Q&As: is the money real, a friend who doesn't pay, no-shows, who checks, can Boardman run away (admits the wallet is run by Boardman through Circle), getting game money, games, house agents, seed words, fees. | Honest but thin. Missing: gambling, age, naira, cash-out, limits, lying about the score, WhatsApp, draws, account safety. | **Merge into `/faq`** (308 `/questions` → `/faq`). |
| `/about` (`app/rematch/about/page.tsx`, 81) | "Every neighbourhood has one…" What Boardman does, why a contract does it better, humans and AI agents, who makes it (sideQuest). | The story is good. It sits in the drawer, and its agent paragraph distracts. | **Keep (footer, Company group), shorten.** The trust parts move to `/safety`. |
| `/games` (`app/rematch/games/page.tsx`, 107) | Any game with a friend (READY), AI chess (LIVE), Connect Four and tic-tac-toe (SOON), AI football league (SOON). | Contradicts the homepage, which leads with football. Never lists the real catalogue (EA FC, eFootball, FC Mobile, CODM, Free Fire, Ludo, chess…). | **Keep, rewrite.** Lists the real games by where you play them. AFM gets one flagship card. Agent chess becomes a small "watch" card. |
| `/contact` (`app/rematch/contact/page.tsx`, 110) | "The desk". Four doors: bot, community, builders, email. "Leave a note" form (posts to `/api/rematch/waitlist`). | Fine content under a bookmaker metaphor. No WhatsApp slot. No promised response time. | **Merge into `/help`** (308 `/contact` → `/help`). |
| `/leaderboard` (`app/rematch/leaderboard/page.tsx`, 201) | "The board": open challenges and the PLAY leaderboard, live from `/api/rematch/public`. | Useful social proof. The jargon ("PLAY score", "the book") hides it. **Linked from the bot** (`src/bot/utils/community.py:150`, `rematch_public.py:523`). | **Keep URL (footer and app), rename "Top players".** |
| `/get-usdc` (`app/rematch/get-usdc/page.tsx`, 130) | "Fund the wallet": copy address, Circle faucet, Arc Testnet, USDC. | Pure jargon. It is the only route to practice money. **The bot links it with `?address=`** (`src/backend/services/circle_faucet.py:126`). | **Utility, keep URL.** Retitle "Get free practice money". Noindex, out of the nav, linked from `/money` and the app. In real-money mode it shows a "practice money is only for the AI agents' table" note. |
| `/minipay` (`app/rematch/minipay/page.tsx`, 65, `MiniPayHost.tsx`) | "Boardman on MiniPay": Celo, Proof-of-Ship checklist, says "Custodial play wallet", shows the old `playingsidequest.fun/app?host=minipay` URL. | Internal and reviewer copy shown to the public. | **Move to `/partners`** as a section. Keep `/minipay` as a 308 to `/partners#minipay`, unless the MiniPay listing points at `/minipay` (founder question). The launch URL `/app?host=minipay` is unchanged. |

## Builder, agent and football pages

| URL (source) | What it says today | Verdict |
|---|---|---|
| `/arena` (`app/rematch/arena/page.tsx`, 1,119 lines) | "The chess table": three house AI agents (Raja, Nero, Sheila), a live board, betting with test USDC (Raja/Nero/Draw tiles), Telegram or wallet sign-in. | **Move.** Out of the player nav, linked from `/games` ("Watch AI agents play chess") and `/builders`. Restyle on the new tokens. Betting UI stays practice-only, and copy follows the realm rule: spectator betting is off on mainnet (`spectator_policy.py`). |
| `/builders` (`app/rematch/builders/page.tsx`, 196) | "For builders": webhook, Stack API key, register call, escrow `0xD382…`, 8 GitHub docs. | **Move** to the Builders group in the footer. Keep the copy technical (jargon is fine here). Restyle only. |
| `/football` (`app/football/page.tsx`, 114) | "A football league run by AI managers. Pick your seat." Three doors: watch, own, build. | **Keep as the flagship sub-site.** Add the main-site header and footer with a "Part of Boardman" back link. Index `/football` and `/football/players` only. |
| `/football/players` (`components/football/PlayersBrowser.tsx`) | "A world of players. Pick your squad." 58 nations, Nigeria's stars, search. | **Keep.** Add it to the sitemap. Best visual asset for the flagship card. |
| `/football/watch`, `/watch/prematch`, `/watch/broadcast` | Spectator seat, read-only pots, broadcast replay. | **Keep (noindex).** Only restyle the shell. Pots stay labelled read-only, practice money. |
| `/football/owner` (`ManagerMarket`, `OwnerDashboard`, `SalesDesk`) | "The owner seat": create, adopt or buy a manager. `ManagerMarket.tsx:546` says "funded with Naira". | **Keep (noindex).** Fix the naira line to follow the flag, because naira is not live. |
| `/football/agent`, `/manage`, `/squad/[agent_id]`, `/league`, `/tactics` | Agent operating seat, lineup editor, squad room, standings, match board. | **Keep (noindex).** Restyle the shell only. |
| `/football/roadmap` (142) | "The master plan — live status". This is an internal board. | **Kill from the public site.** 308 to `/football`, or gate it under `/admin`. Founder call. |
| `/agentic/football-catalog.html` (static, 207) | AFM player catalogue (legacy HTML). | **Kill.** Repoint `/catalog` and `/agentic/catalog` from this file to `/football/players` and delete the HTML. |
| `/llms.txt`, `/agentic/llms.txt` | Agent-facing protocol text, says Arc testnet. | **Keep.** Link only from `/builders`, not the player footer. |

## Web app (`/app`, internally `/rematch/app`)

The web app is product UI, not marketing. This overhaul **re-skins and rewords it** but does not change its flows. Security auditors are editing this code now, so copy and style changes land after their branches merge (see BUILD_PLAN phase 4).

| URL | What it says | Verdict |
|---|---|---|
| `/app` (`page.tsx`, 503) | Signed out: "Humans play. Boardman settles.", Continue with Telegram (shows a developer hint about "BotFather /setdomain"), wallet login, demo login.<br>Signed in: "Balance on the book (Arc · play wallet)", action grid, LiveRoomsCard, MiniPay promo. | **Keep, reword.** Remove the BotFather hint from public view. Plain balance label ("Your balance"). |
| `/app/challenge` (296) | 5-step wizard: "Who are you calling out?", stake, where, game, slip. | **Keep, reword.** Copy is in COPY_DECK §App. |
| `/app/match`, `/app/match/[code]`, `/app/match/[code]/upload` | My matches, match detail, submit result photo. | **Keep, reword.** Empty and error states are in COPY_DECK. |
| `/app/wallet` (133) | "Send Arc testnet USDC here only", faucet. | **Keep, reword.** Make the copy depend on the money-mode flag. |
| `/app/how-to-play` (157) | Short version, "House rule №1 — testnet money only", fund, play, bet the arena, fine print with a "SETTLED · ARC · <1S" stamp (a speed claim that isn't true). | **Merge into `/how-it-works`** (308). In the app, link to `/how-it-works` instead. |
| `/app/withdraw/[token]`, `/app/naira/[token]`, `/app/approve/[token]`, `/app/wallet/setup` | One-time pages opened from chat: withdrawal PIN, naira top-up form (Paycrest, off), passkey stake and withdraw approval (off), passkey wallet setup (off). | **Utility (noindex), keep URLs.** The backend builds these URLs (`self_custody/intents.py:82,86`, `withdraw_links.py`, `paycrest/onramp.py`). Re-skin only. Wording changes need the auditors' sign-off. |

## Legal, company and system

| URL | Verdict |
|---|---|
| `/terms` (renders `content/legal/TERMS_OF_SERVICE.md`, "Draft") | **Keep (Legal group).** Restyle the prose. No copy changes here: counsel owns it. |
| `/privacy` (336) | **Keep (Legal).** Note: it says "We do not run advertising or third-party analytics trackers". Any analytics in BUILD_PLAN must be first-party and cookie-free, or this page must change first. |
| `/data-deletion` (121) | **Keep (Legal).** |
| `/admin` (772, noindex, `proxy.ts`) | **Keep, untouched.** Not part of the site overhaul. |
| `/clawstation` (redirect to `/`) | **Keep the redirect.** Move it into `next.config.js` `redirects()` and delete the page (cut list item). |
| `app/not-found.tsx` "Not in the book" | **Keep, reword** (COPY_DECK §System). |
| `app/error.tsx` "The page tore", `app/rematch/error.tsx`, `app/rematch/app/error.tsx` | **Keep, reword.** Use one shared error component. |
| `sitemap.ts`, `robots.ts` | **Rewrite** to the new route list (BUILD_PLAN). |
| `/.well-known/discord`, `google…html` | **Keep** (domain verification). |

## Copy problems that appear on many pages

1. **Jargon in player copy:** USDC, Arc, testnet, escrow, contract, resolver, dual-lock, on-chain, chain 5042002, "the book" and "the board". Players should read "dollars", "practice money" and "Boardman holds both stakes".
2. **Three different custody stories:**
   - `/questions`: "run by Boardman through Circle".
   - `/minipay`: "Custodial play wallet".
   - The passkey pages: "you hold the keys", but those pages are behind an off flag.

   One honest line per money mode now lives in COPY_DECK.
3. **Football is "SOON" on `/games` and the flagship on `/`.** It needs one place and one status.
4. **Speed claims that aren't true:** "<1S" on `/app/how-to-play`, and the "FAIR · FAST · YOURS TO KEEP" footer stamp.
5. **No WhatsApp, naira, limits or age copy anywhere in the marketing pages.**
6. **The bookmaker theme leaks into the voice:** "the desk", "put me in the book", "paper first", "clerk the money". It is charming but slows a first-time reader down.
7. **Internal copy in public:** the BotFather hint, the Proof-of-Ship checklist, the roadmap page, the "Demo mode — live history needs the Stack API" note.

## Redirects the overhaul adds

All are 308 permanent, added to `next.config.js` `redirects()`:

| From | To |
|---|---|
| `/questions` | `/faq` |
| `/contact` | `/help` |
| `/app/how-to-play` | `/how-it-works` |
| `/minipay` | `/partners#minipay` (after the founder confirms the listing URL) |
| `/football/roadmap` | `/football` (or gate it) |
| `/catalog`, `/agentic/catalog` | `/football/players` (replaces the redirect to the static HTML) |
| `/fees`, `/pricing` | `/money#fees` (common guesses) |
| `/whatsapp` | `/help#whatsapp` (a stable link to print on flyers) |
| `/start` | `/how-it-works#start` |
