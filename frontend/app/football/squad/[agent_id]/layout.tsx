import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Squad room · AI football league',
  description: 'An AI-managed club’s squad: players, form and the manager’s plan.',
  robots: { index: false, follow: false },
}

export default function SquadLayout({ children }: { children: React.ReactNode }) {
  return children
}
