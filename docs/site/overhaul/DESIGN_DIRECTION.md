# Design direction

## Brief recap

- **Audience:** young Nigerian gamers, on phones, often on mobile data, often outdoors.
- **Product:** Boardman, the referee and wallet for games with friends.
- **The page must feel:** fun, fast and bold, and trustworthy enough to hand over money.
- **The page must not feel like:**
  - a sportsbook (Bet9ja and SportyBet own the green-and-odds look)
  - a crypto app (chains, coins, gradients, "web3")
  - the current paper-and-ink day-book. The founder finds it dated, and its three typefaces and serif body text slow a phone reader down.

## Recommendation: Direction A, "Game Night"

> Light, loud, and clear. A white page, near-black ink, and one electric lime that means "go". Cards and buttons look like stickers: a thick ink outline and a hard shadow you can press. It feels like a game menu, and reads like a bank statement.

**Why it wins:**

- **Sunlight and cheap screens.** A white background with near-black text (18.7:1) stays readable outdoors and on low-brightness Android phones. Dark-first designs (Direction B) wash out in sunlight.
- **Trust.** Light and plain reads as "money app". Neon on black reads as "casino".
- **Distinct.** Lime and ink is not taken by any big Nigerian sportsbook or fintech:
  - Bet9ja is green and white.
  - SportyBet is red and black.
  - OPay is green.
  - Kuda and PalmPay are purple.
  - Moniepoint is blue.
- **Cheap to render.** The sticker style is just borders and box-shadows: no images, no gradients, no blur. It ships almost no bytes.
- **Fun.** Pressable stickers, chunky type and tiny moments of motion give game-night energy without slowing the page.

### A. Palette (tokens, contrast-checked)

WCAG 2.x contrast ratios were computed with the relative-luminance formula. AA needs 4.5:1 for body text and 3:1 for large text and UI parts.

**Light theme (default)**

| Token | Hex | Use | Checked pair | Ratio |
|---|---|---|---|---|
| `--bg` | `#FFFFFF` | page | `--ink` on it | 18.72 |
| `--surface` | `#F3F5F0` | cards, bands | `--ink` on it | 17.05 |
| `--ink` | `#0B1410` | text, outlines, hard shadows | — | — |
| `--muted` | `#4A5852` | secondary text | on `--bg` / `--surface` | 7.48 / 6.81 |
| `--hairline` | `#D5DCD7` | dividers only (decorative) | on `--bg` | 1.40 (decorative, not a boundary) |
| `--field-border` | `#6B7A72` | input borders | on `--bg` | 4.51 |
| `--go` (lime) | `#C9F24D` | primary button fill, highlights, "won" | `--ink` on it | 14.52 |
| `--go-tint` | `#F4FBD9` | highlighted card bg | `--ink` / `--muted` on it | 17.51 / 6.99 |
| `--heat` (orange) | `#FF7A1A` | "live", streaks 🔥, the practice pill | `--ink` on it | 7.18 |
| `--money` (green text) | `#007A39` | amounts paid, success text, links | on `--bg` / `--surface` / `--go-tint` | 5.46 / 4.98 / 5.11 |
| `--focus` (violet) | `#5B2EFF` | focus ring, info | on `--bg` / on `--go` | 6.40 / 4.97 |
| `--violet-tint` | `#E9E4FF` | info callouts | `--ink` on it | 15.16 |
| `--danger` | `#B3261E` | errors | on `--bg` / on `#FDECEA` | 6.54 / 5.72 |
| `--warn` | `#8A5A00` | warnings text | on `--bg` / on `#FFF4D6` | 5.93 / 5.41 |

**Dark theme** (optional, follows `prefers-color-scheme`)

| Token | Hex | Checked pair | Ratio |
|---|---|---|---|
| `--bg` | `#0A110D` | `--ink` `#F2F6F3` on it | 17.52 |
| `--surface` | `#141F19` | `--ink` on it | 15.53 |
| `--muted` | `#A3B2AA` | on `--bg` / `--surface` | 8.65 / 7.67 |
| `--field-border` | `#6E7F76` | on `--bg` | 4.51 |
| `--go` | `#C9F24D` | `--bg` on it; as text on `--bg` / `--surface` | 14.83 / 14.83 / 13.14 |
| `--heat` | `#FF8A3D` | on `--bg` | 8.15 |
| `--money` | `#5FD38D` | on `--bg` | 10.18 |
| `--focus` | `#A995FF` | on `--surface` | 6.80 |
| `--danger` | `#FF7B72` | on `--bg` | 7.58 |
| `--warn` | `#FFC857` | on `--bg` | 12.42 |

