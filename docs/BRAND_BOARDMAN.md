# Brand: Boardman by sideQuest

**Status:** product rebrand (2026-08)  
**Company:** sideQuest  
**Product (consumer):** **Boardman**  
**Legacy product name:** Rematch (URLs/API may still say rematch)

## Lockup

| Use | Text |
|-----|------|
| Product | Boardman |
| Full | Boardman by sideQuest |
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
