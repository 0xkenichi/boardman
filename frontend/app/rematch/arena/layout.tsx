import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'The chess table',
  description:
    'Watch the house robots play chess for stake on real clocks, and back a side from the spectator pool. Settled in USDC on Arc.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/arena' },
}

export default function ArenaLayout({ children }: { children: React.ReactNode }) {
  return children
}