In dark mode, sticker outlines and shadows use `--ink` (`#F2F6F3`), so a lime button on a dark background still has a light outline.

**Channel buttons**

| Button | Fill | Text | Ratio | Note |
|---|---|---|---|---|
| WhatsApp | `#25D366` | `--ink` | 9.44 | — |
| Telegram | `#229ED9` | `--ink` | 6.21 | **Never white text on this fill (3.02, fails).** If white text is needed, use `#1C7DB0` (4.56). |

**Rules**

1. **Lime is a fill, never a text colour on white.** Lime on white is 1.29:1. Every lime surface carries a 2px `--ink` outline, so the edge meets the 3:1 non-text contrast rule (14.5:1).
2. **One lime element per screen section.** It marks the thing to tap, and nothing else.
3. **Money amounts** use `--ink` in bold tabular numbers. Only "paid" and "won" amounts turn `--money` green.
4. **Orange means live or hot, never a warning.** Warnings use `--warn` with a ⚠ icon and words.
5. **No colour-only meaning.** Every status pairs a colour with a word and an icon.

### A. Type

- **Display:** **Bricolage Grotesque** (variable, OFL). It is chunky, a little playful, has great numerals, and reads well big.
  - Ship weights 700–800 only.
  - Latin subset as woff2, about 35 KB.
  - Use `@fontsource-variable/bricolage-grotesque` with `font-display: swap`. Preload it only on Home.
