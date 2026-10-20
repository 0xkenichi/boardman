# Build plan

This is the order to build the new site in. Each task says what "done" means.

**Ground rules**

- **This phase is planning only. No code is changed.** Implementation starts on a fresh branch, `site/overhaul`, cut from `integration/wave1` *after* the current security-audit branches merge. They are editing `frontend/app/rematch/app/**`, `frontend/app/api/**`, `next.config.js` (CSP) and the token pages.
- The marketing pages (phases 1–3) touch almost none of those files, so they can start as soon as the founder approves the direction.
- Phase 4 (the web app re-skin) waits for the auditors.

**Read with:** `INVENTORY.md`, `SITEMAP.md`, `COPY_DECK.md`, `DESIGN_DIRECTION.md`.

## Phase 0: decisions and inputs (blocking)

| # | Task | Owner | Done when |
|---|---|---|---|
| 0.1 | Approve direction A, or pick B or C, after the 5-second test (DESIGN_DIRECTION §Validating) | Founder | Written yes in the PR or issue |
| 0.2 | Supply the founder assets (list at the end) | Founder | Files are in `frontend/public/brand/` or a shared folder |
| 0.3 | Answer the founder questions (list at the end) | Founder | Answers merged into COPY_DECK |
| 0.4 | Counsel read of the FAQ "Is this gambling?" answer, the Safety page, and the 18+ and responsible-play lines, **before `MONEY_MODE=real`** | Founder and counsel | Signed off. Not needed to ship in practice mode. |

## Phase 1: foundations

| # | Task | Files | Acceptance |
|---|---|---|---|
| 1.1 | **Design tokens.** Add `frontend/styles/tokens.css` with direction A's light and dark tokens, spacing, radius, the sticker recipe and the type scale (with `clamp()`). | new `styles/tokens.css`; imported in `app/layout.tsx` | Every colour in the new components comes from a token. A unit test or script re-computes the contrast pairs in DESIGN_DIRECTION and fails if any drops below its stated ratio. |
| 1.2 | **Site mode and flags.** `frontend/lib/siteMode.ts` reads `NEXT_PUBLIC_MONEY_MODE`, `NEXT_PUBLIC_NAIRA_LIVE`, `NEXT_PUBLIC_PASSKEY_WALLETS` and `NEXT_PUBLIC_WHATSAPP_URL`. It exports `mode`, `nairaLive`, `passkeys`, `whatsappUrl`, the banner strings and the `LIMITS` object, so the numbers in COPY_DECK §Money live in one place. Rule: `nairaLive` is forced false unless `mode==='real'`. | new `lib/siteMode.ts` and tests in `lib/__tests__/` | With the flags unset, every page renders [P] copy. The test covers all flag combinations. No page hard-codes "$25", "$100", "₦1,000" and so on. |
| 1.3 | **Flag consistency guard.** The backend exposes a read-only `GET /api/public/site-status` returning `{real_money, naira, passkeys, whatsapp}` from `REAL_MONEY_ENABLED`, `PAYCREST_ENABLED`, `SELF_CUSTODY_WALLETS_ENABLED` and `WHATSAPP_ENABLED`. The frontend deploy script (`scripts/` frontend deploy) compares it with the `NEXT_PUBLIC_*` flags and **fails the deploy** if the site would claim more than the backend has on. | backend: new route (after `launch/arc-mainnet-humans` merges); frontend deploy script | A deploy with `MONEY_MODE=real` against a backend with `real_money=false` stops with a clear message. The reverse (backend on, site still practice) only warns. |
| 1.4 | **Fonts.** Add `@fontsource-variable/bricolage-grotesque` (check the package name and version on npm and pin it). Keep `@fontsource-variable/inter`. Remove `@fontsource-variable/big-shoulders`, `@fontsource/instrument-serif`, `@fontsource/space-mono` and `@fontsource-variable/jetbrains-mono` once no page imports them (phase 6). | `package.json`, `app/layout.tsx` | Two font files at most on any marketing page. No layout shift on swap (CLS < 0.05). |
| 1.5 | **Fee maths.** `frontend/lib/fees.ts` ports `platform_fee_for_pot` from `src/stack/agentic/economy/fees.py`. The thresholds are $0.50 flat per player for a stake under $5, 7% from $5 to $500 inclusive, and 10% above. | new `lib/fees.ts` and tests | Tests cover $2, $4.99, $5, $10, $25, $500 and $500.01. They also match the COPY_DECK example table. |
| 1.6 | **Channel links.** `lib/channels.ts` builds `{CTA}` and `{CTA2}` per SITEMAP rules. Telegram uses `t.me/<bot>?start=site_<page>`; WhatsApp uses `whatsappUrl` when set. | new `lib/channels.ts` | With [W-], Telegram is primary and there is no WhatsApp button, only a "coming soon" pill. With [W], WhatsApp is primary. Payloads never start with `ctr_`, `cup_` or `m_`. |
| 1.7 | **Games data.** A script exports the enabled games from `config/games/*.yaml` and `game_catalog.py` into `frontend/content/games.json`. Vercel builds from `frontend/` and cannot read `../config`. A CI check fails if the JSON is out of date. | new `scripts/export_site_games.py`; `frontend/content/games.json` | The Games page and the Home chips render from the JSON. Disabled games (battle royale modes and the like) are absent. |

