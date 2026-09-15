/** BFF: point an owned manager at the webhook hosting its brain. */
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

function stackHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = {}
  if (json) headers['Content-Type'] = 'application/json'
  const key = process.env.BOARDMAN_API_KEY || process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || ''
  if (key) {
    headers['X-Rematch-Key'] = key
    headers['X-Stack-Key'] = key
  }
  return headers
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  if (rematchApiConfigured()) {
    const out = await rematchApiFetch('/api/stack/agentic/football/agents/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return NextResponse.json(out.data, { status: out.ok ? 200 : out.status || 502 })
  }
  try {
    const res = await fetch(`${localStackBase()}/api/stack/agentic/football/agents/webhook`, {
      method: 'POST',
      headers: stackHeaders(true),
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'boardman_backend_unreachable' }, { status: 503 })
  }
}