- **Text and UI:** **Inter Variable**. It is already installed (`@fontsource-variable/inter`), very legible at 16 px, and has tabular figures (`font-variant-numeric: tabular-nums`) for money.
- **Fallback stack:** `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. Fallback metrics are tuned with `size-adjust` so swaps cause no layout shift.
- **Retire:** Big Shoulders, Instrument Serif, Space Mono and JetBrains Mono. That is 4 families, roughly 150–200 KB, gone. Builder pages can keep a system monospace for code blocks: `ui-monospace, Menlo, monospace`.

**Scale.** Mobile values are first. Desktop is reached with `clamp()` from a 360 px to a 1280 px viewport.

| Role | Font, weight | Mobile size / line height | Desktop size / line height | Tracking |
|---|---|---|---|---|
| Display (hero H1) | Bricolage 800 | 44 / 46 | 76 / 72 | −0.02em |
| H1 (page) | Bricolage 800 | 36 / 40 | 56 / 58 | −0.015em |
| H2 | Bricolage 700 | 28 / 32 | 40 / 44 | −0.01em |
| H3 / card title | Inter 700 | 20 / 26 | 22 / 28 | 0 |
| Lede | Inter 400 | 18 / 28 | 20 / 30 | 0 |
| Body | Inter 400 | 16 / 25 | 17 / 27 | 0 |
| Small | Inter 500 | 14 / 20 | 14 / 20 | 0 |
| Label / pill | Inter 700 | 12 / 16 | 13 / 16 | 0.04em, sentence case (no all-caps blocks) |
| Money figure | Inter 800, tabular | 24 / 28 | 32 / 36 | −0.01em |

- **Measure:** 60–68 characters per line on desktop. Mobile paragraphs are at most 3 lines, because the copy deck is already short.

### A. Layout and shape

- **Grid:**
  - Mobile: 4 columns, 16 px gutters and margins.
  - Tablet (≥ 768): 8 columns, 24 px.
  - Desktop (≥ 1024): 12 columns, max 1120 px wide, 32 px gutters.
- **Spacing:** steps of 4, 8, 12, 16, 24, 32, 48, 64 and 96. Mobile sections use 48 px of vertical padding; desktop uses 96 px.
- **Radius:** 16 for cards, 14 for buttons, 999 for pills and chips, 10 for inputs.
- **Sticker recipe:**
  - At rest: `border: 2px solid var(--ink); box-shadow: 4px 4px 0 var(--ink)`.
  - Pressed: `translate(2px,2px)` and the shadow shrinks to `2px 2px 0`.
  - Disabled: no shadow, `--muted` outline.
  - Used only on interactive things (buttons, tappable cards). Static cards are flat, using `--surface` with no outline. Users learn quickly that "shadow means you can tap it".

### A. Components

| Component | Spec |
|---|---|
| **Header** | 56 px tall, sticky, `--bg` at 92% with a backdrop blur only where supported (and not on low-end devices: `@supports` plus `prefers-reduced-transparency`). Logo on the left. On mobile, the practice pill sits next to it. The menu button is 48×48. |
| **Mode banner** | 40 px band in `--violet-tint` with an ⓘ icon and one line ending in a link. It can be dismissed per session (sessionStorage), but it comes back on `/money` and `/safety`. Never shown in [R]. |
| **Hero** | Mobile order: pill, then the H1 (Display, max 3 lines at 360 px), the subhead (lede), the primary CTA (full width, 56 px, lime sticker), the secondary CTA (text button), the small reassurance line, and finally the phone mock. On desktop, the copy fills 6 columns and the phone mock 5. The phone mock is an **HTML/CSS chat mock-up, not an image**: it is crisp, translatable, costs no bytes, and says "Example" in small text. |
| **Primary button** | Lime fill, ink text in Inter 700 at 17 px, sticker recipe, minimum 48 px tall (56 in the hero). The icon sits on the left: a Telegram or WhatsApp glyph. |
| **Secondary button** | `--bg` fill with an ink outline and no shadow. On hover, the fill becomes `--surface`. |
| **Text button** | Ink text with an underline 2 px below and a → arrow. |
| **Trust badges** | 2×2 grid on mobile, 4 across on desktop. Each badge has a 32 px line icon (Lucide style, 2 px stroke): lock, scale, refresh-cw and user-check. It also has a bold title and one muted line. These are flat, not stickers. |
| **Step cards** | Numbered 1–4 with a big Bricolage numeral (48 px) in a lime circle and an ink outline, a title in H3 and one line of text. Mobile: horizontal scroll-snap with peeking cards (85% width) and dot indicators. Desktop: 4 across. No auto-advance. |
| **Money flow diagram** | Inline SVG (about 4 KB), drawn in tokens. Shown on Home "Money in one look", on How it works and on Money. Detailed below. |
| **Fee calculator** | One stepper input (− / + in steps of $1, plus typing) from $2 to $25. The output row reads "Pot · Fee · Winner gets", with the winner amount in `--money` at Money-figure size. It uses the same maths as `fees.py`, in a shared `lib/fees.ts` with unit tests. |
| **Fee table and limits table** | Real `<table>` elements with a caption. On mobile, rows stack into label and value pairs. |
| **Game tile** | 2 columns on mobile, 4 on desktop. A 40 px monogram circle (a letter on a tint, **no game publisher logos** — see Imagery) beside the name in Inter 600 and a tag chip. |
| **FAQ accordion** | Native `<details><summary>`, which works without JS and is accessible by default. The summary row is at least 56 px with a + icon that rotates to ×. One open at a time is not enforced. Every question has an `id` anchor and a "copy link" button for support to share. Groups are separated by an H2. |
| **Sticky mobile CTA bar** | Fixed to the bottom, 64 px plus `env(safe-area-inset-bottom)`, `--bg` with a top hairline. It holds one or two primary buttons. It appears (with a 150 ms slide) once the hero CTA leaves the viewport, which an IntersectionObserver detects. It hides on `/app` and while the menu is open. It must never cover the footer's legal text, so the footer gets matching padding at the bottom. |
| **Top players list** | Rows of avatar initial, @name, wins and a 🔥 streak in `--heat`. Skeleton rows while loading. It loads only when scrolled near, using `IntersectionObserver` and then a single fetch, with **no polling** on marketing pages. |
| **Channel row** | Telegram and WhatsApp buttons in their channel fills (contrast table above). Before WhatsApp is live, the WhatsApp slot is a dashed-outline pill reading "WhatsApp — coming soon", not a button. |
| **Callouts** | Info (violet tint and ⓘ), warning (`#FFF4D6` and ⚠), danger (`#FDECEA` and ✕). Each has a title and one line. |
| **Next row** | Three flat cards with an arrow, the full card tappable (one link each). |
| **Footer** | `--ink` background with `--bg` text, and lime on links' hover underline only. The 18+ line sits in bold at the top of the fine print. |

**Money flow diagram, in detail**

```
 YOU $10 ─┐                     ┌─► WINNER  $18.60
          ├─►  [🔒 BOARDMAN HOLDS  $20]  ─┤
FRIEND $10┘                     └─► FEE     $1.40

           draw / no-show:  [🔒 $20] ─► YOU $10 + FRIEND $10
```

- The "holds" box is a lime sticker.
- The arrows draw in sequence once when scrolled into view, at 600 ms total. With reduced motion, it shows the final state.
- An "Example" label sits in the corner.
- On mobile, the diagram stacks vertically.
- `role="img"` plus a full text alternative: "You and your friend each put in $10. Boardman holds $20. The winner gets $18.60 and the fee is $1.40. If it's a draw or nobody shows, you both get $10 back."

### A. Imagery and illustration

