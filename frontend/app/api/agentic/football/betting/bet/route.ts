/** BFF: place an AFM parimutuel bet (POST) — always as the signed-in spectator. */
import { NextRequest, NextResponse } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  const { matchday, home, away, side, amount, season_no } = body as Record<string, any>
  if (!matchday || !home || !away || !side || !(Number(amount) > 0)) {
    return NextResponse.json({ ok: false, error: 'matchday, home, away, side, amount required' }, { status: 400 })
  }
  const payload = {
    matchday,
    home,
    away,
    side,
    amount: Number(amount),
    ...(season_no ? { season_no } : {}),
  }
  return proxyAuthed(req, '/api/stack/agentic/football/betting/bet', { body: payload, identityFields: ['better'], limit: 20 })
}
