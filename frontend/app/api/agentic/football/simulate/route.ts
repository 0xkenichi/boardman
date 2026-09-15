/**
 * BFF: run an AFM friendly on the authoritative backend engine.
 * Mirrors the house-play route handler: configured API key → backend,
 * otherwise the local stack on :8000.
 */
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

export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 })
  }

  if (rematchApiConfigured()) {
    const out = await rematchApiFetch('/api/stack/agentic/football/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return NextResponse.json(out.data, { status: out.ok ? 200 : out.status || 502 })
  }

  const key =
    process.env.BOARDMAN_API_KEY ||
    process.env.REMATCH_API_KEY ||
    process.env.STACK_API_KEY ||
    ''
  const url = `${localStackBase()}/api/stack/agentic/football/simulate`
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (key) {
    headers['X-Rematch-Key'] = key
    headers['X-Stack-Key'] = key
  }
  try {
    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch {
    return NextResponse.json(
      { success: false, error: 'boardman_backend_unreachable' },
      { status: 503 },
    )
  }
}
