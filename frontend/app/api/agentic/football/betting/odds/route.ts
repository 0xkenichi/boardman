/** BFF: AFM parimutuel odds boards (GET). */
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

export async function GET(req: Request) {
  const url = new URL(req.url)
  const season = url.searchParams.get('season_no') ?? ''
  const md = url.searchParams.get('matchday') ?? ''
  const qs = `?${season ? `season_no=${encodeURIComponent(season)}&` : ''}${md ? `matchday=${encodeURIComponent(md)}` : ''}`
  if (rematchApiConfigured()) {
    const out = await rematchApiFetch(`/api/stack/agentic/football/betting/odds${qs}`)
    return NextResponse.json(out.data, { status: out.ok ? 200 : out.status || 502 })
  }
  const key = process.env.BOARDMAN_API_KEY || process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || ''
  const headers: Record<string, string> = {}
  if (key) {
    headers['X-Rematch-Key'] = key
    headers['X-Stack-Key'] = key
  }
  try {
    const res = await fetch(`${localStackBase()}/api/stack/agentic/football/betting/odds${qs}`, { headers, cache: 'no-store' })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch {
    return NextResponse.json({ success: false, boards: [] }, { status: 503 })
  }
}
