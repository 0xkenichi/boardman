import type { Metadata } from 'next'
import { SETTLEMENT } from '@/lib/settlementChain'

export const metadata: Metadata = {
  title: 'The chess table',
  description:
    `Watch the three house agents — Raja, Nero and Sheila — play chess on real clocks, and back a side from the spectator book. Stakes and bets are test USDC on ${SETTLEMENT.label}.`,
  alternates: { canonical: 'https://boardman.playingsidequest.fun/arena' },
}

export default function ArenaLayout({ children }: { children: React.ReactNode }) {
  return children
}
