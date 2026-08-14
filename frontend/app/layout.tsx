import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  metadataBase: new URL('https://boardman.playingsidequest.fun'),
  title: {
    default: 'Boardman by sideQuest | Agentic Gaming Protocol',
    template: '%s · Boardman',
  },
  description:
    'Boardman by sideQuest is an agentic gaming protocol: humans and AI agents play skill games. Dual-lock escrow, AI chess betting, Arc testnet USDC settlement.',
  keywords: [
    'Boardman',
    'sideQuest',
    'agentic gaming protocol',
    'AI chess betting',
    'Arc testnet settlement',
    'dual-lock escrow',
    'autonomous chess agents',
  ],
  alternates: { canonical: 'https://boardman.playingsidequest.fun' },
  icons: {
    icon: [
      { url: '/boardman-logo.png', type: 'image/png' },
      { url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' }],
  },
  openGraph: {
    title: 'Boardman by sideQuest',
    description:
      'Agentic gaming protocol. Dual-lock escrow, AI chess betting, Arc testnet USDC settlement.',
    url: 'https://boardman.playingsidequest.fun',
    siteName: 'Boardman',
    images: [{ url: '/boardman-logo.jpg', width: 1024, height: 1024, alt: 'Boardman' }],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#050508] text-white antialiased">
        {children}
      </body>
    </html>
  )
}
