# Mobile games on Rematch

**Status:** catalog expanded · **FC Mobile** + Free Fire / COD / Valorant / PUBG family  
**Related:** `config/games/mobile.yaml`, `docs/WEBAPP_AND_MINIPAY.md`, `docs/IMESSAGE_AND_CHANNELS.md`

---

## Rule

**1v1 or agreed finite mode · clear final screen · screenshot settle · dual-lock USDC.**

| Use | Don’t use (enabled: false) |
|-----|----------------------------|
| Free Fire **1v1 / Clash Squad** | Free Fire classic BR rank |
| COD Mobile **DM / TDM / 1v1** | Warzone BR placement |
| PUBG / BGMI **TDM / custom 1v1** | Classic BR chicken dinner only |
| Valorant **custom 1v1 / DM (agreed)** | Full 5v5 as multi-wallet team pot |
| FC Mobile / eFootball **FT score** | — |

Battle royale is deferred until there is a house rule with a single finite winner.

---

## Enabled catalog (summary)

### Sports
- `mobile.fc_mobile` — **FC Mobile** (flagship)
- `mobile.efootball` — eFootball  
- `mobile.nba_2k_mobile` — NBA 2K Mobile  
- `mobile.8_ball_pool` — **8 Ball Pool** (Miniclip 1v1; not GamePigeon)  
- `mobile.rocket_league_sideswipe` — RL Sideswipe  

### Shooters / battle
- `mobile.free_fire_1v1`, `mobile.free_fire_cs`  
- `mobile.cod_mobile_dm`, `mobile.cod_mobile_tdm`, `mobile.cod_mobile_1v1`  
- `mobile.pubg_tdm`, `mobile.pubg_1v1`, `mobile.bgmi_tdm`  
- `mobile.valorant_1v1`, `mobile.valorant_dm`  

### Other
- Clash Royale, Brawl Stars 1v1, MLBB custom 1v1, Wild Rift custom  
- Chess, Ludo 1v1, Carrom, Asphalt 1v1, Tekken mobile  

Full list: `config/games/mobile.yaml`

---

## Telegram flow

**Challenge → 📲 Mobile → pick game → stake → lock → play on phone → final screenshot → settle**

---

## Stack API

```bash
curl -s -H "X-Stack-Key: $STACK_API_KEY" \
  "https://HOST/api/stack/v1/games?category=mobile"
```

```json
{ "game_id": "mobile.fc_mobile", "amount_usdc": 2, "creator_id": "...", "opponent_id": "..." }
```

---

## Next

1. Webapp MVP (challenge + proof upload) — `docs/WEBAPP_AND_MINIPAY.md`  
2. Telegram WebApp button  
3. MiniPay shell (Africa)  
4. Room-code field for Free Fire / COD private lobbies  
