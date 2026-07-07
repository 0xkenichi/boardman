# ClawStation Compliance & Custody Posture

This document records the legal-technical controls for the ClawStation gaming
package.

## Geo-fence policy

ClawStation applies a **silent, server-side IP-based geo-fence**.  Users are
never asked to self-declare their country in a form field or onboarding prompt.

### Detection priority

The region is determined from the incoming request in this order:

1. `cf-ipcountry` header (Cloudflare)
2. `x-vercel-ip-country` header (Vercel)
3. MaxMind GeoLite2 offline database lookup against the remote IP

### Blocked regions

| Country code | Country | Status |
|--------------|---------|--------|
| `NG` | Nigeria | Blocked at launch (extensible list) |

The canonical list lives in `gaming/config/blocked_regions.json`:

```json
{
  "blocked": ["NG"],
  "version": 1
}
```

### Behavior when blocked

- **FastAPI / web**: HTTP `451 Unavailable For Legal Reasons` with body
  `{"error": "service_unavailable_in_region"}`.
- **Telegram bot**: `/start` replies with
  "ClawStation isn't available in your region yet." and skips onboarding.
- **Webhooks**: region check runs on every request; blocked regions are rejected
  before reaching business logic.

### What counts as "blocked" detection

A request is considered blocked when the detected ISO-3166-1 alpha-2 country
code matches an entry in the blocked list.  If detection fails entirely (no
header and no GeoLite2 match), the request is allowed to proceed but is logged
for monitoring.

## Custody posture

- All ClawStation wallets are **Circle Programmable Wallets, Developer-Controlled
  mode** (W3S API).
- SideQuest/ClawStation holds the entity secret and wallet sets; users do not
  manage private keys.
- Deposits arrive at a Circle-generated wallet address stored in
  `public.profiles.gaming_deposit_address`.
- The Circle webhook handler credits `wallet_balance_usdc` (or equivalent RPC)
  idempotently and writes an immutable row to `gaming.wallet_credit_audit` keyed
  by `tx_hash`.

## Blocked jurisdictions

The following jurisdictions are explicitly blocked from using ClawStation:

- Nigeria (`NG`)

The list is intentionally small for launch and will be expanded based on legal
counsel.  Expansion requires:

1. An update to `gaming/config/blocked_regions.json`.
2. A new migration or configuration change log entry.
3. Approval from the compliance owner.

## Logging & audit

- Every blocked request logs the detected country, source header, and remote IP.
- Geo-fence decisions MUST NOT be cached in a way that survives IP changes
  (e.g., do not store "allowed" in a session).
- Custody events (deposits, credits, failed webhooks) are written to
  `gaming.wallet_credit_audit` and are immutable.
