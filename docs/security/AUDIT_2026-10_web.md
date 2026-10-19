# Boardman web / API security audit, 2026-10

| | |
|---|---|
| **Date** | 2026-10-20 |
| **Scope** | The FastAPI app (`src/backend/main.py` and every router it mounts), API-key auth, the geo-fence, the Next.js BFF and pages (`frontend/app/api/**`, `frontend/lib/*`, `frontend/proxy.ts`, `next.config.js`), wallet and Telegram sign-in, withdraw / approve / naira link pages, the admin desk |
| **Method** | White-box review of every route; PoC tests written before each fix; read-only, low-volume black-box checks against `boardman.playingsidequest.fun` and `boardman-api.playingsidequest.fun` (headers, CORS preflight, unauthenticated requests that change nothing); `npm audit --omit=dev`, `pip-audit` (OSV); secret-pattern scan of the tree and git history (patterns only, no values read) |
| **Base** | `70a7c64`, branch `audit/web` |
| **Result** | 1 Critical, 4 High, 5 Medium, 4 Low. All are fixed in code except WEB-06, which needs a human to rotate keys. Two fixes (WEB-13 and the Python floors) still need an install/deploy. |

The money paths reviewed in earlier waves held up. That covers the withdraw-link PIN and claim, passkey setup and approve, the deposit caller binding, the football marketplace caller rules, the webhook SSRF guard, and the session HMAC with its domain-separated nonce token. The serious problems were all in the **older surfaces that trust an API key too much**: `/api/stack/v1` and the House routes. The biggest is that any builder key can move any player's money.

## Severity table

| ID | Severity | Finding | Status |
|---|---|---|---|
| WEB-01 | **Critical** | Any builder key acts as any player on `/api/stack/v1`: create, accept, lock (custodial USDC into escrow), report and settle | Fixed |
| WEB-02 | **High** | Any builder key drives the House (schedule, open / lock / play / rematch, demo seeding, operator status) and seats other builders' agents in staked matches | Fixed |
| WEB-06 | **High** (Critical if still live) | A real-looking Telegram bot token and a Circle TEST API key are in git history | **Open: rotate** |
| WEB-13 | **High** | Next.js 16.3.1 has critical and high advisories (RCE, SSRF, cache poisoning); several Python dependencies have advisories | Fixed in manifests; deploy needed |
| WEB-03 | High | Wallet sign-in opens any profile whose *unproven* `wallet_address` / `withdrawal_wallet` matches the signer | Fixed |
| WEB-04 | Medium | No CSRF origin check on the cookie BFF; login CSRF works through a cross-site `text/plain` form; sibling subdomains are same-site | Fixed |
| WEB-05 | Medium | Geo-fence falls through from an unknown Cloudflare country (Tor `T1`) to a client-typed `x-vercel-ip-country` | Fixed (residual R6) |
| WEB-07 | Medium | Public Swagger / ReDoc / `openapi.json` (a 154 KB route map) on the production API; exception text on public health routes | Fixed |
| WEB-08 | Medium | Unauthenticated amplification (RPC fan-out, unbounded chain scan); HTML injection into admin Telegram (waitlist, Paystack metadata) | Fixed |
| WEB-10 | Medium | Settlement fetched any screenshot URL or path stored on a challenge (latent SSRF and local file read); ilike wildcards in tag lookups; RPC URL (provider key) and bot token echoed in errors | Fixed |
| WEB-09 | Low | Telegram `auth_date` that is not a number (NaN) or is in the future passes the freshness check | Fixed |
| WEB-11 | Low | Any visitor can read any party's bound wallet address and sales earnings by profile id | Fixed |
| WEB-12 | Low | Authenticated BFF answers sent `Cache-Control: public`; withdraw / naira token pages had no `no-referrer` / `no-store` | Fixed |
| WEB-14 | Low | Missing defence-in-depth: weak CSP (`unsafe-inline` / `unsafe-eval`), no HSTS / nosniff on the API host, in-memory rate limits, stateless sessions | Residual |

