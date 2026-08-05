import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Boardman by sideQuest',
  description:
    'Digital boardman for skill 1v1s — lock in, play, settle. by sideQuest.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#050508] text-white antialiased">{children}</body>
    </html>
  )
}