## Phase 2: shared components

Build these in `frontend/components/site/`. They are server components unless noted.

| # | Component | Acceptance |
|---|---|---|
| 2.1 | `SiteHeader` and `MobileMenu` (client) | 56 px tall. The menu is a focus-trapped sheet, Esc closes it, and it works without JS: `<details>` fallback, or the nav is visible on no-JS. |
| 2.2 | `ModeBanner` (client, for sessionStorage dismissal) | Shows only in [P]. Comes back on `/money` and `/safety`. |
| 2.3 | `StickyCta` (client) | Shows only after the hero CTA leaves view. Respects the safe area. Hidden on `/app` and while the menu is open. The footer has matching bottom padding. |
| 2.4 | `Button`, `ChannelButton`, `TextLink` | 48 px minimum, sticker recipe, visible focus ring, channel fills per the contrast table. |
| 2.5 | `TrustStrip`, `StepCards`, `NextRow`, `Callout` | Match the DESIGN_DIRECTION specs. Step cards use scroll-snap on mobile with no JS. |
| 2.6 | `MoneyFlow` (SVG) | Has the text alternative from DESIGN_DIRECTION. The animation is off under reduced motion. Figures come from `lib/fees.ts`. |
| 2.7 | `FeeCalculator` (client), `FeeTable`, `LimitsTable` | Numbers come from `lib/fees.ts` and `lib/siteMode.ts`. Tables are real `<table>` elements with captions and stack on mobile. |
| 2.8 | `FaqAccordion` | Native `<details>`. An `id` on every item. A copy-link button (client island). Opening `/faq#who-holds-my-money` opens and scrolls to that item. |
| 2.9 | `GameGrid` | Built from `games.json`, grouped by place. No publisher logos. |
| 2.10 | `TopPlayers` (client island) | Loads only when near the viewport, makes one fetch to `/api/rematch/public`, and does not poll. Has skeleton, empty and error states with COPY_DECK text. |
| 2.11 | `SiteFooter` | Groups, channels row and fine print per [P] or [R]. |
| 2.12 | `PhoneChatMock` | HTML/CSS hero mock labelled "Example". Figures come from `lib/fees.ts`. |

## Phase 3: pages

Pages go in a new route group, `frontend/app/(site)/`, sharing one layout with `SiteHeader`, `ModeBanner`, `SiteFooter` and `StickyCta`. They replace `app/v2` and the `rematch` marketing pages.

| # | Page | Replaces | Acceptance (on top of COPY_DECK text being used word for word) |
|---|---|---|---|
| 3.1 | `/` Home | `app/v2/*`, `components/rematch/v2/*` | The 5-second test is passed (below). Hero copy and CTA show with no JS. No live data or polling above the fold. LCP ≤ 2.0 s. The flagship strip is below the fold. |
| 3.2 | `/how-it-works` | `app/rematch/how-it-works`, `app/rematch/app/how-to-play` | The `#start` and `#if-something-goes-wrong` anchors work. The refund table matches COPY_DECK. |
| 3.3 | `/money` (new) | `/get-usdc` copy, the fee slider on v2 | All 4 flag states render correctly (snapshot tests). The calculator matches `fees.ts`. |
| 3.4 | `/safety` (new) | parts of `/questions` and `/about` | The custody wording switches on [K]. The 18+ section is present in both modes. |
| 3.5 | `/games` | `app/rematch/games` | Built from `games.json`. The football flagship card and the AI chess watch card are present. |
| 3.6 | `/faq` | `app/rematch/questions` | All 28 questions. JSON-LD `FAQPage` uses the *visible* answers for the current mode only. |
| 3.7 | `/help` | `app/rematch/contact` | The form posts to the existing `/api/rematch/waitlist` (source `help-page`). The WhatsApp card follows [W]. |
| 3.8 | `/partners` (new) | `app/rematch/minipay` | MiniPay launch link `/app?host=minipay`. Game-centre section with no revenue percentage. The Proof-of-Ship checklist moves to `docs/`. |
| 3.9 | `/about` | `app/rematch/about` | Founder photo and line when supplied, a neutral line otherwise. |
| 3.10 | `/leaderboard` "Top players" | restyle `app/rematch/leaderboard` | URL unchanged, so bot links keep working. Tabs work. Empty and error copy updated. |
| 3.11 | `/get-usdc` | restyle `app/rematch/get-usdc` | `?address=` still works (`circle_faucet.py:126`). Noindex. The [R] state shows the redirect note. |
| 3.12 | 404, error, offline | `app/not-found.tsx`, `app/error.tsx`, `app/rematch/error.tsx` | One shared component. COPY_DECK §16 text. |

