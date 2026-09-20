# Season Scheduling, World-Clock & Competition Structure

**Companion to:** Agentic Football Manager PRD, Technical Architecture document
**Purpose:** How time, fixtures, seasons, and competitions actually work across the platform.

---

## 1. Two clocks, not one

Your message describes two genuinely different things that are worth separating cleanly, because conflating them is where scheduling systems get fragile:

- **Calendar time** — when fixtures are scheduled to kick off. This should be the simplest possible model: **one real-world timestamp = one in-world timestamp.** No separate compressed "agent calendar" running at a different rate than reality. Agents and humans share exactly one clock. This is what makes "the match kicks off at 3pm Saturday" mean the same thing to everyone and everything on the platform.
- **Match playback duration** — how long a simulated 90-minute match takes to *broadcast* (your 1–5 minute target). This compression happens entirely inside a single match's presentation (the pacing layer from the technical architecture doc) and has nothing to do with the calendar. A match "takes" 3 broadcast minutes; the next fixture is still exactly 1 real week later, unaffected.

Keeping these separate means you never have to explain to an agent (or a bettor) what "in-world time" means relative to real time — there's only one clock. If you later want multiple matchdays to happen in a single real day (which your message also raises), that's a **scheduling density** decision (§3), not a second clock.

## 2. World-Clock Service & Schedule-Change Policy

- One service publishes: current matchday, next kickoff times, active transfer window (if any), and any schedule exceptions — this is the canonical source every agent and every UI queries, never something they compute themselves.
- **Schedule changes** (maintenance, server upgrades, unforeseen issues): published through the same service as a distinct record type, with a minimum-notice requirement before it takes effect — recommend **72 hours** as a starting default for planned maintenance (configurable), with a separate, clearly-labeled "emergency" exception path for genuinely unplanned outages that unavoidably provides less notice.
- Every schedule change is visible in the same place to humans (spectators/bettors) and agents — no separate or delayed channel for either.

## 3. Matchday Density & Concurrency

Two decisions to make explicitly rather than let emerge by accident:

- **Matches per club per real day**: recommend **one**, matching real football conventions — this keeps each match legible as an event spectators and bettors can plan around, and keeps a club's agent from needing to manage simultaneous matches.
- **Matches across the league per matchday**: scales with club count (e.g., 20 clubs → 10 fixtures). Decide whether these kick off **concurrently** (real-football-style simultaneous kickoffs, higher production complexity, authentic "matchday" feel) or **staggered through the day** (each match gets dedicated spectator/broadcast attention, easier to produce well, more like a TV schedule). Given the broadcast-quality bar you're describing, **staggered kickoffs** are the more achievable near-term choice — you can produce each match's broadcast properly rather than splitting attention ten ways at once. Concurrent kickoffs become viable once the broadcast pipeline is proven and you're not personally reviewing every match's quality.

## 4. Season Lifecycle

Standard shape, made explicit:

1. **Preseason / squad building** — agents sign free agents, review budgets.
2. **Transfer window** — timed, platform-enforced (per PRD §7.4).
3. **Regular season** — fixed number of matchdays (a double round-robin — each club plays every other club home and away — is the standard, well-understood structure to start with).
4. **Season end** — final table, promotion/relegation or expansion decisions (§5), any cup finals.
5. **Restructuring / off-season window** — new agents onboard, league sizes adjust, next season's fixture list is generated.
6. Loop.

## 5. League Expansion / Restructuring Mechanism

Needs a concrete rule, not just "it changes dynamically":

- New agents entering the platform join the **lowest tier** by default (Development tier, per the onboarding wizard) unless the league structure doesn't have room — bootstrap rule: keep adding clubs to a tier up to a defined maximum size (e.g., 20), and only create a new tier once that cap is hit.
- Recommend deciding early whether movement *between* tiers is promotion/relegation-based (performance-driven, more authentic, more meaningful for agents to optimize toward) or purely capacity-driven (clubs stay in their entry tier unless they choose to re-enter at a higher one) — this is a real design fork worth resolving deliberately since it changes what "good performance" means to an agent long-term.

## 6. Competition Structure Beyond the League

- **League** (Genesis League + future tiers) — the season-long, points-based backbone.
- **Cup competition** — knockout format, ideally open across tiers (lower-tier clubs facing top-tier ones is a natural storyline generator for the spectator/news layer, and costs little extra engine work since it reuses the same match simulation).
- **Paid-entry friendly tournaments** — off-cycle, opt-in, entry fee funding a prize pool paid to winners. Flag this clearly: this is a **third** distinct real-money structure alongside club buy-ins (PRD §12) and sportsbook betting (raised in the earlier mockup discussion) — a paid-entry contest with a payout is its own skill-contest/wagering hybrid with its own regulatory profile, and belongs in the same legal review as the other two rather than assumed to be covered by whatever clears the others.

## 7. Agent Onboarding Minimum & Builder Tournament

- Set an explicit minimum before Genesis League can launch — your instinct of **10–20 agents** is a reasonable starting target; treat it as a floor to hit, not a hard design constraint baked into the engine.
- Recommended mechanism to get there: publish the playbook/API well ahead of launch and run a **qualifying/builder period** — submitted agents play sandbox or exhibition matches (this is the same sandbox league already scoped as PRD Phase 1) before Genesis League goes live. This does three things at once: validates agents meet a baseline competence/safety bar, generates pre-launch content for the news/spectator layer, and organically produces the 10–20 threshold rather than you needing to source them directly.
- Worth deciding now whether the qualifying period has its own pass/fail bar (e.g., "must complete N sandbox matches without violating platform rules") or is purely a numbers game (first N agents that show up get in) — the former protects launch quality, the latter is simpler to run.

## 8. Open Decisions

- Concurrent vs. staggered kickoffs (§3) — recommended staggered for now, revisit once broadcast pipeline is proven.
- Promotion/relegation vs. capacity-only tier movement (§5).
- Qualifying-period pass bar vs. first-come-first-served for the builder tournament (§7).
- Prize-pool tournament structure and its legal review, alongside the two real-money structures already flagged in the PRD (§6 here; PRD §12).
