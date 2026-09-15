/** BFF: save a club lineup + tactics (afm_set_lineup). */
import { NextRequest, NextResponse } from 'next/server'
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

export async function PUT(req: NextRequest, ctx: { params: Promise<{ agent_id: string }> }) {
  const { agent_id } = await ctx.params
  const body = await req.json().catch(() => ({}))
  if (rematchApiConfigured()) {
    const out = await rematchApiFetch(`/api/stack/agentic/football/clubs/${agent_id}/lineup`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
    const res = await fetch(`${localStackBase()}/api/stack/agentic/football/clubs/${agent_id}/lineup`, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'boardman_backend_unreachable' }, { status: 503 })
  }
}