## Phase 4: web app re-skin and reword (after the security branches merge)

| # | Task | Acceptance |
|---|---|---|
| 4.1 | Apply the tokens and components to `app/rematch/app/*`: home, challenge, match, upload, wallet. | No change to API calls or flow logic: the diff is markup, CSS and strings only. Existing tests pass. |
| 4.2 | Make the copy changes from COPY_DECK §8. | No "USDC", "Arc", "the book" or "testnet" in visible app strings, except the wallet address line in [P]. |
| 4.3 | Hide the "BotFather /setdomain" hint unless `NODE_ENV !== 'production'`. | Not visible on prod. |
| 4.4 | Re-skin only the token pages (withdraw, naira, approve, wallet/setup). | Every safety line from COPY_DECK §8 is still present. The auditors review it. |

## Phase 5: sub-sites

| # | Task | Acceptance |
|---|---|---|
| 5.1 | `/football/*`: slim Boardman header with "← Boardman", `PortalNav` as a second row, shared footer. Make the `ManagerMarket` naira line follow the flag. | Every football page links back to `/`. `/football` and `/football/players` are indexable and in the sitemap; the rest stay noindex. |
| 5.2 | `/arena`: restyle to the tokens; update H1, subhead, bet card and offline copy (COPY_DECK §11). | Bet card copy follows [P] or [R]. No polling change in this task. |
| 5.3 | **Bot attribution (backend).** Record the `site_*` start payloads as a first-touch `source` on the profile, next to `partners.attribute_profile`, so the site can see which page led to a sign-up. | A test in `tests/` shows `site_money` stored as the source, and that partner codes are unaffected. |
| 5.4 | `/builders`: restyle only; fix any remaining "for robots" link text. | Technical content unchanged. |

## Phase 6: routing, cleanup and redirects

| # | Task | Acceptance |
|---|---|---|
| 6.1 | Add the redirects from INVENTORY §"Redirects the overhaul adds" to `next.config.js` `redirects()`: `/questions`, `/contact`, `/app/how-to-play`, `/minipay`*, `/football/roadmap`, `/catalog`, `/agentic/catalog`, `/fees`, `/pricing`, `/whatsapp` and `/start`. Also add `/v2` → `/`. | `curl -I` on each old URL returns a 308 to the new one. A test lists them (extend `lib/__tests__`). |
| 6.2 | Remove the `'/' → '/v2'` rewrite and the `toRematch()` rewrites for pages that moved to `app/(site)`. Keep the rewrites for `/app/*`, `/leaderboard`, `/get-usdc`, `/terms`, `/privacy`, `/data-deletion` and `/arena` until those pages move too. | No marketing URL changes for users, apart from the redirected ones. |
| 6.3 | Delete the retired code: `app/v2/`, `components/rematch/v2/`, `BookShell`/`book.css` (once unused), the `rematch` marketing pages that moved, `public/agentic/football-catalog.html`, `app/clawstation/page.tsx` (moved to a redirect), and the four retired fonts. | The build passes. A `rg` for the deleted imports is empty. Bundle size drops (record before and after). |
| 6.4 | **Claims re-check.** Update `docs/site/HOMEPAGE_CLAIMS.md` into `docs/site/SITE_CLAIMS.md`, covering every page, with COPY_DECK's "Facts the copy relies on" table. Before [R], check the deployed mainnet escrow's verified source for the `InvalidWinner` check. | Each claim has a file:line or explorer link. |
| 6.5 | **Banned-words test.** A test renders every player page in [P] and [R] and fails on any of these, matched as whole words and case-insensitive: `robot`, `USDC`, `testnet`, `Arc`, `non-custodial`, `on-chain`, `instant`, `licensed`, `guaranteed`, `the book`, or "escrow contract". `/builders`, `/arena` and `/get-usdc` step 3 are allow-listed. | It runs in `npm test`. |

