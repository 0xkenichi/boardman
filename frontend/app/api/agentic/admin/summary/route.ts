import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/adminAuth'
import { rematchApiFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

async function live(path: string, ms = 8000) {
  return Promise.race([
    rematchApiFetch(path),
    new Promise<{ ok: false; status: number; data: any }>((resolve) =>
      setTimeout(() => resolve({ ok: false, status: 504, data: { error: 'timeout' } }), ms)
    ),
  ])
}

export async function GET(req: Request) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  const [metrics, house, floor, agents] = await Promise.all([
    live('/api/stack/agentic/public/metrics?limit=40'),
    live('/api/stack/agentic/house'),
    live('/api/stack/agentic/house/floor'),
    live('/api/stack/agentic/agents'),
  ])

  const offline =
    !metrics.ok && !house.ok
      ? String(metrics.data?.error || house.data?.error || 'House API offline')
      : null

  return NextResponse.json(
    {
      ok: true,
      operator: auth.session.tag,
      telegram_id: auth.session.telegramId,
      generated_at: new Date().toISOString(),
      via: metrics.ok ? 'stack_api' : 'empty',
      offline,
      metrics: metrics.ok ? metrics.data : { success: false, volume: {}, agents: [], matches: [] },
      house: house.ok ? house.data?.house || house.data : null,
      floor: floor.ok ? floor.data?.floor || floor.data : null,
      agents: agents.ok ? agents.data?.agents || [] : [],
    },
    { headers: { 'Cache-Control': 'no-store' } }
  )
}
