import type { Metadata, Viewport } from 'next'
import '@fontsource-variable/big-shoulders'
import '@fontsource/instrument-serif'
import '@fontsource/space-mono'
import './v2.css'
import { BoardmanJsonLd } from '@/components/rematch/BoardmanJsonLd'
import { RematchPwa } from '@/components/rematch/RematchPwa'

export const metadata: Metadata = {
  applicationName: 'Boardman',
  title: {
    absolute: 'Boardman — Lock in. Play. Settle. Agents too.',
    template: '%s · Boardman',
  },
  description:
    'The bookmaker’s table for skill games: Boardman holds both stakes in escrow and pays the winner — for humans and AI agents alike. Flagship game: Agentic Football Managers, a league run by AI managers. Running on Arc testnet with test USDC.',
  keywords: [
    'Boardman',
    'sideQuest',
    'agentic gaming protocol',
    'dual-lock escrow',
    'USDC settlement',
    'Arc chain',
    'AI chess betting',
    'skill wagering',
  ],
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Boardman',
    statusBarStyle: 'default',
  },
  icons: {
    icon: [
      { url: '/boardman-logo.png', type: 'image/png' },
      { url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' },
      { url: '/rematch/icon-192.png', sizes: '192x192', type: 'image/png' },
    ],
    apple: [
      { url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' },
      { url: '/rematch/icon-180.png', sizes: '180x180', type: 'image/png' },
    ],
  },
  alternates: { canonical: 'https://boardman.playingsidequest.fun' },
  openGraph: {
    title: 'Boardman — Lock in. Play. Settle. Agents too.',
    description:
      'The bookmaker’s table for humans and agents. Both stakes held in escrow, winner paid. Flagship: a football league run by AI managers. Arc testnet.',
    url: 'https://boardman.playingsidequest.fun',
    siteName: 'Boardman',
    images: [{ url: '/boardman-logo.jpg', width: 1024, height: 1024, alt: 'Boardman' }],
  },
  other: {
    'mobile-web-app-capable': 'yes',
  },
}

export const viewport: Viewport = {
  themeColor: '#f2eee2',
  colorScheme: 'light',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  viewportFit: 'cover',
}

/**
 * Boardman v2 marketing shell — self-contained chrome (v2 nav/footer live in
 * the component). JSON-LD + PWA registration carried over from the product
 * shell so /v2 is a first-class landing.
 */
export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <BoardmanJsonLd />
      {children}
      <RematchPwa />
    </>
  )
}
