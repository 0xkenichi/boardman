# Onile / game centers (Lagos GTM)

**Goal:** Make every onile (console / game center) a Boardman desk — QR in, stakes lock, play on their TVs or tables, settle in USDC.

**Related:** `docs/GROWTH_TOURNAMENTS_AFFILIATES.md` §3 · `docs/PHYSICAL_GAMES.md` · `docs/TOURNAMENT_MODE.md`

---

## 0. What “onile” means here

In Lagos, **onile** / game centers are shops with PS5s, Xboxes, phones, and often board games. They already:

- Rent time on consoles  
- Host informal 1v1s and side bets  
- Trust people **in the room**, not wallets  

Boardman is their **cashier + fairness layer** — not a replacement for the shop.

---

## 1. How a shop uses Boardman (player journey)

```
1. Desk shows QR (sticker / A4 / phone)
2. Both players open Telegram → Boardman bot (deep link)
3. First open stamps partner_code (e.g. IKEJA01)
4. One player: New challenge → friend at next chair / public
5. Both Lock stake (play balance / Get money if needed)
6. Play on center hardware OR physical table (Chess, Ludo, Monopoly)
7. Report result (FT photo / board photo) → settle
8. Center earns % of matched volume from platform fee (not extra tax)
```

### Deep link (QR target)

```
https://t.me/myboardmanOfficialBot?start=ctr_IKEJA01
```

| Payload | Meaning |
|---------|---------|
| `ctr_IKEJA01` | Attribute player to center IKEJA01 |
| `cup_ABC123` | Open / join that tournament cup |
| `m_XXXX` | Open public challenge (existing) |

Config: `config/partners.yaml`  
Code: `src/backend/services/partners.py`

---

## 2. Economics (v0)

| Item | Rule |
|------|------|
| Player stake | Unchanged — they see $ stake, not “shop tax” |
| Platform fee | e.g. 7–10% of pot / matched volume (as today) |
| Center cut | **1–1.5% of matched volume** from platform slice (`volume_bps: 150`) |
| Payout | Weekly USDC to owner wallet (ops manual at first) |

**Prefer:** cut from platform fee.  
**Avoid:** “+shop fee” line on the player — kills trust.

### Example

Two players lock **$5** each → matched volume **$10**.  
Center at 150 bps → **$0.15** credit to IKEJA01 ledger.

Ledger file: `data/partner_ledger.json` (until Supabase table).

---

## 3. What the shop owner needs (onboarding kit)

| Deliverable | Owner |
|-------------|--------|
| Partner code + QR PNG/sticker | You (Boardman ops) |
| 1-page “How to desk” flyer | You |
| Bot username + Get money path (Paystack/Kobox) | Product |
| WhatsApp support line | Ops |
| Optional: Friday night **cup** code | Ops `/tcreate` |

### Desk script (30 seconds)

1. Scan QR → open Boardman  
2. Get money if balance empty  
3. Challenge the person next to you  
4. Both Lock  
5. Play  
6. Both report winner  

Physical games: **Physical / Table** category (Chess, Ludo, Monopoly).

---

## 4. Tournament nights at the onile

Centers drive volume with **fixed cups**:

```
Ops: /tcreate 8 5 physical.chess Ikeja Friday Chess
  or /tcreate 8 5 EAFC Ikeja EA FC Cup
→ print cup code or QR: ?start=cup_XXXXXX
→ players /tjoin or deep link
→ when full: /tstart CODE
→ each bracket game = normal 1v1 report (ops /twinner until auto-wire)
```

Tag cup to center:

```
/tcreate 8 5 physical.ludo Friday Ludo --center=IKEJA01
```

(See bot usage; `metadata.partner_code` on tournament.)

**Dry-run:** `TOURNAMENTS_MONEY_LIVE=0` (seats only, no USDC pot lock yet).  
**Money later:** entry lock + pot payout when vault path ships.

---

## 5. Rollout plan (Lagos)

| Phase | What | Success |
|-------|------|---------|
| **0** | 2–3 friendly onile (Ikeja / Yaba / Surulere) | QR works, 5+ settled matches |
| **1** | Friday cups at one shop | Full T4/T8 dry-run then small $ |
| **2** | 10 centers, weekly USDC settle to owners | Ledger + paid flag |
| **3** | Desk Mini App + multi-TV status | Attendant creates 1v1 for seated players |

### Do not wait for

- Perfect auto-payout to center wallets  
- Multi-sig shop accounts  
- 32-player money cups  

Ship: QR → 1v1 + dry-run cups → real $ after trust.

---

## 6. Ops commands (bot)

| Command | Who | Action |
|---------|-----|--------|
| Scan `ctr_*` | Player | Attribute partner |
| `/partners` | Ops | List active centers |
| `/tcreate …` | Ops | Create cup (optional `--center=CODE`) |
| `/tlist` · Cups button | Anyone | Browse / join |
| `/tstart CODE` | Ops | Bracket live |
| `/twinner CODE R1-M0 @tag` | Ops | Advance bracket (until auto) |

---

## 7. Anti-abuse (later tighten)

- First-touch attribution (don’t steal existing partner)  
- Prefer credit when **both** players share center or challenge tagged  
- Suspend partner code if fraud  
- Cap daily credit per center  

---

## 8. Adding a real center

1. Edit `config/partners.yaml` — new `code`, name, area, `volume_bps`  
2. Restart bot  
3. Generate kit:
   ```bash
   PYTHONPATH=src:gaming:. python scripts/generate_onile_kit.py
   # or one shop:
   PYTHONPATH=src:gaming:. python scripts/generate_onile_kit.py --code IKEJA01
   ```
4. Print `data/onile_kit/<CODE>/qr.png` + hand `DESK_CARD.md`  
5. Train desk once  
6. Same weekend: dry-run cup, then small $ with `TOURNAMENTS_MONEY_LIVE=1`

Demo codes already seeded: `IKEJA01`, `YABA01`, `SURULERE01`, `LEKKI01`, `COMPUTER01`.

Generic printable: `docs/onile_kit/ONE_PAGER.md`
