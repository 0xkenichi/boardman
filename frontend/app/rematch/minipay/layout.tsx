import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Boardman on MiniPay',
  description: 'Play for stake on Boardman from inside MiniPay.',
  alternates: { canonical: 'https://boardman.playingsidequest.fun/minipay' },
}

export default function MiniPayLayout({ children }: { children: React.ReactNode }) {
  return children
}
