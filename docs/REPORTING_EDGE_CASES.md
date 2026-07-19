# Reporting edge cases & mitigations

| Situation | What we do |
|-----------|------------|
| **Winner reports, loser ghosts** | Immediate wait + DM. Nudge ~30m. After **6h** with **screenshot proof** → AI verifies reporter’s photo → **payout to winner**. Silent player: **−50 $PLAY** (penalty, not a reward). |
| Only one reports **text only** (no photo) | Nudge. After 24h abandon → refund (not enough proof). |
| Nobody reports | After **24h** → cancel / refund both. |
| Both report different scorelines | **Disputed**. Both notified. AI can break ties if screenshots exist. |
| Both claim same side (home) | Dispute until fixed. |
| Scores agree, no photos | Wait for both screenshots (default). Nudge for photos. |
| Scores agree + both photos | Settle (short dispute window; skip if AI high confidence). |
| AI unreadable on no-show | **Dispute for admin** — do **not** refund away a photo-backed claim blindly. |
| File path as text | Bot rejects; attach photo. |
| Double submit | Latest report overwrites that player’s claim. |
| Draw (agreed 1-1) | Refund both. |
| Admin override | Manual resolve / dispute tools. |

## No-show policy (loser silence)

```
A reports + FT photo
    → B nudged
    → after NO_SHOW_HOURS (default 6h)
        → AI reads A's screenshot (conf ≥ 0.70)
        → winner paid from pot
        → B notified of no-show loss
```

Without a screenshot, A cannot force a win — we won't pay on text alone.

Env knobs:
- `MATCH_NO_SHOW_HOURS` (default **6**)
- `MATCH_NO_SHOW_AI_CONFIDENCE` (default **0.70**)
- `MATCH_REPORT_TIMEOUT_HOURS` (default **24**) — full abandon
- `MATCH_REPORT_NUDGE_MINUTES` (default **30**)
- `MATCH_REQUIRE_SCREENSHOTS` (default true)
- `SETTLEMENT_DISPUTE_WINDOW_MINUTES` (default 5)
- `AI_FAST_SETTLE_CONFIDENCE` (default 0.75)