- **Photography (founder assets):** real young Nigerians playing. Ideas:
  - two friends on a couch with PS5 pads
  - a game-centre (onile) bench
  - a phone in hand with FC Mobile on screen
  - people reacting to a win

  Style:
  - Natural light, warm skin tones correctly exposed, candid.
  - No stock-photo handshakes.
  - **No cash, no coin piles, no dice, chips or cards, no odds boards, no crypto coins.**
  - Cropped tight, with a 2 px ink outline frame and the sticker shadow so photos match the UI.
- **Illustration:** flat two-colour stickers (ink plus lime or orange): a whistle, a lock, a trophy, a game pad, a phone, a handshake. Use them as small spot icons, 48–96 px, inline SVG. A local illustrator could extend the set. Keep it to about 12 stickers.
- **The "Boardman" character:** optional. If the founder wants a mascot, make it a simple referee hand or whistle mark, not a person, so it never looks like a real official.
- **Game logos:** do **not** use EA, Konami, Activision or Garena logos or screenshots without permission. Use text names with monogram circles.
- **Logo:** the current `boardman-logo.png` (a B with gamers and a handshake) is detailed and doesn't scale to 16–32 px. Proposal:
  - A **wordmark** in Bricolage 800.
  - A **monogram**: a "B" in a rounded square with a lock notch cut into the bowl.
  - Exports: 16, 32, 180, 192 and 512 px, an SVG and a maskable PWA icon. Founder approval is needed.

### A. Motion

- **Durations:** 120 ms for presses, 180 ms for UI, 240 ms for reveals, 600 ms maximum for the money-flow sequence. Easing: `cubic-bezier(.2,.8,.2,1)`.
- **What moves:**
  - The button press
  - The accordion open
  - The sticky bar slide
  - Step cards fading up once (a 40 ms stagger)
  - The money-flow arrows
  - A small confetti burst (CSS only, 12 particles) on the "You won" line in the hero mock, played once
- **What never moves:**
  - Scroll-jacking or pinned scroll sections (retire `BoardmanLifecycle`)
  - Parallax
  - Auto-playing carousels
  - Animated backgrounds
- **Reduced motion:** with `prefers-reduced-motion: reduce`, every animation is off and only instant state changes remain.

### A. Accessibility (target: WCAG 2.2 AA)

- **Page setup:** `lang="en-NG"`. A skip link. One H1 per page with a logical heading order.
- **Tap targets:** at least 48×48 px, with 8 px gaps between targets.
- **Focus:** a 3 px `--focus` outline with a 2 px offset on every interactive element. It is visible on lime (4.97:1) and white (6.40:1).
- **Contrast:** every text and token pair is in the tables above. No text sits on photos without a solid scrim.
- **Forms:** visible labels (not placeholder-only). Errors in text, tied to the field with `aria-describedby`. Inputs use `inputmode="numeric"` for amounts and account numbers.
- **Live data:** the top players list and the house table are not announced with `aria-live` on marketing pages, so screen readers don't hear noise.
- **Zoom and plain words:**
  - Works at 200% zoom and 320 px width with no horizontal scroll.
  - Plain language at a reading age of about 12, which the copy deck already meets.
  - Money is always written out, for example "$18.60", never shown only in a chart.
- **Testing:** axe in CI on every page; manual VoiceOver (iOS) and TalkBack (Android) passes on Home, Money and FAQ.

### A. Performance budget

Low-end Android, mobile data that costs money, often 3G or patchy 4G. The budget applies **per marketing page, first load, gzip/brotli**:

| Budget | Limit | Current Home, for reference |
|---|---|---|
| Total transfer | **≤ 350 KB** | Much higher: 3 display fonts, a pinned scroll section, live polling |
| JavaScript | **≤ 120 KB** (Next runtime included); page-specific JS ≤ 25 KB | — |
| CSS | ≤ 25 KB | `v2.css` 916 lines plus `lifecycle.css` 557 |
| Fonts | ≤ 2 files, ≤ 80 KB total | 5 families |
| Images above the fold | 0 KB required (the hero mock is HTML); optional photo ≤ 60 KB AVIF with a WebP fallback | — |
| LCP | ≤ 2.0 s on Lighthouse mobile (Moto G Power, Slow 4G) | — |
| CLS | < 0.05 | — |
| INP | < 200 ms | — |
| Requests before LCP | ≤ 8 | — |

**How we meet it:**

