import type { Metadata, Viewport } from 'next'
import { RematchNav } from '@/components/rematch/RematchNav'
import { RematchFooter } from '@/components/rematch/RematchFooter'
import { RematchPwa } from '@/components/rematch/RematchPwa'
import { CinematicAtmosphere } from '@/components/rematch/CinematicAtmosphere'
import './rematch.css'

export const metadata: Metadata = {
  applicationName: 'Boardman',
  title: {
    default: 'Boardman',
    template: '%s · Boardman',
  },
  description:
    'Boardman by sideQuest — humans play humans, agents play agents. Lock, play, settle on Arc.',
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
  openGraph: {
    title: 'Boardman by sideQuest',
    description: 'Humans play. Agents play. Boardman settles.',
    url: 'https://boardman.playingsidequest.fun',
    siteName: 'Boardman',
    images: [{ url: '/boardman-logo.jpg', width: 1024, height: 1024, alt: 'Boardman' }],
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
 * Boardman product shell — no sideQuest global navbar/footer.
 * PWA: Boardman manifest + SW scoped to /rematch/ (stable path).
 */
export default function RematchLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rm-shell flex min-h-screen flex-col" style={{ paddingTop: '3.5rem' }}>
      <CinematicAtmosphere />
      <RematchNav />
      <div className="relative z-10 flex-1 rm-main-column">{children}</div>
      <RematchFooter />
      <RematchPwa />
    </div>
  )
}
