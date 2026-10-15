# Homepage claims — fact-check ledger

Scope: everything on `/` (served from `/v2`): `frontend/app/v2/layout.tsx` (title and
meta), `frontend/components/rematch/v2/BoardmanV2.tsx` (nav, hero, slip, ledger strip,
flagship, humans, arena, the book, builders, band, footer),
`frontend/components/rematch/v2/BoardmanLifecycle.tsx` ("The Match" scroll section),
`frontend/components/rematch/v2/FootballHand.tsx`, and `BoardmanJsonLd.tsx`.

Checked on 2026-10-15 against branch `site/boardman-first` (based on `main` @ 123e2cb).

The statuses are:

- **true**: the claim matches the code.
- **fixed**: the claim was false or misleading, and the copy was changed.
- **removed**: the claim was dropped.
- **hedged**: the claim is true only with a condition, so the copy now states that condition.

Defaults quoted below are code defaults, so production env vars can change them. Where
the homepage depends on a production setting, the "Needs founder input" section says so.

## Network and money

| Claim (before) | Status | Evidence | Copy now |
|---|---|---|---|
| Implied real money ("I hold the stakes", "USDC", "settled on-chain") with no testnet label in the hero | **fixed** | Only Arc Testnet (5042002) is a live settlement chain: `config/chains.yaml:16-23` (`enabled: true`, `status: live`). Arc Mainnet is `enabled: false` and `status: prep` with no escrow (`config/chains.yaml:45-60`). `CONTRACTS.md:107` says the mainnet escrow is not deployed. | A TESTNET chit sits in the nav at every width. The hero has a note: "Every stake on Boardman today is test USDC on Arc testnet — play money". The stamps read "HELD · ARC TESTNET" and "TEST USDC · ARC TESTNET". |
| Escrow link `0xD898…66Fc` labelled BoardmanEscrow (slip, ledger strip, "Read the contract", footer) | **fixed** | That address is the archived flat-fee V1 (`config/chains.yaml:33`; `docs/developers/05-contracts.md:24`: "Archived, do not use"). The live tiered escrow is `0xD382f627fB565eb96D9EFFb66B9119DD4a555847` (`config/chains.yaml:34`). | All links point at `0xD382…5847`. |
| "Every stake held in escrow and settled on-chain" (meta description, football context) | **fixed** | AFM entries, match stakes, wages and bets all move on the book-entry ledger (`src/stack/agentic/games/football_managers/season.py:524-527, 1269-1300`, `ledger.py:1-11`). | The meta description is rewritten. The flagship section says "League money is test USDC on the house ledger for now." |

## Hero and slip

| Claim | Status | Evidence | Note |
|---|---|---|---|
| "I hold both stakes so nobody has to trust anybody" | **fixed** | Wallets are Circle developer-controlled: `src/backend/circle_wallet_service.py:65-68, 198-215`. Refunds and settlements depend on Boardman's resolver key. `COMPLIANCE.md:163-191` says not to call it non-custodial. | Now reads "…so neither of you has to trust the other". Players still trust the house. |
| "I pay the winner once the result stands" | true | Settlement happens after reports, the screen check and the dispute window: `src/backend/services/clawstation_settlement.py:28-30, 109-147, 196-204`. | |
| "Agents play under the same house rules" | true | The platform fee mirrors the contract: `src/stack/agentic/economy/fees.py:25-36, 56-67`. | |
| Live table slip (LIVE / NEXT / QUIET / OFFLINE) | true | `frontend/components/rematch/house.ts`. It never says LIVE unless `/api/agentic/house-play` reports a game in play. | Unchanged. |
| Stamp "SETTLED · ARC · <1S" | **fixed** | Arc blocks are sub-second (`CONTRACTS.md:106`). Settlement, though, waits for both reports. Disputes then get a 5-minute window (`clawstation_settlement.py:28`), and the scheduler polls every 2 minutes (`src/bot/jobs/expiry.py:368, 390-396`). | Now "HELD · ARC TESTNET" (hero) and "TEST USDC · ARC TESTNET" (arena). |

## The Match (lifecycle)

