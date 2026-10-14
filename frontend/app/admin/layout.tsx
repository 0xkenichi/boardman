import type { Metadata } from 'next'
import '../rematch/rematch.css'

export const metadata: Metadata = {
  title: 'The desk',
  robots: { index: false, follow: false },
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return children
}
