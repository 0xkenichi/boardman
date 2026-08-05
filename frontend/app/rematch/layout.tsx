import type { Metadata, Viewport } from 'next'
import { RematchNav } from '@/components/rematch/RematchNav'
import { RematchFooter } from '@/components/rematch/RematchFooter'
import { RematchPwa } from '@/components/rematch/RematchPwa'
import { CinematicAtmosphere } from '@/components/rematch/CinematicAtmosphere'
import './rematch.css'

export const metadata: Metadata = {
  applicationName: 'Rematch',
  title: {
    default: 'Rematch',
    template: '%s · Rematch',
  },
  description: 'Lock in. Play. Settle. Run it back. — 1v1 skill matches with USDC.',
  manifest: '/rematch/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Rematch',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: [
      { url: '/rematch/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/rematch/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/rematch/icon-180.png', sizes: '180x180', type: 'image/png' }],
  },
  openGraph: {
    title: 'Rematch by sideQuest',
    description: 'Lock in. Play. Settle. Run it back.',
    url: 'https://playingsidequest.fun/rematch',
    siteName: 'Rematch',
    images: [{ url: '/rematch-logo.jpg', width: 1024, height: 1024, alt: 'Rematch' }],
  },
  other: {
    'mobile-web-app-capable': 'yes',
  },
}

export const viewport: Viewport = {
  themeColor: '#07080c',
  colorScheme: 'dark',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  viewportFit: 'cover',
}

/**
 * Rematch product shell — no sideQuest global navbar/footer.
 * PWA: Rematch-only manifest + SW scoped to /rematch/
 */
export default function RematchLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rm-shell flex min-h-screen flex-col">
      <CinematicAtmosphere />
      <RematchNav />
      <div className="relative z-10 flex-1 rm-main-column">{children}</div>
      <RematchFooter />
      <RematchPwa />
    </div>
  )
}
