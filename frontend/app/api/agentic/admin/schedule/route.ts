import { NextRequest, NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/adminAuth'
import { rematchApiFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  const r = await rematchApiFetch('/api/stack/agentic/house/schedule')
  return NextResponse.json(
    r.ok ? r.data : { ok: false, error: r.data?.detail || r.data?.error || 'schedule unavailable' },
    { status: r.ok ? 200 : r.status || 502, headers: { 'Cache-Control': 'no-store' } }
  )
}

export async function POST(req: NextRequest) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  let body: any = {}
  try {
    body = await req.json()
  } catch {
    body = {}
  }
  const payload: Record<string, unknown> = {}
  if (body.cadence_sec != null) payload.cadence_sec = Number(body.cadence_sec)
  if (body.burst_games != null) payload.burst_games = Number(body.burst_games)
  if (body.enabled != null) payload.enabled = Boolean(body.enabled)

  const r = await rematchApiFetch('/api/stack/agentic/house/schedule', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return NextResponse.json(
    r.ok ? r.data : { ok: false, error: r.data?.detail || r.data?.error || 'schedule update failed' },
    { status: r.ok ? 200 : r.status || 502, headers: { 'Cache-Control': 'no-store' } }
  )
}
