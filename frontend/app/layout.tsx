import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Boardman by sideQuest',
  description:
    'Boardman by sideQuest (formerly Rematch by sideQuest) — digital boardman for skill 1v1s.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#050508] text-white antialiased">{children}</body>
    </html>
  )
}