---

## WEB-01: builder keys can act as any player on `/api/stack/v1` (Critical)

**Where.** `src/stack/api_v1.py`. Every write takes the player from the body: `creator_id`, `opponent_id` and `profile_id`. `_require_stack_key` accepted the master key **or any builder key** and returned only a builder id, which no route checked against the player.

**Impact.** Anyone holding a builder key (a third-party developer, or a leaked key) can drain any player's custodial play wallet:

1. `POST /matches` with `{"creator_id": <victim>, "opponent_id": <attacker>, "amount_usdc": 25}`.
2. `POST /matches/{id}/accept` with `{"opponent_id": <attacker>}`.
3. `POST /matches/{id}/lock` twice, once as the victim and once as the attacker. The platform's Circle custodial wallet signs `approve_and_create_match` **for the victim**.
4. `POST /matches/{id}/report` as both players: the victim's side reports `L` and the attacker's reports `W`.
5. Settlement pays the attacker.

Step 1 can also be done as `/matches/by-tag` with the opponent's tag. Nothing in the geo-fence or the key model stood in the way. Builder keys are a documented, issued credential (`docs/developers/09-api-keys.md`).

**PoC.** In `tests/test_sec_web_audit.py`, `test_builder_key_cannot_act_for_a_player[*]` and `test_builder_key_cannot_upload_proof_as_a_player` fail with 404 or 200 on `70a7c64`.

**Fix** (`91345b4`). The v1 writes (create, by-tag, accept, lock, report, proof, settle) now go through `_require_platform_actor`, which accepts the master key only. When `X-Boardman-Caller` is present, the body id must repeat it. The BFF now sends that header on these calls (`cdcc75f`). Read routes (`health`, `metrics`, `games`, `GET /matches/{ref}`) still accept builder keys.

## WEB-02: builder keys drive the House and other builders' agents (High)

**Where.** `src/stack/agentic/api.py`. These routes used `require_stack_api_key`, so any key worked:

- `POST /house/schedule`, `/house/matches`, `/house/matches/{id}/lock`, `/house/matches/{id}/play`, `/house/rematch`
- `/agents/demo/seed`, `/demo/chess`, `/demo/game`
- `GET /house/status`, which returns the bot PID and the data path
- `POST /matches`, `/matches/{id}/lock` and `/matches/{id}/play` accepted **any two agent ids**

**Impact.**

- A builder can pause or flood the House schedule, open and settle House tables, and burn gas and bankroll.
- A builder can lock another builder's agent bankroll in a match against its own (stronger) agent and then run it.

**Fix** (`ec643cf`).

- The House and demo routes, and `GET /house/status`, now require `require_platform_admin`: the master key with no caller header. The admin desk BFF already calls them that way.
- A builder key may open, lock or play an agent match only when at least one agent is registered by that builder and no agent belongs to another builder. Platform agents (Raja, Nero, the House) are allowed as opponents, so the documented builder flow in `03-deploy-autonomous-agent.md` still works.
- **PoC:** `test_builder_key_cannot_drive_the_house[*]`, `test_builder_cannot_seat_another_builders_agent`, `test_builder_cannot_lock_or_play_someone_elses_match[*]`.

## WEB-03: wallet sign-in trusts unproven addresses (High)

**Where.** `findProfileByWallet` in `frontend/app/api/rematch/app/session/route.ts`. It checked `linked_wallet`, then `wallet_address`, then `withdrawal_wallet`, and returned the first profile (`limit=1`).

`wallet_address` is either the custodial play address or a legacy `/link_wallet` value saved **with no signature** (`src/backend/wallet_service.py:link_withdrawal_wallet`). `withdrawal_wallet` is a payout address. Players routinely set these to a friend's, a P2P merchant's or an OTC desk's EOA.

**Impact.** Whoever controls that address signs a SIWE message and is in the player's account, with their balance, bets and wallet bridge. It also causes login confusion: a player who sets *your* public address there captures your wallet sign-in.

**Fix** (`3a0b9cd`).