| Claim | Status | Evidence | Copy now |
|---|---|---|---|
| "The money leaves both wallets at the same moment", "DUAL-LOCK · ATOMIC" | **fixed** | The two locks are sequential transactions. The creator locks first and the opponent only after `creator_locked`: `src/bot/handlers/lock_stake.py:121-127, 161-179`. | "the challenger first, then the opponent… DUAL-LOCK · ON-CHAIN" |
| Locks go into BoardmanEscrow on-chain (human flow) | true | `approve_and_create_match` / `approve_and_join_match` call the Arc escrow through Circle: `src/backend/services/clawstation_escrow.py:268-335`. | |
| "The stake sits in the contract — not with us", "NON-CUSTODIAL", "USDC HELD · NOT CUSTODIAL" | **fixed** | The wallets are custodial (see above). The stakes do sit in the escrow contract while the game is played. | "Both stakes sit in the escrow contract…", "HELD IN ESCROW", "TEST USDC HELD IN ESCROW". |
| "Fans can back a side from the spectator pool" (human match) | **removed** | Spectator betting is only for agent arena matches ("arena bets", `src/bot/handlers/approvals.py:28`). Human challenges have no spectator book. | The sentence and the spectator dots are gone from the human lifecycle. |
| "on-chain, sub-second finality. No humans touch the money" | **fixed** | Results come from both players' reports plus screenshots (`src/backend/services/match_report.py:33`). AI vision decides conflicts (`src/backend/score_verifier.py`). Disputes and low-confidence cases go to an admin (`clawstation_settlement.py:600-630`). | "Both players report… when the reports agree — or the screen reader is sure — the resolver submits… Disagreements get a short dispute window and a human referee." |
| The contract does the math: payout and tiered fee | true | The fee is computed on-chain at resolve: `contracts/contracts/core/BoardmanEscrow.sol:574-586`. The resolve call is in `clawstation_escrow.py:658`. | |
| "A public artifact… reconciled", "RECONCILED · PUBLIC" | **fixed** | Reconciliation exists, but it is internal: `src/backend/services/escrow_reconciliation.py:79-250` runs every 15 minutes (`expiry.py:404-421`) and alerts ops. There is no public receipt. Settlement transactions are public on the explorer. | "Every settlement is a transaction anyone can look up on the Arc testnet explorer… The house checks its own books against the contract balance around the clock." |
| Example receipt ($120 pot, 7%, $111.60) | true (labelled) | The example is labelled "EXAMPLE · ILLUSTRATIVE FIGURES". 7% of $120 is $8.40, and a $60 stake is in the Standard tier. | The receipt footer now says "ARC TESTNET · EXAMPLE RECEIPT · TEST USDC" instead of "< 1s". |

## Humans

| Claim | Status | Evidence | Copy now |
|---|---|---|---|
| "EA FC, Free Fire, Valorant, iMessage" | **fixed** (iMessage) | EA FC is built in (`src/backend/services/game_catalog.py:18-40`) and FC Mobile is enabled (`config/games/mobile.yaml:17`). Free Fire is at `mobile.yaml:83-98` and Valorant at `mobile.yaml:193-209`. The iMessage titles are GamePigeon games you play yourself (`config/games/imessage.yaml:1-139`). There is no iMessage app or extension in the repo. | "GamePigeon on iMessage". The flow note reads "iMESSAGE GAMES". |
| "both wallets lock before kickoff" | true | `lock_stake.py:121-179`. A match isn't in play until both stakes are locked. | "both stakes lock in escrow before kickoff" |
| "Final screen settles it" | hedged | Screenshots are required by default (`match_report.py:33`). AI vision reads the final screen (`clawstation_settlement.py:663-688`). Matching scorelines can also settle on their own, and conflicts go to an admin. | "Both of you send a photo of the final screen; when it checks out, the winner is paid." |
| "If your opponent never shows, the sweep refunds you automatically" | hedged | If the opponent never locks: the challenge expires at 24h (`src/bot/handlers/challenge.py:141`). `sweep_stale_creator_locks` refunds the creator every 2 minutes (`expiry.py:47-144, 380-389`). If nobody reports: both stakes are refunded at 24h (`match_report.py:29`, `expiry.py:214-245`). If one side goes silent after the other reports with proof, the reporter is paid at 6h (`match_report.py:31`). That case is a no-show win, not a refund. | "If your opponent never locks in, the sweep refunds your stake automatically, and if nobody reports a result, both stakes go back after 24 hours." |
| Flow step "CREATE — both wallets approve stake" | **fixed** | Each player approves and locks separately: `clawstation_escrow.py:268-335`. | Five steps now: create, lock (each stake), play, report, settle. |
| "SETTLE — winner paid, fee split on-chain" | true | `BoardmanEscrow.sol:574-586` is called through `resolveMatch`. | "fee taken on-chain" |
| Channels | **added** | The Telegram bot is `src/bot/main.py`. The web app is `frontend/app/rematch/app/`. WhatsApp is off by default (`src/channels/config.py:54-55`), and when on it only has balance, deposit, link and withdraw flows (`src/channels/core/flows/`), with no challenges. | "Play from the Telegram bot or the web app — WhatsApp soon." |
| Stake range | **added** | `CLAW_MIN_STAKE_USDC=2` and `CLAW_MAX_STAKE_USDC=25` (`src/backend/services/safety.py:23-24, 175`). | "Testnet stakes run $2 to $25 a side." |

