# Solid game outcome reporting

## Why text-only scores are weak

| Signal | Alone | With proof |
|--------|-------|------------|
| “I scored 2” | Easy to lie | Weak |
| Full scoreline `5-3` | Better | Still forgeable |
| FT screenshot + AI | Strong | Preferred |
| Home/away + clubs + console IDs | Disambiguates | Required for solid AI |

## Correct Telegram flow

```
/set_side <id> home          # or away
/set_team <id> home Real Madrid
/set_team <id> away Barcelona
/link_psn YourPsnId          # optional but strong
# play match
# ATTACH PHOTO in Telegram chat with caption:
/submit_score <id> 5-3
```

❌ Pasting a Mac path like `/var/folders/.../Screenshot.png` does nothing — Telegram never sees your disk.

## What AI extracts

- Final home / away goals  
- Club names (text + crest when possible)  
- Home/away labels  
- PSN / Xbox gamertags if on screen  
- Confidence score  

Context from `/set_side` and `/set_team` is injected so left/right mapping is reliable.

## Extra signals that make outcomes rock-solid

1. **Home / away declaration** (`/set_side`) before kickoff  
2. **Club names** (`/set_team`) — cross-check logos and names  
3. **Console platform + IDs** (`/link_psn`, `/link_xbox`) — match on-screen gamertags  
4. **Both players’ screenshots** — AI agreement or high-confidence single shot  
5. **Full scoreline** `home-away`, not just “my goals”  
6. **Timestamp / FT badge** on the results screen (prompt already prefers FT)  
7. **Dispute window** if claims disagree  
8. **Admin resolve** for unreadable / conflicting AI  

### Future (not all built yet)

- Auto-pull PSN/Xbox recent match via linked accounts  
- Require both screenshots before payout  
- Crest image embeddings for club ID  
- Kickoff code / lobby ID entered by both  
- Video clip of last 10s instead of still  

## Settlement priority

1. Both scorelines agree + sides set → payout  
2. AI high confidence scoreline + sides → payout  
3. Legacy “my goals” comparison → payout after window  
4. Conflict → dispute / admin  
