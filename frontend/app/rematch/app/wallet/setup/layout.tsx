import type { Metadata } from 'next'

// Opened from one-time chat links: never indexed.
export const metadata: Metadata = {
  title: 'Set up your wallet',
  robots: { index: false, follow: false },
}

export default function WalletSetupLayout({ children }: { children: React.ReactNode }) {
  return children
}
