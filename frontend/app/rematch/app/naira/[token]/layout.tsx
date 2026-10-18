import type { Metadata } from 'next'

// One-time links carrying identity details: never indexed, never cached.
export const metadata: Metadata = {
  title: 'Top up with naira',
  robots: { index: false, follow: false },
}

export default function NairaLayout({ children }: { children: React.ReactNode }) {
  return children
}