## Arena (agents)

| Claim | Status | Evidence | Copy now |
|---|---|---|---|
| "Raja, Nero and Sheila — autonomous agents" | true | There are three contestants: `src/stack/agentic/agents/{raja,nero,sheila}/manifest.py:7-8`. Raja and Nero run Stockfish/Hybrid and Sheila runs Ethereal (`agents/*/runtime.py:3`). The LLM layer is optional. | "three house agents, each a chess engine with its own style". The "two house robots, three minds" line on `/arena` (`frontend/app/rematch/arena/page.tsx:727`) is not on the homepage. It is still inaccurate (three players). |
| "real clocks" | true | `src/stack/agentic/clock.py:18-58`. Flagging loses the game (`chess/arena.py:341-345`). | |
| "real stakes" | **fixed** | On-chain agent stakes need `BOARDMAN_AGENTIC_ONCHAIN=1`, and the demo ledger is the default (`src/stack/agentic/onchain.py:246-253`). | "Stakes and bets are test USDC." |
| "The resolver calls the result on-chain, same as a human match" | **removed** | This only holds when on-chain mode is on (`src/stack/agentic/matches.py:1131-1158`). | |
| "Back a side from the spectator pool" | true (testnet) | There is a 120s betting window before each game (`src/stack/agentic/house.py:51-57`). Betting is on by default off mainnet and off on mainnet (`src/backend/services/spectator_policy.py:47-87`). The on-chain pool is `0xd45b…9664` behind `SPECTATOR_ONCHAIN` (off by default, `src/stack/agentic/spectator_onchain.py:185-187`). Otherwise bets go to the off-chain book. | "Every game opens with a betting window: back a side from the spectator book" |
| "the creator split is baked into every pot" | true | It is 2% in both the book (`src/stack/agentic/economy/spectator.py:62`) and the pool (`contracts/contracts/core/SpectatorPool.sol:43`). | "a 2% creator cut baked into every pot" |
| "Refreshing the page does not stop the game" | true | Games run in a server process, `scripts/run_house_session.py:299-375`. The page only polls. | "The games run on the house's server, not in your browser" |

## The Book (fees)

| Claim | Status | Evidence | Copy now |
|---|---|---|---|
| Tiers: $0.50 flat per player under $5, 7% for $5–$500, 10% above | true | `contracts/contracts/core/BoardmanEscrow.sol:48-51, 80-88, 574-586`. The tiers are on the per-player stake. Exactly $5 and exactly $500 are both Standard. The off-chain mirror is `src/stack/agentic/economy/fees.py:27-35`. | Tiers are now labelled "a side". The fee calculator already used `< 5`, `<= 500`, `> 500`. |
| "One fee schedule for humans and agents alike, enforced by the contract" | hedged | The platform tiers match. In agent ledger mode, Python computes the fee rather than the contract. Agent winnings also pay a 6–8% creator fee (`economy/fees.py:1-17`). | "One platform fee schedule… written into the BoardmanEscrow contract". The contract-enforced claim is now scoped to human matches. |
| "No changing the terms mid-season" | **removed** | The owner can call `setFeeTiers` (`BoardmanEscrow.sol:434`). On the deployed V1, the fee is read at resolve time (`COMPLIANCE.md:183-185`). | |
| "No withdrawal games" | **removed** | Withdrawals are capped: $1–$50 each, $100 a day, 5 an hour (`src/backend/services/safety.py:25-30`). | |
| "the money moves the second the result lands" | **removed** | See the settlement timing above. | "the contract takes the fee itself in the same transaction that pays the winner" |
| Premium tier (over $500) | hedged | Human stakes are capped at $25 by default (`safety.py:24`). | "While we're on testnet, human stakes top out at $25 a side — Premium is for later." |

## Builders

| Claim | Status | Evidence | Copy now |
|---|---|---|---|
| "host a move webhook, take a Stack API key, register your agent" | true | API keys are issued manually (`docs/developers/09-api-keys.md`). Registration is `src/stack/agentic/api.py:930-993`. | "get a Stack API key from us" |
| Sample `POST /agents/register` with `"game": "chess"` | **fixed** | The route is `/api/stack/agentic/agents/register`. `agent_id`, `name` and `creator_id` are required, and the field is `game_ids`, a list (`api.py:913-927`). | The sample uses the real route and fields with `agentic.chess_standard`. |
| "→ 200 OK · agent queued for matchmaking", "Matchmaking… is the house's job" | **fixed** | There is no matchmaking queue (`auto_challenge` is stored but never read). The response is `{success, agent, issued_by}` (`api.py:988-992`). | "→ 200 OK · { success, agent }". The copy now says "Matches between agents are booked through the API." |
| "Games beyond chess… the arena accepts new games" | hedged | The catalog lists connect4, checkers, go9 and others as live on the generic runner (`src/stack/agentic/games/catalog.py:15-35`). The house table only plays chess. | "The house table plays chess today. Connect four, checkers, go and more already run on the same engine." |
| "SAMPLE AGENT IN builders/sample_agent/" | true | `builders/sample_agent/webhook.py` | |

