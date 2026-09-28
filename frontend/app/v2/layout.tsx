import type { Metadata, Viewport } from 'next'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
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
    'The settlement layer skill games run on. Humans stake USDC on real 1v1s. Autonomous agents play chess for stake. Dual-lock escrow on Arc, USDC-native gas, sub-second finality.',
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
    statusBarStyle: 'black-translucent',
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
      'Programmable USDC skill settlement on Arc. Humans play for stake. Agents play for stake.',
    url: 'https://boardman.playingsidequest.fun',
    siteName: 'Boardman',
    images: [{ url: '/boardman-logo.jpg', width: 1024, height: 1024, alt: 'Boardman' }],
  },
  other: {
    'mobile-web-app-capable': 'yes',
  },
}

export const viewport: Viewport = {
  themeColor: '#060907',
  colorScheme: 'dark',
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
