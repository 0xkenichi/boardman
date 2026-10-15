import type { Metadata } from 'next'
import { PortalNav } from '@/components/football/PortalNav'
import { PlayersBrowser } from '@/components/football/PlayersBrowser'
import '../portal.css'
import './players.css'

export const metadata: Metadata = {
  title: 'The players · Robot football',
  description:
    "Every player in Boardman's football league: original Icons and headliners from 58 nations, Nigeria's stars, and legends coming soon.",
}

export default function PlayersPage() {
  return (
    <div className="fd-wrap">
      <PortalNav active="/football/players" />
      <PlayersBrowser />
    </div>
  )
}
