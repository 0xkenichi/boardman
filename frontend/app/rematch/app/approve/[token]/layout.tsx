import type { Metadata } from 'next'

// One-time approve links: never indexed, never cached by a crawler.
export const metadata: Metadata = {
  title: 'Approve with passkey',
  robots: { index: false, follow: false },
}

export default function ApproveLayout({ children }: { children: React.ReactNode }) {
  return children
}
