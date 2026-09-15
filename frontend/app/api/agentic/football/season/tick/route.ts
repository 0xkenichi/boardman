/** BFF: advance the AFM season clock (POST /football/season/tick). */
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

export async function POST() {
  if (rematchApiConfigured()) {
    const out = await rematchApiFetch('/api/stack/agentic/football/season/tick', { method: 'POST' })
    return NextResponse.json(out.data, { status: out.ok ? 200 : out.status || 502 })
  }
  const key = process.env.BOARDMAN_API_KEY || process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || ''
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (key) {
    headers['X-Rematch-Key'] = key
    headers['X-Stack-Key'] = key
  }
  try {
    const res = await fetch(`${localStackBase()}/api/stack/agentic/football/season/tick`, { method: 'POST', headers })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.ok ? 200 : res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 503 })
  }
}