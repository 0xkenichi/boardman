/**
 * Public house schedule for the arena — how often the house seats a table.
 * Proxies the Stack API's key-authed /house/schedule server-side and returns
 * only the display fields. Fails soft ({ok:false}) so the arena can hide the line.
 */
import { NextResponse } from 'next/server'
import { rematchApiFetch, rematchApiConfigured } from '@/lib/stackServer'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function localStackBase(): string {
  return (
    process.env.BOARDMAN_API_URL ||
    process.env.REMATCH_API_URL ||
    'http://127.0.0.1:8000'
  ).replace(/\/$/, '')
}

export async function GET() {
  const empty = { ok: false as const }
  try {
    let data: any = null
    if (rematchApiConfigured()) {
      const r = await rematchApiFetch('/api/stack/agentic/house/schedule')
      if (!r.ok) return NextResponse.json(empty, { headers: { 'Cache-Control': 'no-store' } })
      data = r.data
    } else {
      const key =
        process.env.BOARDMAN_API_KEY ||
        process.env.REMATCH_API_KEY ||
        process.env.STACK_API_KEY ||
        ''
      const res = await fetch(`${localStackBase()}/api/stack/agentic/house/schedule`, {
        headers: key ? { 'X-Rematch-Key': key, 'X-Stack-Key': key } : undefined,
        cache: 'no-store',
      })
      if (!res.ok) return NextResponse.json(empty, { headers: { 'Cache-Control': 'no-store' } })
      data = await res.json().catch(() => null)
    }
    const sched = data?.schedule || {}
    const enabled = Boolean(sched.enabled)
    const cadence = Math.max(0, Number(sched.cadence_sec ?? 0) || 0)
    return NextResponse.json(
      {
        ok: true,
        enabled,
        cadence_sec: cadence,
        games_per_day: cadence > 0 ? Math.floor(86400 / cadence) : 0,
        every_minutes: cadence > 0 ? Math.max(1, Math.round(cadence / 60)) : 0,
        last_settled_at: sched.last_settled_at || null,
      },
      { headers: { 'Cache-Control': 'no-store' } }
    )
  } catch {
    return NextResponse.json(empty, { headers: { 'Cache-Control': 'no-store' } })
  }
}
