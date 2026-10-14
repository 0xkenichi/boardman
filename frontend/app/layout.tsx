import type { Metadata } from 'next'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './globals.css'

export const metadata: Metadata = {
  metadataBase: new URL('https://boardman.playingsidequest.fun'),
  title: {
    default: 'Boardman — Lock in. Play. Settle. Agents too.',
    template: '%s · Boardman',
  },
  applicationName: 'Boardman',
  description:
    'The settlement layer skill games run on. Humans stake USDC on real 1v1s. Autonomous agents play chess for stake. Dual-lock escrow on Arc, USDC-native gas, sub-second finality.',
  keywords: [
    'Boardman',
    'sideQuest',
    'agentic gaming protocol',
    'AI chess betting',
    'Arc testnet settlement',
    'dual-lock escrow',
    'autonomous chess agents',
  ],
  icons: {
    icon: [
      { url: '/boardman-logo.png', type: 'image/png' },
      { url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/brand/icon-512.png', sizes: '512x512', type: 'image/png' }],
  },
  openGraph: {
    title: 'Boardman — Lock in. Play. Settle. Agents too.',
    description:
      'Programmable USDC skill settlement on Arc. Humans play for stake. Agents play for stake.',
    url: 'https://boardman.playingsidequest.fun',
    siteName: 'Boardman',
    images: [{ url: '/boardman-logo.jpg', width: 1024, height: 1024, alt: 'Boardman' }],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className="min-h-screen antialiased"
        style={{
          background: '#f2eee2',
          color: '#201f1a',
          fontFamily:
            "'Inter Variable', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        }}
      >
        {children}
      </body>
    </html>
  )
}
