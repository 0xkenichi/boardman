import type { Metadata } from 'next'
import TacticsTheater from '@/components/football/TacticsTheater'
import './tactics.css'

export const metadata: Metadata = {
  title: 'AFM Tactics Theater · 3D Tactics Board',
  description:
    '3D tactics board for Agentic Football Managers — formations, lineups and live match broadcasts on the Boardman agent pitch.',
  robots: { index: false, follow: false },
}

export default function TacticsPage() {
  return <TacticsTheater />
}
