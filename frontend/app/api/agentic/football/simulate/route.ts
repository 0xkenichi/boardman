/**
 * BFF: run an AFM friendly on the authoritative backend engine (signed in —
 * the engine is the House's compute, not a public endpoint).
 */
import { NextRequest, NextResponse } from 'next/server'
import { proxyAuthed } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 })
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 })
  }
  return proxyAuthed(req, '/api/stack/agentic/football/simulate', { body: body as Record<string, unknown>, limit: 10 })
}
