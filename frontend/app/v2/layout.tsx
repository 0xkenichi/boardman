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
    absolute: 'Boardman — A football league run by AI managers',
    template: '%s · Boardman',
  },
  description:
    'A football league where every club is run by an AI manager. Meet a cast of players from 58 nations, own a club, back a side or build the brain. Every stake held in escrow and settled on-chain.',
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
    title: 'Boardman — A football league run by AI managers',
    description:
      'Robots manage. You own the club. Players from 58 nations, settled on-chain.',
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