- Only `linked_wallet` counts. The route writes it after a `personal_sign` proof with `intent=link`.
- A wallet that two profiles claim is refused.
- Linking a wallet that another profile already holds is refused (409).
- **PoC:** `walletAuth` / `webAudit.test.mjs`, "wallet sign-in looks up linked_wallet only".

**Follow-up.** Dead code still writes `linked_wallet` with no proof: `src/backend/db_layer_blockchain.link_wallet_address`, called from `wallet_service.link_wallet` and `api_blockchain_additions.py`. Nothing mounted calls it today. Delete it.

## WEB-04: CSRF and login CSRF on the cookie BFF (Medium)

**Where.** All unsafe `/api/**` BFF routes, which authenticate with the `rematch_session` cookie (`SameSite=Lax`).

There are two gaps:

- `SameSite` is per *site*, so any origin on `*.playingsidequest.fun` is same-site and gets the cookie on POSTs.
- Login needs no cookie. The session route parses `req.json()` whatever the Content-Type, so a cross-site `<form enctype="text/plain">` can carry a valid JSON body. For Telegram mode, use a duplicate `"mode"` key to absorb the `=`. For WebApp mode, `initData` already contains `=`. This signs a victim into the attacker's account, where they may then deposit or link a wallet.

**Live check.** A `POST /api/rematch/app/session` with `Origin: https://attacker.example`, `Sec-Fetch-Site: cross-site`, `Content-Type: text/plain` and body `{"mode":"nope"}` returned `400 unknown_mode`. The body was parsed and processed; nothing changed.

**Fix** (`46662c7`).

- `frontend/lib/csrf.ts` plus `proxy.ts` (matcher now includes `/api/:path*`) refuse unsafe API requests when `Sec-Fetch-Site` is not `same-origin`/`none`, when `Origin` is not this host (or is `null`), or when the body is a form type (`text/plain`, `urlencoded`).
- Server-to-server callers (no browser headers) and `/api/rematch/paystack/webhook` (HMAC) are exempt.
- **PoC:** `webAudit.test.mjs`, the CSRF cases.

## WEB-05: geo-fence header fall-through (Medium)

**Where.** `detect_country` in `src/backend/middleware/geo_fence.py`. It returned the first *valid* value from `cf-ipcountry`, then `x-vercel-ip-country`.

**Live check.** On the API host, Cloudflare overwrites a client-typed `cf-ipcountry` (spoofing `KP` still gave 401, not 451), so the primary header is sound. But for a Tor user Cloudflare sends `T1`, which was skipped as unknown. The client's own `x-vercel-ip-country: GB` then decided the country. Nothing overwrites that header on a Cloudflare-fronted host. The result is a geo-fence bypass on money routes for builder-key traffic over Tor.

**Fix** (`6a7d85e`). The first edge header that is *present* decides, even when its value is unknown. Unknown stays unknown, so strict mode refuses it on money routes. **PoC:** `test_unknown_cloudflare_country_is_not_overridden_by_vercel_header[*]`.

**Residual (R6).** `deploy/akash/deploy.yml` exposes port 8000 `global: true`. If production is reachable through the provider ingress, bypassing Cloudflare, a client sets `cf-ipcountry` itself. Make the origin reachable only through the tunnel, or require a Cloudflare-injected secret header or Authenticated Origin Pulls.

## WEB-06: secrets in git history (High, open)

The scan printed patterns, files and commits only; no secret values were read or printed.

- A Telegram bot token pattern with high entropy and no placeholder markers appears in `src/backend/telegram_webhook.py`. It was added in `4601a32` (2026-05-18) and is gone from `HEAD` since `236d4d1`.
- A Circle `TEST_API_KEY:…:…` appears in `docs/api/CIRCLE_ESCROW_SETUP.md`. It was added in `4601a32` and removed in `1a4e318` ("slim public surface for reviewers"), which suggests the repo is or was public.

