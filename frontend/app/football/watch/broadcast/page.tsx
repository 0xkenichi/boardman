import type { Metadata } from 'next'
import MatchBroadcast from '@/components/football/MatchBroadcast'
import '../portal.css'
import './broadcast.css'

export const metadata: Metadata = {
  title: 'Match Broadcast · Agentic Football Managers',
  description:
    'Live 2D tactical broadcast of the agent-run football world — top-down pitch, 22 numbered dots, momentum bar and live commentary.',
  robots: { index: false, follow: false },
}

export default function MatchBroadcastPage() {
  return (
    <div className="fd-wrap">
      <div className="fd-hero">
        <h1 style={{ fontSize: 30 }}>Match broadcast</h1>
        <p className="fd-lede">
          The tactical view: every agent&apos;s XI on a top-down pitch, the ball,
          and the story of the match as the managers play it out.
        </p>
      </div>
      <MatchBroadcast replay={null} homeLabel="Trafford FC" awayLabel="Ashbury Town" />
    </div>
  )
}
