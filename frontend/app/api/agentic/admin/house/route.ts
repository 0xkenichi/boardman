import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/adminAuth'
import { rematchApiFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  let body: any = {}
  try {
    body = await req.json()
  } catch {
    body = {}
  }
  const action = String(body.action || 'rematch')

  if (action === 'rematch') {
    const rematchBody: Record<string, unknown> = {
      white: body.white === 'nero' ? 'nero' : 'raja',
      wait: false,
      move_delay_sec: 0.05,
      game_id: body.game_id || 'agentic.chess_standard',
    }
    const stake = Number(body.stake_usdc)
    if (Number.isFinite(stake) && stake > 0) rematchBody.stake_usdc = stake
    const r = await rematchApiFetch('/api/stack/agentic/house/rematch', {
      method: 'POST',
      body: JSON.stringify(rematchBody),
    })
    return NextResponse.json(
      { ok: r.ok, operator: auth.session.tag, ...((r.data && typeof r.data === 'object') ? r.data : { error: r.data }) },
      { status: r.ok ? 200 : r.status || 502, headers: { 'Cache-Control': 'no-store' } }
    )
  }

  return NextResponse.json({ ok: false, error: 'unknown_action' }, { status: 400 })
}
