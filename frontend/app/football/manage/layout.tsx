import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Manager mode · Robot football',
  description: 'Run your club in the robot football league — the squad, the plan, the transfer window.',
  robots: { index: false, follow: false },
}

export default function ManageLayout({ children }: { children: React.ReactNode }) {
  return children
}
