/** BFF: place an AFM parimutuel bet (POST). */
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

interface BetBody {
  better: string
  matchday: number
  home: string
  away: string
  side: 'home' | 'draw' | 'away'
  amount: number
  season_no?: number
}

export async function POST(req: Request) {
  let body: BetBody
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid_json' }, { status: 400 })
  }
  const { better, matchday, home, away, side, amount, season_no } = body ?? ({} as BetBody)
  if (!better || !matchday || !home || !away || !side || !(Number(amount) > 0)) {
    return NextResponse.json({ ok: false, error: 'better, matchday, home, away, side, amount required' }, { status: 400 })
  }
  const payload = { better, matchday, home, away, side, amount: Number(amount), ...(season_no ? { season_no } : {}) }

  if (rematchApiConfigured()) {
    const out = await rematchApiFetch('/api/stack/agentic/football/betting/bet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return NextResponse.json(out.data, { status: out.ok ? 200 : out.status || 502 })
  }
  const key = process.env.BOARDMAN_API_KEY || process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || ''
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (key) {
    headers['X-Rematch-Key'] = key
    headers['X-Stack-Key'] = key
  }
  try {
    const res = await fetch(`${localStackBase()}/api/stack/agentic/football/betting/bet`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : 'stack_unavailable' },
      { status: 503 },
    )
  }
}
