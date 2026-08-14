import type { Metadata } from 'next'
import '../rematch/rematch.css'

export const metadata: Metadata = {
  title: 'Admin — Boardman',
  robots: { index: false, follow: false },
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return children
}
