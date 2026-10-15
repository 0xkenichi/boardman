import type { Metadata } from 'next'

// One-time links: never indexed, never cached by a crawler.
export const metadata: Metadata = {
  title: 'Confirm withdrawal',
  robots: { index: false, follow: false },
}

export default function WithdrawLayout({ children }: { children: React.ReactNode }) {
  return children
}
