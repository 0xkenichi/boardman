# New site map and navigation

**Goal:** a Nigerian player who lands on any page knows within 5 seconds what Boardman is, and knows within one tap how to start.

**Design rules:**
- Boardman is the product. Games, AI agents and football hang off it. They never compete with it.
- At most 8 top-level player pages. Builder, partner, company and legal pages live in the footer.
- Every page has **one** primary call to action (CTA), and it is always the same thing: start playing in chat.

## Site flags (decide which copy shows)

All copy variants in `COPY_DECK.md` switch on these flags. They are build-time public env vars, so pages stay static and fast. BUILD_PLAN task 1.2 adds a check that keeps them in step with the backend.

| Flag | Values | Default | Turns on |
|---|---|---|---|
| `NEXT_PUBLIC_MONEY_MODE` | `practice` \| `real` | `practice` | Real-money copy: the $25 a match and $100 a day limits, and the "real money" warnings. Set it only when the backend has `REAL_MONEY_ENABLED=1` and the Arc mainnet escrow is live. |
| `NEXT_PUBLIC_NAIRA_LIVE` | `0` \| `1` | `0` | Naira top-up and cash-out copy (Paycrest). Needs `MONEY_MODE=real`, because Paycrest is mainnet-only. |
| `NEXT_PUBLIC_PASSKEY_WALLETS` | `0` \| `1` | `0` | "A wallet only you control" copy. Mirrors `SELF_CUSTODY_WALLETS_ENABLED`. |
| `NEXT_PUBLIC_WHATSAPP_URL` | a `wa.me/…` link, or empty | empty | Empty shows "WhatsApp — coming soon". Set, it shows WhatsApp buttons, and WhatsApp becomes the first CTA. |
| `NEXT_PUBLIC_TELEGRAM_BOT_URL` | already exists | `t.me/myboardmanOfficialBot` | Telegram CTA. |

The "practice / real" banner text and the limits are written once in `lib/siteMode.ts` (BUILD_PLAN task 1.2), never typed into individual pages.

## Player pages (top level, 8)

| # | Page | URL | Job (one line) | Primary CTA | Secondary CTA |
|---|---|---|---|---|---|
| 1 | Home | `/` | What Boardman is, why you can trust it, how to start. | **Start on Telegram** (or **Start on WhatsApp** when live) | Play on the web (`/app`) |
| 2 | How it works | `/how-it-works` | 4 steps from "challenge a friend" to "winner gets paid", plus what happens if something goes wrong. | Start on Telegram/WhatsApp | See the money rules (`/money`) |
| 3 | Money | `/money` **(new)** | Putting money in, taking it out, fees, limits, practice vs real money. | Start on Telegram/WhatsApp | Get free practice money (`/get-usdc`, practice mode only) |
| 4 | Safety | `/safety` **(new)** | Who holds the money, disputes, refunds, account safety, 18+, playing responsibly. | Start on Telegram/WhatsApp | Read the FAQ |
| 5 | Games | `/games` | Every game you can play a friend on, grouped by console, phone, iMessage and table. Flagship card for the AI football league. | Challenge a friend (chat) | Watch the AI football league (`/football`) |
| 6 | FAQ | `/faq` (from `/questions`) | 28 real questions, short answers. | Start on Telegram/WhatsApp | Ask us (`/help`) |
| 7 | Help | `/help` (from `/contact`) | Get a human: Telegram, WhatsApp (soon), email, form. | Message Boardman support on Telegram | Email us |
| 8 | Play | `/app` | The web app (sign in with Telegram). | (app UI) | — |

**Utility pages.** These are not in the top nav, but they are linked from the pages, the app or chat:

- `/leaderboard` "Top players". It is linked from Home, the footer, the app and the bot, so it must stay.
- `/get-usdc` "Get free practice money". Practice mode only, and noindex. The bot links it with `?address=`.
- `/app/*` token pages: withdraw, naira, approve and wallet/setup. Opened from chat, noindex.

## Footer groups

| Group | Pages |
|---|---|
| **Play** | How it works · Money · Safety · Games · FAQ · Top players · Help |
| **AI & builders** | AI football league (`/football`) · AI agents' chess table (`/arena`) · Build an AI agent (`/builders`) · `llms.txt` |
| **Company** | About (`/about`) · Partners (`/partners`, **new**) · `boardman@playingsidequest.fun` |

`/partners` covers two things:
- **Game centres (onile).** The bot already has partner QR deep links, `t.me/<bot>?start=ctr_<CODE>`, with first-touch attribution (`config/partners.yaml`). Today only demo centres are configured.
- **MiniPay**, plus general partnership enquiries.
| **Legal** | Terms · Privacy · Delete your data |
| **Channels row** | Telegram bot · Telegram community · WhatsApp (shows "coming soon" until the flag is set) |
| **Fine print** | "18+ only. Practice mode: no real money yet." In real mode: "18+ only. Real money. Play within your limits." Plus "Boardman by sideQuest". |