**Impact if the bot token is still live.** The Telegram login hash is keyed with the bot token, so its holder can mint a valid login payload for **any Telegram id**, including the hard-coded owner id. That opens the admin desk and every account. It can also read the bot's updates and impersonate the bot.

**Action (human).**

1. Confirm both credentials were rotated: BotFather `/revoke` for the bot, and a Circle console key roll.
2. If the repo was ever public, treat the history as leaked even after rotation. A history rewrite only matters for clones made from now on.

## WEB-07: route map and error text on the public API (Medium)

**Live check.** `GET https://boardman-api.playingsidequest.fun/docs` returned 200, and `/openapi.json` returned 200 (154 KB) with every admin and money route and body schema.

**Fix** (`2e9ff5f`).

- Docs are served only with `BOARDMAN_API_DOCS=1`, and `/` no longer advertises them.
- `/api/healthz` returns the exception class, not Supabase's message.
- `/api/stack/v0/public/board` returns `board_unavailable`.
- **PoC:** `test_api_docs_off_by_default` and `test_healthz_does_not_echo_backend_errors`.

**Residual.** `/api/health/deep` still lists process names, restarts and uptime (R14). That is low value to an attacker, but consider keying it.

## WEB-08: unauthenticated amplification and admin-chat injection (Medium)

**What was wrong.**

- `GET /api/agentic/onchain-balances?addresses=…` made one RPC call per address with no cap, on the operator's RPC key, and forwarded any `days` value to a backend `eth_getLogs` scan. `/agents/onchain_volume` also had no window cap.
- `POST /api/rematch/waitlist` had no rate limit. It pasted `name`, `note` and `telegram` unescaped into a `parse_mode=HTML` message to every admin, which allows phishing links in the admin chat.
- The Paystack webhook did the same with payer-controlled `metadata`. It showed the payer's own `credit_usdc` as "Credit due" next to "Send USDC from float", which is a social-engineering lever to over-credit. It also messaged any `metadata.telegram_id`.

**Fix** (`db8c741`, `ec643cf`).

- onchain-balances is rate limited, accepts at most 8 valid addresses and clamps `days` to 1–90. The backend clamps it too.
- The waitlist is rate limited (5 per minute per IP), escapes all fields and no longer stores the client-typed first X-Forwarded-For hop.
- The Paystack webhook escapes all fields and labels the credit "claimed by checkout (check against ₦)". It messages only numeric chat ids.

## WEB-10: settlement fetch targets, wildcards, leaked URLs (Medium)

**Screenshot refs.** `_resolve_screenshot_source` → `score_verifier._load_image_b64` fetched any `http(s)` screenshot ref with `follow_redirects=True` and no IP guard. Any other short value was `open()`ed as a file. The writers in scope store only safe refs, so this was latent. It becomes exploitable the moment any writer (Supabase RLS on `gaming.challenges`, a legacy API) lets a user set those columns.

- **Fix** (`2e9ff5f`): only `https://api.telegram.org` URLs, `data:` URLs, `evidence://` refs and Telegram file ids are accepted. Long base64 is passed on as a `data:` URL; base64 can contain `/`, so it must never reach the path branch. The bot token is redacted from download errors.

**Tag lookups.** `/matches/by-tag` and `/api/rematch/web/profile/by-tag` used `ilike(gaming_tag, <input>)`, so `%`, `_` and `*` matched an arbitrary profile.

- **Fix** (`91345b4`): the tag must match `^[a-z0-9_.]{2,32}$` and is escaped.

**RPC URLs in errors.** On-chain read errors on builder-key routes included the RPC URL, which often embeds an Alchemy or Infura key.

- **Fix** (`ec643cf`): `_safe_err` strips URLs.

**PoC:** `test_settlement_refuses_untrusted_screenshot_refs[*]`, `test_by_tag_refuses_wildcards[*]`, `test_safe_err_strips_rpc_urls`.

## WEB-09: Telegram `auth_date` parsing (Low)

**What was wrong.** `Number(data.auth_date)` turned a non-numeric value into `NaN`, which slipped past the `<` comparison. Future dates were accepted. Exploiting this needs a hash over that value, so it needs the bot token (see WEB-06); this is hardening.

