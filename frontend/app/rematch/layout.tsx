import type { Metadata } from 'next'
import { RematchNav } from '@/components/rematch/RematchNav'
import { RematchFooter } from '@/components/rematch/RematchFooter'
import './rematch.css'

export const metadata: Metadata = {
  title: 'Rematch by sideQuest',
  description: 'Lock in. Play. Settle. Run it back. — 1v1 skill matches with USDC.',
  themeColor: '#07080c',
  appleWebApp: {
    title: 'Rematch',
    statusBarStyle: 'black-translucent',
  },
}

/**
 * Rematch product shell — no sideQuest global navbar/footer.
 */
export default function RematchLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rm-shell flex min-h-screen flex-col">
      <RematchNav />
      <div className="relative z-10 flex-1">{children}</div>
      <RematchFooter />
    </div>
  )
}
