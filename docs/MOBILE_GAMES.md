# Mobile games on Rematch

**Status:** catalog live · product focus **after iMessage**  
**Primary title:** **FC Mobile** (`mobile.fc_mobile`)  
**Related:** `config/games/mobile.yaml`, `docs/IMESSAGE_AND_CHANNELS.md`, `PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`

---

## Rule (same as everything else)

**1v1 · finite winner · final screenshot · dual-lock USDC.**

Mobile is not a new money path. It is a **catalog category** + AI proof pack.

| Play | Settle |
|------|--------|
| On phone (FC Mobile, Free Fire 1v1, …) | Telegram / Stack API — photo of final screen |

---

## FC Mobile (flagship)

| | |
|--|--|
| `game_id` | `mobile.fc_mobile` |
| Outcome | Scoreline `H-A` (same mental model as console EA FC) |
| Proof | FT / full-time result screenshot |
| Flow | Challenge → Mobile → FC Mobile → lock → play on phone → Submit result photo |

AI hints stress **mobile UI** (not console EA FC layout).

---

## Enabled now (catalog)

| game_id | Name | Type |
|---------|------|------|
| `mobile.fc_mobile` | FC Mobile | scoreline |
| `mobile.efootball` | eFootball | scoreline |
| `mobile.nba_2k_mobile` | NBA 2K Mobile | scoreline |
| `mobile.free_fire_1v1` | Free Fire 1v1 | binary (private / clash only) |
| `mobile.cod_mobile_dm` | COD Mobile Deathmatch | binary (not BR) |
| `mobile.pubg_tdm` | PUBG Mobile TDM | binary |

**Disabled (on purpose):** open battle royale, MLBB until custom 1v1 proof is solid.

---

## Player flow (Telegram)

1. **Challenge** → stake  
2. **Where do you play?** → **📲 Mobile**  
3. Pick **FC Mobile** (or another title)  
4. Both **Lock**  
5. Play on the phone app  
6. **Submit result** → final screen photo (+ caption `2-1` or `W`/`L`)  
7. Settle + zingers  

---

## Product order

1. **iMessage** — catalog + wizard (done)  
2. **Mobile** — FC Mobile first ← **you are here**  
3. Console polish / more titles  
4. WhatsApp / SMS channel  

---

## Stack API

```bash
curl -s -H "X-Stack-Key: $STACK_API_KEY" \
  "https://HOST/api/stack/v1/games?category=mobile"
```

Create match with `"game_id": "mobile.fc_mobile"`.

---

## Next engineering (when you say go)

- [ ] Public challenges filtered by mobile  
- [ ] Per-game timeout presets from `duration_hint_min`  
- [ ] Optional “room code / friend invite” field for Free Fire / COD  
- [ ] Sample FT screenshots in `docs/proof_samples/mobile/` for AI tuning  
