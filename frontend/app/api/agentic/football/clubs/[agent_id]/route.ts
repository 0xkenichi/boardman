/** BFF: single AFM club + enriched FM-style squad (GET). */
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

export async function GET(_req: Request, ctx: { params: Promise<{ agent_id: string }> }) {
  const { agent_id } = await ctx.params
  const path = `/api/stack/agentic/football/clubs/${encodeURIComponent(agent_id)}`
  if (rematchApiConfigured()) {
    const out = await rematchApiFetch(path)
    return NextResponse.json(out.data, { status: out.ok ? 200 : out.status || 502 })
  }
  const key = process.env.BOARDMAN_API_KEY || process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || ''
  const headers: Record<string, string> = {}
  if (key) {
    headers['X-Rematch-Key'] = key
    headers['X-Stack-Key'] = key
  }
  try {
    const res = await fetch(`${localStackBase()}${path}`, { headers })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch {
    return NextResponse.json({ success: false, club: null, squad: [] }, { status: 503 })
  }
}