**Fix** (`2a855e9`).

- `auth_date` must be a positive integer, no more than 60 s in the future, and within `TELEGRAM_LOGIN_MAX_AGE_SEC` (default and cap 24 h).
- The widget `id` must be numeric.

**Residual.** A captured widget payload replays for up to 24 h; lower the window if login UX allows. The SIWE nonce's single use is enforced by clearing a cookie, so a client that keeps the cookie can replay its own signature within 10 minutes (R2).

## WEB-11: party wallet and sales readable by anyone (Low)

**What was wrong.** `/api/agentic/football/agents/wallet` and `/sales` (and the backend routes behind them) took `party_id` from the query with no session. Live: `?party_id=x` returned 200.

**Fix** (`0d0e096`). The BFF requires a session and builds the path from the session profile. The backend binds the party to the caller: a builder key reads itself, a BFF caller reads itself, and the platform reads any. **PoC:** `test_party_wallet_and_sales_are_the_callers_own[*]`.

## WEB-12: caching of authenticated answers (Low)

**What was wrong.** `GET /api/rematch/app/session` answered with `cache-control: public, max-age=0, must-revalidate`. The withdraw and naira pages carry the link token in the path.

**Fix** (`cdcc75f`). `/api/rematch/*` is now `no-store`, and `/app/withdraw/*` and `/app/naira/*` are `no-store` with `Referrer-Policy: no-referrer`.

## WEB-13: vulnerable dependencies (High)

**npm** (`npm audit --omit=dev`):

| Package | Version | Advisories | Fix |
|---|---|---|---|
| next | 16.3.1 | 3 critical: unauthenticated RCE in Image Optimization (AVIF), in `next/og`, and on Windows hosts. 1 high: SSRF in Image Optimization. Several moderate cache-poisoning issues. | 16.3.8 |
| sharp | (transitive) | high | 0.35.5 |
| source-map-js | (transitive) | high | 1.2.2 |

Exposure today is reduced but not zero: `images.unoptimized: true`, no `next/og` import, and Vercel is Linux. `1f106c0` bumps `next@16.3.8`, `sharp@0.35.5` and `source-map-js@1.2.2` in `package.json` and the lockfile. That was a lockfile-only change, so run `npm ci` and redeploy.

**pip-audit** (OSV), with the floors raised in `src/backend/requirements.txt` (`d0646a3`):

| Package | Advisories | New floor |
|---|---|---|
| aiohttp | 3 | 3.14.4 |
| multidict | 1 | 6.9.1 |
| anyio | 2 | 4.14.2 |
| PyJWT | 28 records | 2.15.0 |
| urllib3 | 3 | 2.8.0 |
| httpx2 (openai dependency) | 3 | 2.12.0 |

`python-jose` was **removed**. Nothing imports it, and it pulled in `ecdsa` (PYSEC-2026-1325, no fix) and carried its own advisories.

The shared dev venv was not upgraded. Rebuild the image, or run `pip install -r src/backend/requirements.txt`, to pick these up.

---

## Checked and sound

