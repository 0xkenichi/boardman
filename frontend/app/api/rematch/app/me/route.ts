import { NextResponse } from 'next/server'
import { readSessionFromRequest } from '@/lib/session'
import { stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  // Prefer Stack balance when wired; otherwise demo numbers
  let balance = 0
  let otherBalance = 0
  let otherAddress = ''
  let address = ''
  let playPoints = 0
  let demo = !stackConfigured()

  if (stackConfigured()) {
    // Future: GET /api/stack/v1/me when available — for now try balance via custom path or skip
    const bal = await stackFetch(`/api/stack/v1/matches?noop=1`).catch(() => null)
    void bal
  }

  // Demo / offline: honest scaffold data
  if (demo) {
    balance = Number(process.env.REMATCH_DEMO_BALANCE || 12.5)
    address = '0x0412256c17cdaaaf01cdcb5cde84c8780fc98a2b'
    playPoints = 1203
  }

  return NextResponse.json({
    ok: true,
    profileId: s.profileId,
    tag: s.tag,
    name: s.name,
    telegramId: s.telegramId,
    balance,
    otherBalance,
    otherAddress,
    address,
    playPoints,
    demo,
  })
}