## Flagship: Agentic Football Managers

| Claim | Status | Evidence | Copy now |
|---|---|---|---|
| "A football league run by agents" / "every club is run by an AI manager that picks the team" | hedged | Each matchday the House asks each manager's webhook. If there is no reply, it falls back to the deterministic playbook (`football_managers/manager_protocol.py:465-539`, `decide.py:741`). The LLM brain is optional (`llm_brain.py`). Filler clubs are auto-picked by the House (`fillers.py`, `season.py:913`). | "The managers are AI agents — a house playbook out of the box, or your own brain on a webhook — and they pick the XI and the tactics for every matchday." |
| "plays all day and night" | **removed** | There is one matchday per 24h (`season.py:96-98`). The tick runs from `scripts/keep_agents_playing.py`, a local launchd keeper, and nothing in the production entrypoint ticks it. | |
| "The managers are robots. The club is yours." / "Own a club" | hedged | You can create, adopt or buy a manager (`agent_market.py:518-655`, `api.py:2181-2209`). The owner page marks funding and autonomy as "Coming next" (`frontend/app/football/owner/page.tsx:39-87`). | No longer the headline. The copy now reads "Create, adopt or buy a manager and take the owner's seat". |
| "back a side" (football) | **removed** | The backend exists (`football_managers/betting.py`), but the UI is read-only (`frontend/components/football/BettingPots.tsx:3-8`). | |
| "build the brain" | true | `POST /football/agents/webhook` (`api.py:2057-2077`). | "your own brain on a webhook" |
| "a cast of players from 58 nations" | **fixed** (scope) | The catalog is `frontend/public/agentic/afm-catalog.json`. It has 616 players: 437 signable and 179 upcoming (125 global stars and 42 legends with licences pending, plus 12 Legends-era originals). The 58 nations are among the signable cast. The full catalog has 66 codes, which is 65 real nations once EN and ENG are merged. | "616 players on the cards: 437 you can sign today — Boardman's own cast from 58 nations — and 179 licence-pending stars and legends shown as coming soon." |
| Nigerian players | true (not on homepage) | There are 82 NG players: 35 real Nigerian players, 38 originals, 8 legends and 1 Legends-era original. | |
| Hero hand: Akanbi (NG), Kurosawa (JP), Danjuma (NG), all Icons and signable | true | `afm-catalog.json` ids `afm_og_001`, `afm_og_002` and `afm_og_006`. | |
| Ticker: real results, otherwise headliners | true | `FootballHand.tsx` reads `/api/agentic/football/season`, which returns `recent` from `simulate_match` results (`season.py:346-424`). If there are none, it lists the cast's headliners, labelled by persona title. It never shows invented scores. | |

## Numbers on the page

- Fee calculator: user-driven, and the arithmetic matches the contract.
- Lifecycle figures: labelled "EXAMPLE · ILLUSTRATIVE FIGURES".
- Slip and ledger strip: live from `useHouseTable`.
- AFM cast counts: static constant `AFM_CAST` in `BoardmanV2.tsx`, counted from the catalog. Recount it when the catalog changes.
- No volume, rating or game-count figures are shown.

## Needs founder input

1. **Production flags.** Set the arena and football copy to "on-chain" only if production sets the flags for it. Today's copy is true either way.
   - The arena needs `BOARDMAN_AGENTIC_ONCHAIN` and `SPECTATOR_ONCHAIN`.
   - Football needs its tick to be running.
2. **AFM cadence.** Is the season actually ticking in production? Nothing in `deploy/start_akash.py` ticks it. The homepage no longer claims a cadence, but `/football/watch` will look empty without the tick.
3. **Custody wording.** Any page that still says "non-custodial" contradicts `COMPLIANCE.md` and needs fixing. One example is the docstring in `src/backend/services/clawstation_escrow.py:2-6`.
4. **Stale copy elsewhere (not homepage).**
   - `/arena` says "two house robots, three minds".
   - `/builders` (`frontend/app/rematch/builders/page.tsx:88,92`) still links the archived escrow `0xD898…`.
   - `/football/watch` labels the read-only pots "Live · pots".
5. **Backend bugs seen while checking.** These are not fixed here:
   - The audit rows in `clawstation_escrow.py:620-621, 662-663` hardcode 7%, which is wrong for Pocket stakes.
   - The abandon path in `expiry.py:223-237` tells players "Stakes refunded" even if `cancel_match` failed.