## The flagship sub-site (`/football`)

AFM stays a separate world with its own `PortalNav`, because it is a different activity: an AI agent manages a club you own. Changes:

- Every `/football/*` page gets the slim Boardman header with a "← Boardman" back link and the shared footer.
- `PortalNav` goes in a second row.
- Indexed: `/football` and `/football/players` only. The rest stays noindex.
- `/football/roadmap` leaves the public site.
- How the main site links in:
  - Home: one flagship strip below the fold.
  - `/games`: the flagship card.
  - Footer.
  - Never in the hero, and never in the top nav.

## Navigation

### Mobile (main design target, 360–414 px)

```
┌──────────────────────────────────────────┐
│ [B] Boardman      (Practice mode)   [≡]  │  ← 56 px header, sticky
└──────────────────────────────────────────┘
  …page…
┌──────────────────────────────────────────┐
│ [ Start on Telegram ▸ ]  [ WhatsApp ]    │  ← sticky bottom CTA bar (64 px + safe area)
└──────────────────────────────────────────┘
```

- **The menu (≡)** opens a full-height sheet:
  - How it works, Money, Safety, Games, FAQ, Help (48 px rows)
  - A divider, then "Play on the web →" and "Top players"
  - At the bottom, the channel buttons
- **The "Practice mode" pill** taps through to `/money#practice`. It is hidden in real mode, where the header shows a small "18+" pill instead.
- **The sticky CTA bar** appears after the hero CTA scrolls out of view. It hides while the menu is open and on `/app`.
  - When WhatsApp is not live, it shows one full-width button: "Start on Telegram".
  - When WhatsApp is live, it shows two buttons: WhatsApp first, Telegram second.

### Desktop (≥ 1024 px)

```
[B] Boardman   How it works  Money  Safety  Games  FAQ      Play on web   [Start on Telegram]
```

- "Help" lives in the footer and the FAQ, so the bar stays at 5 links and 2 buttons.
- The practice pill sits next to the logo.

### Breadcrumbs and in-page links

No breadcrumbs, because the site is flat. Every player page ends with the same three-card "Next" row:
- How it works
- Money
- Safety

The current page is left out, and FAQ is added in its place.

## Primary CTA rules

1. **Channel order:** WhatsApp, when `NEXT_PUBLIC_WHATSAPP_URL` is set, because more Nigerians use it daily. Then Telegram. Then the web app. Until WhatsApp is live, Telegram is the primary CTA.
2. **Button text is a verb and a place:** "Start on Telegram", "Start on WhatsApp", "Play on the web". Never "Get started" with no place, and never "Open the app →".
3. **Deep links:** Telegram links open `t.me/<bot>?start=site_<page>` (for example `site_home` or `site_money`).
   - This is safe today. `parse_start_payload` (`src/backend/services/partners.py:148-169`) turns `site_home` into the code `SITEHOME`. No partner has that code, so it returns `unknown`. `start.py` then falls through to the normal welcome.
   - **The payload is not stored yet.** Counting players by source page needs a small backend task (BUILD_PLAN 5.3).
   - **Never use the `ctr_`, `cup_` or `m_` prefixes for site links.** The bot reserves them for game-centre partner links, cups and match links.
4. **The waitlist email form is kept as a secondary option, but only in real-money "coming soon" sections.** In practice mode, people can play right away, so the form is not needed.

## Redirect map (summary)

See `INVENTORY.md` §"Redirects the overhaul adds".

| Old | New |
|---|---|
| `/questions` | `/faq` |
| `/contact` | `/help` |
| `/app/how-to-play` | `/how-it-works` |
| `/minipay` | `/partners#minipay`* |
| `/football/roadmap` | `/football` |
| `/catalog`, `/agentic/catalog` | `/football/players` |
| `/fees`, `/pricing` | `/money#fees` |
| `/whatsapp` | `/help#whatsapp` |
| `/start` | `/how-it-works#start` |

\* Pending founder confirmation of the MiniPay listing URL.

## Final route list

```
/                       Home
/how-it-works           How it works   (+ #start, #if-something-goes-wrong)
/money                  Money          (+ #practice, #top-up, #cash-out, #fees, #limits)
/safety                 Safety         (+ #who-holds, #disputes, #refunds, #account, #age)
/games                  Games          (+ #console, #phone, #imessage, #table, #football)
/faq                    FAQ
/help                   Help           (+ #whatsapp)
/app/…                  Web app (unchanged routes)
/leaderboard            Top players
/get-usdc               Practice money helper (practice mode only, noindex)
/football/…             AI football league (flagship sub-site)
/arena                  AI agents' chess table
/builders               Builders
/partners               Partners (new; includes MiniPay)
/about                  About
/terms /privacy /data-deletion   Legal
/admin                  Operator desk (untouched)
```
