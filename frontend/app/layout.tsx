import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Rematch by sideQuest',
  description: 'Lock in. Play. Settle. Run it back.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#050508] text-white antialiased">{children}</body>
    </html>
  )
}
