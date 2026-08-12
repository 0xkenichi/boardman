# Agentic Football Managers — Player Catalog Spec

This document describes the Catalog UI and player model for the Agentic Football Managers game. It's intentionally focused and non-invasive: documentation and schema only. Implementation and DB seeding are left as discrete tasks.

## Catalog Button / Flow

- Add a `Catalog` button on the Agentic Football Managers page that navigates to `/agentic/football/catalog` (or existing catalog route).
- Catalog view: paginated list of available players.
- Each row / card shows:
  - `name` (required)
  - `rating` (numeric, e.g., 87)
  - `ranking` (current ranking position; optional)
  - `price` (cost to acquire/own)
  - `wage` (recurring pay frequency value)
  - `stars` (rarity: 1-5)
  - `stats` (goals, assists, appearances—summary)

Note: images/icons are optional and disabled by default — the canonical view shows only the name and numeric fields to avoid likeness issues.

## Legal / Likeness Guidance

- Avoid using an actual player's photographic likeness or official club badges unless you have a license.
- Displaying names alone is lower-risk but still requires legal review for real-world superstars in some jurisdictions — consult legal for final approval.
- Recommendation: default to fictionalized or aggregated names for public builds. If testing with real names, use an internal-only dataset and mark it in code/docs.

## Player Model (example)

JSON schema (concise):

```json
{
  "id": "string",
  "name": "string",
  "rating": 0,
  "ranking": 0,
  "price": 0,
  "wage": 0,
  "contract": {
    "lengthWeeks": 0,
    "renewalFrequency": "weekly|monthly"
  },
  "stars": 0,
  "stats": {
    "goals": 0,
    "assists": 0,
    "appearances": 0
  }
}
```

## Contracts, Wages, and Bankruptcy (game rules)

- Acquisition: an agent pays `price` to own a player. Ownership transfers to agent wallet.
- Contracts: players are signed on short contracts. Options:
  - Weekly contract: player expects `wage` paid every game-week.
  - Monthly contract: `wage` paid every 4 weeks.
- Agents must pay wages on each due period. If the agent cannot cover wages, they become insolvent and enter a bankruptcy state.

Bankruptcy actions (game mechanics):
- On missed payment(s) the agent receives a grace period (configurable).
- If unpaid beyond grace, agent may choose:
  - Sell player(s) on the open market (instant sale at current market value).
  - Reduce squad wages by offering contract renegotiation (player acceptance probability may depend on `stars` and recent performance).
  - Release player (forfeit any future value; reduces wage obligations immediately).

- If the agent sells a player, proceeds go to the agent wallet and can be used to pay outstanding wages or buy other players.

## Pricing, Stars, and Value Dynamics

- `stars` indicate rarity/quality (1-5). Stars are a primary UI indicator.
- `price` is the current market cost. Initially the catalog may set flat pricing rules by star (e.g., all 5-star players start at X amount), or supply varied prices.
- Player market value updates over time based on performance metrics (goals, assists, appearances). Positive performance increases `price` and sometimes `ranking`.
- Example pricing policy (configurable):
  - 5 stars: basePrice = 10000
  - 4 stars: basePrice = 5000
  - 3 stars: basePrice = 2000

These are seeds — adjust economic tuning during playtesting.

## Seed: Top 10 Example (format for DB seed)

```json
[
  { "id": "p001", "name": "Top Andre", "rating": 92, "ranking": 1, "price": 12000, "wage": 700, "stars": 5, "stats": {"goals": 12, "assists": 8, "appearances": 15} },
  { "id": "p002", "name": "M. Mbappé (sample)", "rating": 91, "ranking": 2, "price": 11500, "wage": 680, "stars": 5, "stats": {"goals": 10, "assists": 7, "appearances": 14} },
  { "id": "p003", "name": "La Min (sample)", "rating": 90, "ranking": 3, "price": 11000, "wage": 650, "stars": 5, "stats": {"goals": 9, "assists": 10, "appearances": 16} },
  { "id": "p004", "name": "Player Four", "rating": 88, "ranking": 4, "price": 8000, "wage": 500, "stars": 4, "stats": {"goals": 7, "assists": 6, "appearances": 13} },
  { "id": "p005", "name": "Player Five", "rating": 86, "ranking": 5, "price": 7000, "wage": 450, "stars": 4, "stats": {"goals": 6, "assists": 5, "appearances": 12} }
]
```

- Seed plan: produce top 100 entries in the same format and import via your existing DB seed/import script. Implementation can be delegated to a migration or seed script.

## Implementation notes / handoff

- This file is intentionally spec-only. Implementation tasks:
  - Create UI route and list components for the catalog.
  - Create `Player` model and DB migration/seed for top 100.
  - Implement contract/wage scheduler and bankruptcy flows in the backend.
  - Add admin tuning endpoints for base prices and wage policies.

If you want, I can scaffold the DB seed file and a minimal API endpoint next — or leave those tasks for when Grok (CI/agent) is available to implement heavy changes.

---

Status: high-level spec created and ready for implementation.
