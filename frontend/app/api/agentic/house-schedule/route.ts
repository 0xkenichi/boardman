/**
 * Public house schedule for the arena — how often the house seats a table.
 * Proxies the Stack API's key-authed /house/schedule server-side and returns
 * only the display fields. Fails soft ({ok:false}) so the arena can hide the line.
 */
import { NextResponse } from 'next/server'
import { stackCall } from '@/lib/stackServer'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const empty = { ok: false as const }
  try {
    // display line only — give up fast rather than hold the arena
    const r = await stackCall('/api/stack/agentic/house/schedule', { timeoutMs: 4000 })
    if (!r.ok) return NextResponse.json(empty, { headers: { 'Cache-Control': 'no-store' } })
    const data: any = r.data
    const sched = data?.schedule || {}
    const enabled = Boolean(sched.enabled)
    const cadence = Math.max(0, Number(sched.cadence_sec ?? 0) || 0)
    return NextResponse.json(
      {
        ok: true,
        enabled,
        cadence_sec: cadence,
        cadence_mode: data?.cadence_mode || sched.cadence_mode || 'after_game',
        games_per_day: cadence > 0 ? Math.floor(86400 / cadence) : 0,
        every_minutes: cadence > 0 ? Math.max(1, Math.round(cadence / 60)) : 0,
        last_settled_at: sched.last_settled_at || null,
        next_game_at: data?.next_game_at || null,
        next_in_sec:
          typeof data?.next_in_sec === 'number' ? Math.max(0, data.next_in_sec) : null,
      },
      { headers: { 'Cache-Control': 'no-store' } }
    )
  } catch {
    return NextResponse.json(empty, { headers: { 'Cache-Control': 'no-store' } })
  }
}