\* `/minipay` waits on the founder's answer about the MiniPay listing URL.

## Phase 7: SEO, meta, OG and analytics

| # | Task | Acceptance |
|---|---|---|
| 7.1 | **Metadata.** Per-page `title`, `description` and `canonical` from COPY_DECK. Root `metadataBase` stays `https://boardman.playingsidequest.fun`. Drop the jargon keywords ("AI chess betting", "Arc testnet settlement", "dual-lock escrow"); use "play friends for money Nigeria", "EA FC 1v1", "eFootball challenge", "CODM 1v1", "game referee". | Every page has a unique title under 60 characters and a description under 155. |
| 7.2 | **OG images.** 1200×630 per player page with the headline on the direction-A background and the logo. Generate them at build with `opengraph-image.tsx` (`next/og`), which is static at build so it costs no runtime. Also make a square 1080×1080 version of the Home card for WhatsApp status. | Images render in the Telegram, WhatsApp and X link previews (check with each platform's debugger or a real share). Each is ≤ 200 KB. |
| 7.3 | **Lighthouse CI.** Budgets from DESIGN_DIRECTION run on `/`, `/money`, `/faq` and `/games` in a mobile config. | CI fails over budget. |
| 7.4 | **Structured data.** `Organization`, `WebSite` and `FAQPage` (mode-aware). Remove the "Arc testnet USDC settlement" lines from `BoardmanJsonLd`. | Passes the Rich Results test with no errors. |
| 7.5 | **Sitemap and robots.** `sitemap.ts` lists `/`, `/how-it-works`, `/money`, `/safety`, `/games`, `/faq`, `/help`, `/leaderboard`, `/partners`, `/about`, `/builders`, `/arena`, `/football`, `/football/players`, `/terms`, `/privacy` and `/data-deletion`. `/get-usdc` and `/app/*` token pages are out. `robots.ts` is unchanged apart from adding `/get-usdc` as noindex via metadata. | The sitemap validates, and no redirected URL is in it. |
| 7.6 | **Analytics.** The privacy page promises "no advertising or third-party analytics trackers" (`app/rematch/privacy/page.tsx:161`). So use a **first-party, cookie-free event endpoint**, `POST /api/site/event` (Next route handler). It takes `{name, page, props}` and **no IP, no user ID and no fingerprint**, rate-limits with the existing `lib/rateLimit.ts`, and stores daily counts (Supabase table `site_events_daily`). Alternatively, adopt a hosted tool, but only after updating the privacy page first. | The privacy page is updated in the same PR to describe exactly this. Events fire as listed below. The admin desk shows daily counts. |

**Analytics events**

| Event | Props | Fired when |
|---|---|---|
| `cta_click` | `channel` (telegram/whatsapp/web), `position` (hero/sticky/closing/header/card), `page` | Any channel CTA |
| `nav_click` | `to` | Header and menu links |
| `mode_banner_click` | — | The practice banner link |
| `faq_open` | `id` | An accordion item opened |
| `faq_copy_link` | `id` | Copy-link pressed |
| `fee_calc_change` | `stake_bucket` (<5, 5–10, 10–25) | Debounced calculator input |
| `game_tile_click` | `game_id` | Games grid |
| `whatsapp_soon_click` | `page` | Someone taps the "coming soon" pill. This measures demand. |
| `help_form_submit` | `ok` | The help form |
| `flagship_click` | `to` | Football strip and card |
| `top_players_view` | — | The list scrolled into view (once per page view) |

The funnel ends in the bot. Task 5.3 joins `site_<page>` payloads to sign-ups, which gives page → start → first match.

## Phase 8: QA and launch

### Acceptance gates for the whole overhaul

1. **5-second test.** 10 players, aged 18–30 and found through our Telegram community, see the Home hero for 5 seconds. At least 8 of 10 can say "you play a friend for money and Boardman holds it and pays the winner".
2. **Read-aloud test.** Every COPY_DECK page is read aloud to one teen and one non-gamer. Any sentence they stumble on is rewritten.
3. **Truth check.**
   - Every claim maps to SITE_CLAIMS (6.4).
   - The banned-words test passes (6.5).
   - No [R], [N], [K] or [W] copy is visible with the flags unset (snapshot tests).
4. **Accessibility.** axe shows 0 serious or critical issues on all player pages. Manual TalkBack and VoiceOver pass on Home, Money and FAQ. Keyboard-only path: header to CTA to FAQ to footer.
5. **Performance.** Lighthouse mobile budgets pass, and a manual check runs on a real low-end Android (e.g. Tecno or Infinix) on mobile data.
6. **Links.** No 404s from the bot's known URLs: `/leaderboard`, `/get-usdc?address=`, `/app`, `/app/withdraw/<t>`, `/app/naira/<t>`, `/app/approve/<t>`, `/app/wallet/setup?t=`, `/arena`. Every old URL in INVENTORY redirects.
7. **Both modes rendered.** A preview deploy with `MONEY_MODE=real NAIRA_LIVE=1 PASSKEY_WALLETS=1 WHATSAPP_URL=…` is reviewed by the founder *before* real money launches. This lets the [R] copy be approved ahead of time, not on launch day.

### Switching to real money (runbook excerpt to add to `DEPLOY.md`)

1. The backend has gone live (the go-live gate in `docs/payments/PAYCREST.md` and `docs/MAINNET_GOLIVE_CHECKLIST.md`).
2. Set the frontend env:
   - `NEXT_PUBLIC_MONEY_MODE=real`
   - `NEXT_PUBLIC_NAIRA_LIVE=1` only if Paycrest is on
   - `NEXT_PUBLIC_PASSKEY_WALLETS=1` only if self-custody is on
3. Deploy. The 1.3 guard must pass.
4. Spot-check `/money`, `/safety` and `/faq` against the approved preview from gate 7.
5. Turning WhatsApp on is independent: set `NEXT_PUBLIC_WHATSAPP_URL` to the official `wa.me` link and redeploy.

## Suggested order and sizing

| Step | Work | Estimate |
|---|---|---|
| 1 | Phase 0 decisions | founder, about 1 week of calendar time, in parallel with step 2 |
| 2 | Phase 1 | about 2 dev-days |
| 3 | Phase 2 | about 4 dev-days |
| 4 | Phase 3 | about 5 dev-days (Home and Money take the most) |
| 5 | Phase 6.1–6.2 and 7.1–7.5 | about 2 dev-days. Ship the marketing site in practice mode here. |
| 6 | Phase 5 | about 3 dev-days |
| 7 | Phase 4 | about 3 dev-days, after the auditors |
| 8 | Phases 6.3–6.5 and 7.6 | about 2 dev-days |
| 9 | Phase 8 | about 2 days, including tests with players |

## What we need from the founder

**Assets**

1. **Logo approval.** Approve the new wordmark and monogram (DESIGN_DIRECTION §Imagery), or send the master logo files (SVG or AI). The current `boardman-logo.png` doesn't hold up at favicon size.
2. **Photos.** 6–10 real photos of young Nigerian players (couch console, phone, game centre, a reaction to a win). Each needs signed photo releases, and every person in them must be 18+.
3. **Team.** A founder or team photo, plus one line on who runs Boardman and where (for `/about` and `/safety`).
4. **Testimonials.** 3–5 real quotes from practice-mode players, with name or handle, permission, and age 18+ confirmed. **We will not invent any.** Until they exist, the Home page uses the live Top players list as social proof.
5. **Partners.** Any partner or press logos you have permission to show (MiniPay, Paycrest, game centres).
6. **Socials.** Official social handles (X, Instagram, TikTok), if any. None are in the code today.

**Questions**

1. **WhatsApp.** The official WhatsApp number or `wa.me` link, and a target date. Is `WHATSAPP_ENABLED` already on in production? Commit 123e2cb added the switch-on script, but the repo can't show whether it ran.
2. **Support.** A support Telegram handle (the bot has no Help button), and a response time you can keep.
3. **MiniPay.** Does the MiniPay listing point at `/minipay` or at `/app?host=minipay`? This decides the redirect.
4. **Roadmap page.** Should `/football/roadmap` leave the public site, or stay as a public "what's live" page?
5. **Responsible play.** A Nigerian helpline or organisation for the responsible-play line, before real money.
6. **Real-money top-ups.** Besides naira, will players be able to send USDC directly? On which network? This sets the [R] wallet copy.
7. **Game centres.** The partner revenue share to publish, if any. Today 1.5% is only a default on demo entries in `config/partners.yaml`.
8. **Counsel.** Who reviews the gambling answer and the Safety page before [R]?
