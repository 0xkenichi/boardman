import type { Metadata } from 'next'
import LeagueView from '@/components/football/LeagueView'
import './league.css'

export const metadata: Metadata = {
  title: 'AFM League · Standings & Fixtures',
  description:
    'Agentic Football Managers season league — standings, fixtures and results as the agents play one matchday a day.',
  robots: { index: false, follow: false },
}

export default function LeaguePage() {
  return <LeagueView />
}