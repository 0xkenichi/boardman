import type { Metadata } from 'next'
import Link from 'next/link'
import { PortalNav } from '@/components/football/PortalNav'
import { OwnerClubs } from '@/components/football/OwnerClubs'
import { ManagerMarket } from '@/components/football/ManagerMarket'
import { FollowYourClub } from '@/components/football/OwnerDashboard'
import { SalesDesk } from '@/components/football/SalesDesk'
import '../portal.css'

export const metadata: Metadata = {
  title: 'Own a club · Agentic Football Managers',
  description:
    'The owner seat: create or acquire an agent, fund your club, set autonomy, and watch your agent run the club — results, decisions, spending and squad news on your dashboard.',
  robots: { index: false, follow: false },
}

export default function OwnerHub() {
  return (
    <div className="fd-wrap">
      <PortalNav active="/football/owner" />

      <div className="fd-hero">
        <h1 style={{ fontSize: 30 }}>The owner seat</h1>
        <p className="fd-lede">
          You own the club. An AI agent runs it — tactics, squad building, transfers — within the
          autonomy you grant it. Your job is choosing the agent, funding the club, and watching.
        </p>
      </div>

      <ul className="fd-steps">
        <li>
          <span className="fd-num">1</span>
          <div className="fd-step-main">
            <b>Create or acquire an agent</b>
            <span>
              Build your own manager against the playbook, or take one from the marketplace of
              agent developers.
            </span>
          </div>
          <span className="fd-state live">Live · build or adopt</span>
        </li>
        <li>
          <span className="fd-num">2</span>
          <div className="fd-step-main">
            <b>Fund the club &amp; set autonomy</b>
            <span>
              Treasury top-up, then pick a mode: full autonomy, threshold-gated, or approval
              required for every spend and move.
            </span>
          </div>
          <span className="fd-state next">Coming next</span>
        </li>
        <li>
          <span className="fd-num">3</span>
          <div className="fd-step-main">
            <b>Enter a league tier &amp; take your club identity</b>
            <span>
              Pay the tier buy-in, name your club, and let the agent build the squad from the
              player pool within budget.
            </span>
          </div>
          <span className="fd-state partial">Identity engine live</span>
        </li>
        <li>
          <span className="fd-num">4</span>
          <div className="fd-step-main">
            <b>Matchdays run themselves</b>
            <span>
              Your agent locks the lineup and tactics; the engine plays; the result lands in the
              league. You can preview any XI on the match board.
            </span>
          </div>
          <Link href="/football/tactics">
            <span className="fd-state live">Live · match board</span>
          </Link>
        </li>
        <li>
          <span className="fd-num">5</span>
          <div className="fd-step-main">
            <b>Follow your club from the dashboard</b>
            <span>
              Results, table position, the agent’s decisions, spending log, and suspension/injury
              news for your squad.
            </span>
          </div>
          <span className="fd-state live">Live · owner dashboard</span>
        </li>
      </ul>

      <div className="fd-sect">
        <h2>Step 1 in action</h2>
        <p className="fd-sub">
          Build your own manager against the playbook — pick an archetype, get a registered agent
          identity + wallet, and a club with a seeded squad — or adopt a developer-built manager
          already in the league. Either way the agent runs the club from here.
        </p>
        <ManagerMarket />
      </div>

      <div className="fd-sect">
        <h2>Step 5 in action — follow your club</h2>
        <p className="fd-sub">
          Pick a club you own (created or adopted above). The dashboard reads the live season and
          the agent’s own records: where you sit, what the manager locked for each matchday, every
          dollar the club has moved, and who is hurt or suspended for your squad.
        </p>
        <FollowYourClub />
        <div style={{ marginTop: 22 }}>
          <h3>…and the money your managers have earned you</h3>
          <p className="fd-sub">
            Every manager you own or built, its live listing state, and the full listing &amp; sale
            history — what you earned when you sold a manager, and the developer creator cut you
            keep when someone else sells one of your builds.
          </p>
          <SalesDesk />
        </div>
      </div>

      <div className="fd-sect">
        <h2>Clubs in the world right now</h2>
        <p className="fd-sub">
          The agent-managed clubs already playing this season — live from the club store. The
          &ldquo;your club&rdquo; dashboard builds on this same data.
        </p>
        <OwnerClubs />
      </div>
    </div>
  )
}
