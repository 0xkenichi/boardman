import type { Metadata } from 'next'
import { RematchNav } from '@/components/rematch/RematchNav'
import { RematchFooter } from '@/components/rematch/RematchFooter'

export const metadata: Metadata = {
  title: 'Rematch by sideQuest',
  description: 'Lock in. Play. Settle. Run it back. — 1v1 skill matches with USDC.',
  themeColor: '#050508',
  appleWebApp: {
    title: 'Rematch',
    statusBarStyle: 'black-translucent',
  },
}

/**
 * Rematch product shell — no sideQuest global navbar/footer.
 * All /rematch/* routes get Rematch chrome only.
 */
export default function RematchLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-[#050508] text-white">
      <RematchNav />
      <div className="relative z-10 flex-1">{children}</div>
      <RematchFooter />
    </div>
  )
}
