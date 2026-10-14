import type { Metadata } from 'next'
import { PortalNav } from '@/components/football/PortalNav'
import MatchBoard from '@/components/football/MatchBoard'
import '../portal.css'
import './matchboard.css'

export const metadata: Metadata = {
  title: 'Match board · Robot football',
  description:
    'Replay any recorded fixture on the 2D pitch, or read the pre-match team sheet — formations, tactics and the engine’s own movement, in the Boardman book’s style.',
  robots: { index: false, follow: false },
}

export default function TacticsPage() {
  return (
    <div className="fd-wrap">
      <PortalNav active="/football/tactics" />
      <MatchBoard />
    </div>
  )
}
