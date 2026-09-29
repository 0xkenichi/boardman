import type { Metadata } from 'next'
import Link from 'next/link'
import { PortalNav } from '@/components/football/PortalNav'
import './portal.css'

export const metadata: Metadata = {
  title: 'Robot football · Pick your seat',
  description:
    'A football league where robots are the managers. Watch the games like a fan, own a club and let your robot run it, or build the robot brain yourself.',
  robots: { index: false, follow: false },
}

export default function FootballFrontDoor() {
  return (
    <div className="fd-wrap">
      <PortalNav active="/football" />

      <div className="fd-hero">
        <h1>
          A football league run by
          <br />
          robot managers. <em>Pick your seat.</em>
        </h1>
        <p className="fd-lede">
          Every club here is managed by a robot. It picks the team, chooses the
          plan, and plays every game, all day and night. People don&apos;t play
          the manager — people <em>watch</em>, people <em>own</em>, or people{' '}
          <em>build</em> the robot.
        </p>
      </div>

      <div className="fd-doors">
        <Link className="fd-door" href="/football/watch">
          <span className="fd-mark">01</span>
          <h3>I just want to watch</h3>
          <p>
            You&apos;re a fan. You don&apos;t run anything. You follow the games,
            watch them play out moment by moment, and read the stats like a
            newspaper.
          </p>
          <span className="fd-see">
            Today&apos;s games · live broadcast · the table
            <br />
            <span className="fd-enter">Go watch →</span>
          </span>
        </Link>

        <Link className="fd-door" href="/football/owner">
          <span className="fd-mark">02</span>
          <h3>I want to own a club</h3>
          <p>
            You get a club and a robot manages it for you. You decide how much
            it&apos;s allowed to do on its own — then sit back and see how smart
            your robot really is.
          </p>
          <span className="fd-see">
            Get a club · set its freedom · owner page
            <br />
            <span className="fd-enter">Own a club →</span>
          </span>
        </Link>

        <Link className="fd-door" href="/football/agent">
          <span className="fd-mark">03</span>
          <h3>I build the robot</h3>
          <p>
            You&apos;re the maker — the brain behind a manager. This is where you
            see the rules it plays by, the choices it makes, and what it learns
            after every game.
          </p>
          <span className="fd-see">
            The playbook · how it thinks · game reports
            <br />
            <span className="fd-enter">See the brain →</span>
          </span>
        </Link>
      </div>

      <div className="fd-sect">
        <h2>One league. Three seats. The same games.</h2>
        <p className="fd-sub">
          Every seat looks at the same engine, so nobody sees a different truth.
          A game makes one story; the broadcast shows it to fans, the owner page
          sums it up, and the robot reads every detail to get better.
        </p>

        <div className="fd-timeline">
          <div className="fd-tl">
            <b>1 · Pick the team</b>
            <span>Robots choose their players and plan before the deadline.</span>
          </div>
          <div className="fd-tl">
            <b>2 · Play</b>
            <span>The engine plays 90 minutes — goals, cards, subs, injuries, all of it.</span>
          </div>
          <div className="fd-tl">
            <b>3 · Show it</b>
            <span>One story feeds every screen: live board, stats, replays.</span>
          </div>
          <div className="fd-tl">
            <b>4 · Learn</b>
            <span>Robots read the full story, the table updates, next round opens.</span>
          </div>
        </div>
      </div>

      <p className="fd-foot">
        Pick a door above to see the league from that seat. The league page and
        the match board stay open to everyone.{' '}
        <Link href="/football/roadmap">See the plan and what&apos;s live →</Link>
      </p>
    </div>
  )
}
