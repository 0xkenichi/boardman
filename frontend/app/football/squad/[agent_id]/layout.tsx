import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Squad room · Robot football',
  description: 'A robot-managed club’s squad: players, form and the manager’s plan.',
  robots: { index: false, follow: false },
}

export default function SquadLayout({ children }: { children: React.ReactNode }) {
  return children
}