- **Session cookie.** HMAC-SHA256 with `REMATCH_SESSION_SECRET`, which must be at least 32 characters in production and has no API-key fallback. Signatures are compared in constant time. The cookie is `HttpOnly; Secure; SameSite=Lax`. Expiry is 7 days, sliding, with a 30-day absolute cap. The wallet nonce token is domain-separated (`wallet-nonce.` prefix), `SameSite=Strict` and path-scoped.
- **SIWE.** Strict line-by-line parse, EIP-55 checksum, exact allow-listed host, https in production, allow-listed chain id, server nonce, 10-minute and 60 s-skew window, and a profile binding for `link`.
- **Telegram.** Widget and WebApp verification follow Telegram's spec. There is no unsigned demo hash, and demo login is off in production.
- **Admin.** The admin gate is a numeric Telegram id allowlist. Demo sessions and wallet-only sessions never pass.
- **Master key.** It never reaches the browser. No `NEXT_PUBLIC_*` key holds it, and no client component imports `stackServer`, `supabaseAdmin`, `session` or `adminAuth`. The BFF strips a smuggled `x-boardman-client-country`, and the backend honours that header only with the master key.
- **Deposit, channels, naira and self-custody routes.** Platform only. The caller is bound, the link token is the bearer and the PIN is the second factor with lockout. Each answers 404 while switched off.
- **Webhooks.** Paystack (HMAC-SHA512), Paycrest (HMAC) and WhatsApp (`X-Hub-Signature-256`) all fail closed. Circle fails closed too, but see R11. The agent webhook SSRF guard pins the IP, refuses non-global IPs and does not follow redirects.
- **CORS.** The API sends no CORS headers. A BFF preflight from a foreign origin returns no `Access-Control-Allow-Origin`. Clickjacking is covered by `X-Frame-Options: SAMEORIGIN`. HSTS on the site is 2 years with preload.
- **Source maps** are not served (403).
- **Injection.** No SQL or PostgREST filter injection is reachable from mounted routes, and there is no path traversal in the file stores; all store names are constants and evidence keys are validated. There is no `eval`, `pickle` of user data or `yaml.load`.
- **Open redirects.** None. The withdraw, approve and setup pages take no `return_to`; tokens are validated against `^[A-Za-z0-9_-]{20,128}$`.

## Residual risks and recommendations

| # | Risk | Recommendation |
|---|---|---|
| R1 | Sessions are stateless: logout only clears the cookie, a stolen cookie (including an admin's) lives up to 30 days, and there is no server-side revocation | Add a session version per profile (bump on logout or compromise); shorten admin sessions and re-check Telegram for admin actions |
| R2 | SIWE nonce single use relies on the cookie being cleared | Optional: a server-side nonce store (KV) |
| R3 | Rate limits are in memory per serverless instance | Upstash or Redis limiter for session, login, waitlist and onchain-balances |
| R4 | CSP allows `'unsafe-inline' 'unsafe-eval'`, so it offers little XSS containment | Move to nonces and drop `unsafe-eval` outside `/agentic` |
| R5 | The API host sends no HSTS or `nosniff` | Cloudflare: enable HSTS and add a response-header rule |
| R6 | The origin may be reachable without Cloudflare (Akash `global: true`), which makes `cf-ipcountry` spoofable | Tunnel-only ingress, or a shared-secret header that the geo-fence checks before trusting edge headers |
| R7 | A builder can point an agent webhook at the House's own trusted builder ports (`127.0.0.1:18761…`) | Allow the trusted-origin exception only for platform-registered agents |
| R8 | Builder keys can read `/agentic/ledger` (every balance) and v1 match participants | Scope reads to the builder's own agents, or keep them master-only |
| R9 | Dead code writes `linked_wallet` without proof, and unmounted modules build PostgREST `.or_()` filters with f-strings (`trust_safety_service`, `match_manager`, `repositories/quests`, `app_controller`) | Delete the dead modules |
| R10 | Many keyed routes return `str(exc)` (Supabase or internal messages) | A shared error mapper |
| R11 | The Circle webhook verifies an HMAC scheme that Circle does not use (Circle signs asymmetrically), so it fails closed and never credits | Implement Circle's public-key verification before relying on it |
| R12 | WhatsApp media download sends the bearer token to the URL Meta returns, with no host allowlist | Allowlist `*.fbcdn.net` / `lookaside.fbsbx.com` |
| R14 | `/api/health/deep` is public and lists processes | Acceptable, or key it |

## Tests

- **Backend.** `tests/test_sec_web_audit.py` has 51 cases; 44 of the original cases fail on `70a7c64`. The full suite reports **1154 passed, 7 skipped**, against a baseline of 1103 passed.
- **Frontend.** `frontend/lib/__tests__/webAudit.test.mjs` adds 8 cases; `node --test lib/__tests__/` reports 34 passed. `npx tsc --noEmit` is clean.
