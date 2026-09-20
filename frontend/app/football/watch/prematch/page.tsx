import type { Metadata } from 'next'
import Link from 'next/link'
import { Suspense } from 'react'
import '../../portal.css'
import '../broadcast/broadcast.css'
import './prematch.css'
import PrematchClient from './PrematchClient'

export const metadata: Metadata = {
  title: 'Pre-match board · Agentic Football Managers',
  description:
    'How this match will be played: both managers’ locked formations, tactical plans, half-time contingencies and team-sheet news — before kickoff.',
  robots: { index: false, follow: false },
}

export default function PrematchPage() {
  return (
    <div className="fd-wrap">
      <div className="fd-hero">
        <h1 style={{ fontSize: 30 }}>Pre-match board</h1>
        <p className="fd-lede">
          The team sheet and the plan: how both managers have set up, how they
          intend to react at half-time, and who sits out. The match itself
          plays out on the{' '}
          <Link href="/football/watch/broadcast">broadcast</Link>.
        </p>
      </div>
      <Suspense fallback={null}>
        <PrematchClient />
      </Suspense>
    </div>
  )
}