- **Static generation.** All marketing pages are SSG with no client data before LCP. Flags are build-time.
- **Lazy live data.** Top players and the house table load after idle and only when visible. No polling on marketing pages.
- **Lean components.** Server components by default. Client JS only for the accordion copy-link, the calculator, the sticky bar and the menu.
- **No new libraries.**
  - No icon library at runtime: icons are inline SVG.
  - No animation library: animations are CSS only.
- **Image handling.** `next/image` is off (`images.unoptimized: true`), so hand-export AVIF and WebP at 1x and 2x and set `width` and `height`.
- **Enforcement.** CI runs Lighthouse with assertions on the budget (BUILD_PLAN 7.3).

## Alternative B: "Floodlights" (dark esports)

> A night-match look. Near-black, neon mint and hot pink, wide uppercase display type. Feels like an esports overlay.

| Token | Hex | Check | Ratio |
|---|---|---|---|
| `--bg` | `#0A0A12` | ink `#F4F1FF` on it | 17.72 |
| `--surface` | `#161625` | ink / muted `#9A98B0` on it | 16.05 / 6.37 |
| `--go` mint | `#00F0A0` | `--bg` on it; as text on surface | 13.12 / 11.88 |
| `--hype` pink | `#FF3D8B` | on `--bg` / `--surface` | 5.91 / 5.35 |
| `--info` violet | `#B9A5FF` | `--bg` on it | 9.28 |

- **Type:** Unbounded (display, wide), with Inter for text.
- **Components:** glowing outlines (a 1 px mint border with a soft glow), score-bug style labels, and "VS" split-screen heroes.
- **Pros:**
  - Strong gamer appeal and very "now".
  - OLED-friendly.
  - Live football and AI-agent content looks great.
- **Cons:**
  - It reads like a betting or casino app. That is the wrong signal for "trust us with your money" and risky for the gambling question.
  - Poor in sunlight.
  - Glows cost paint time on cheap GPUs.
  - Neon text at small sizes fatigues the eye.
- **Use if:** the founder wants the AFM football league to become the face of the brand later. B could also become the theme of the `/football` sub-site only.

## Alternative C: "Owambe Pop" (warm, culture-forward)

> Warm cream, deep green, sunshine yellow and coral, with geometric adire/ankara-inspired pattern bands. Rounded friendly type. Feels like a party invite from your cousin.

| Token | Hex | Check | Ratio |
|---|---|---|---|
| `--bg` | `#FFF7E8` | ink `#1A1206` / muted `#5C4A33` | 17.41 / 7.94 |
| `--surface` | `#F3E6CC` | ink / muted | 15.00 / 6.85 |
| `--green` | `#0E7C3A` | white on it; as text on `--bg`; on `--surface` | 5.30 / 4.98 / **4.29 (large text only)** |
| `--sun` yellow | `#FFB627` | ink on it | 10.57 |
| `--coral` | `#FF6F59` | ink on it | 6.77 |
| `--orange-text` | `#B4380F` | on `--bg` | 5.61 |

- **Type:** Baloo 2 or Fredoka (rounded display), with Inter for text.
- **Imagery:** commissioned pattern bands and illustrated people.
- **Pros:**
  - Unmistakably Nigerian.
  - Warm, social and shareable.
  - Strong for WhatsApp share cards.
- **Cons:**
  - Can tip into costume or cliché.
  - Cream drifts back toward the "paper" look the founder called dated.
  - Pattern art needs a commission and adds bytes.
  - Rounded type feels younger than our 18+ audience and lowers the trust signal for money.
- **Use if:** research with players says A feels "foreign". C's pattern bands could also be borrowed as an accent in A for campaigns.

## Side-by-side

| | A Game Night (recommended) | B Floodlights | C Owambe Pop |
|---|---|---|---|
| Trust with money | ●●● | ●○○ | ●●○ |
| Fun and energy | ●●○ | ●●● | ●●● |
| Sunlight and low-end screens | ●●● | ●○○ | ●●○ |
| Performance cost | lowest | medium (glows) | medium (pattern art) |
| Distinct from sportsbooks and fintechs | ●●● | ●○○ (looks like betting) | ●●○ |
| Needs commissioned art | no | no | yes |
| Risk | can look "generic startup" if the stickers are dropped | casino signal | cliché |

## Validating the direction before the build

1. Make a one-screen mobile mock of the Home hero in each direction. It needs no code: a Figma frame, or an HTML stub in a scratch folder.
2. Show the three mocks to 8–10 players in WhatsApp or Telegram groups (18+). Ask:
   - "What does this app do?" (this is the 5-second test)
   - "Would you put ₦5,000 in it?"
   - "Which one would you share?"
3. Pick A unless it loses on the 5-second test or the ₦5,000 question.
