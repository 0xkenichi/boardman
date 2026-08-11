import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Boardman by sideQuest',
  description:
    'Boardman by sideQuest (formerly Rematch by sideQuest) — digital boardman for skill 1v1s.',
  icons: {
    icon: [
      { url: '/boardman-logo.png', type: 'image/png' },
      { url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' }],
  },
  openGraph: {
    title: 'Boardman by sideQuest',
    description: 'Digital boardman. Lock in. Play. Settle. Run it back.',
    url: 'https://boardman.playingsidequest.fun',
    siteName: 'Boardman',
    images: [{ url: '/boardman-logo.jpg', width: 1024, height: 1024, alt: 'Boardman' }],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#050508] text-white antialiased">{children}</body>
    </html>
  )
}
