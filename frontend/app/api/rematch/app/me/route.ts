import { NextResponse } from 'next/server'
import { requireSession } from '@/lib/bff'
import { stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth.error
  const { session: s } = auth

  if (stackConfigured()) {
    const res = await stackFetch(
      `/api/rematch/web/wallet?profile_id=${encodeURIComponent(s.profileId)}`
    )
    if (res.ok && res.data?.success !== false) {
      const balance = Number(res.data.balance ?? 0)
      const otherBalance = Number(res.data.other_balance ?? 0)
      return NextResponse.json({
        ok: true,
        profileId: s.profileId,
        tag: res.data.gaming_tag || s.tag,
        name: res.data.display_name || s.name,
        telegramId: s.telegramId,
        balance,
        totalBalance: Number(res.data.total_balance ?? balance + otherBalance),
        otherBalance,
        otherAddress: res.data.other_address || '',
        address: res.data.address || '',
        chainId: res.data.chain_id || 'arc',
        playPoints: Number(res.data.play_points ?? 0),
        paused: Boolean(res.data.paused),
        balanceError: res.data.balance_error || null,
        demo: false,
      })
    }
  }

  // Offline / misconfigured Stack — still return session identity
  return NextResponse.json({
    ok: true,
    profileId: s.profileId,
    tag: s.tag,
    name: s.name,
    telegramId: s.telegramId,
    balance: Number(process.env.REMATCH_DEMO_BALANCE || 0),
    otherBalance: 0,
    otherAddress: '',
    address: '',
    playPoints: 0,
    demo: true,
    message: 'Connect STACK_API_URL + STACK_API_KEY for live balance',
  })
}
