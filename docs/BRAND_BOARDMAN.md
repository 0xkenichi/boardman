# Brand: Boardman by sideQuest

**Status:** product rebrand (2026-08)  
**Company:** sideQuest  
**Product (consumer):** **Boardman**  
**Former public name:** **Rematch by sideQuest** (grants, applications, partner listings)

> **Continuity note (use on site, bot, grant updates):**  
> *Boardman by sideQuest — formerly Rematch by sideQuest.*  
> Same product, same company. Name change only.

## Lockup

| Use | Text |
|-----|------|
| Product | Boardman |
| Full | Boardman by sideQuest |
| Formerly | Rematch by sideQuest |
| UI note | Formerly Rematch by sideQuest |
| Tagline | Lock in. Play. Settle. Run it back. |
| Role | Digital boardman for skill 1v1s |

## Meaning

In Nigerian game-centre culture, the **boardman** holds stakes, runs the match, and pays the winner.  
Boardman is that role as a product: dual-lock escrow + proof settle.

## What stays “Rematch”

- The **verb** / feature: rematch a rival after a match (`🔄 Rematch`)  
- Technical paths: `/rematch/*`, env `REMATCH_*`, package names (until a later migration)

## Competitors

Vs Blishcrown: they sell platform coins (BC). Boardman sells **fair custody of the pot** (Balance $ / USDC-backed) with boardman culture ownership.

## Domain

| Host | Project | Status |
|------|---------|--------|
| **boardman.playingsidequest.fun** | Vercel `rematch-web` | Added on Vercel — **needs DNS** at Unstoppable Domains |
| playingsidequest.fun/rematch | Vercel `play-sidequest` | Live (legacy path) |
| rematch-web.vercel.app | Vercel `rematch-web` | Live |

### DNS (Unstoppable Domains — current nameservers)

Domain registrar uses **Unstoppable Domains** nameservers (`ns1/ns2.unstoppabledomains.com`), not Vercel NS.

Add **one** of these records for the subdomain:

**Option A — CNAME (preferred)**  
| Type | Name / Host | Value |
|------|-------------|--------|
| `CNAME` | `boardman` | `d8b0d86327c82831.vercel-dns-017.com` |

**Option B — A record**  
| Type | Name / Host | Value |
|------|-------------|--------|
| `A` | `boardman` | `76.76.21.21` |

Then wait a few minutes and run:
```bash
vercel domains verify boardman.playingsidequest.fun --scope playingsidequest-4528s-projects
```

SSL is issued automatically by Vercel once DNS validates.

### After DNS works

- **https://boardman.playingsidequest.fun/** → Boardman marketing (`/rematch`)
- **https://boardman.playingsidequest.fun/rematch/app** → web app  
  (optional later: clean paths without `/rematch` prefix)

## Logo

| File | Use |
|------|-----|
| `/boardman-logo.jpg` · `/boardman-logo.png` | Primary mark (B + handshake + dual gamers) |
| `/boardman-logo-alt.jpg` | Alt closer to legacy R composition |
| `/rematch/icon-{180,192,512}.png` | PWA icons (Boardman) |
| `/rematch-logo.jpg` | Legacy path (mirrors primary for old links) |

## What else to ship (priority)

### Done
- [x] Brand rename Boardman by sideQuest  
- [x] Domain boardman.playingsidequest.fun  
- [x] Marketing cinema + play gallery  
- [x] Naira/USD bank top-up quotes + ops credit  
- [x] Kobox partner CTAs (on/off ramp story)  
- [x] New Boardman logo assets  

### Do next (product)
1. **Restart bot** with Boardman copy + bank env (`FIAT_*`, `KOBOX_REFERRAL_URL`)  
2. **Paste real Kobox referral URL** in env  
3. **BotFather** — display name + photo → Boardman + new logo  
4. **Fund UX polish** — one screen: “Top up Naira / Kobox / Crypto” with quotes  
5. **Ops float** — small USDC buffer for credits; document SLA  
6. **Caps + safety** — min/max top-up, daily limits, admin IDs  
7. **Mainnet settlement** — Base when ready (cheap gas); keep Arc testnet for now  
8. **Optional:** Play balance 1:1 USDC-backed (chip UX like Blishcrown, honest $)  

### Growth / polish
9. Referral / welcome credit (non-cashable or capped)  
10. Clean URLs (`boardman…/app` without `/rematch`)  
11. Custom TG bot username if available (@BoardmanBot etc.)  
12. ToS / skill-gaming disclaimer under Boardman name
