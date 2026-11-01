import type { Metadata } from 'next'
import { SETTLEMENT } from '@/lib/settlementChain'

export const metadata: Metadata = {
  title: 'Fund the wallet',
  description: `Get testnet USDC onto ${SETTLEMENT.label} so you can lock a stake on Boardman.`,
  alternates: { canonical: 'https://boardman.playingsidequest.fun/get-usdc' },
}

export default function GetUsdcLayout({ children }: { children: React.ReactNode }) {
  return children
}
