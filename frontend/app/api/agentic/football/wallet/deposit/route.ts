/** BFF: move USDC from your play balance into your football wallet (POST).
 *  Always the signed-in profile; idempotent per idempotency_key. */
import { NextRequest, NextResponse } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  const amount = String(body.amount ?? '').trim()
  const key = String(body.idempotency_key ?? '').trim()
  if (!/^\d+(\.\d{1,6})?$/.test(amount) || Number(amount) <= 0) {
    return NextResponse.json({ ok: false, error: 'amount must be a positive USDC amount (max 6 decimals)' }, { status: 400 })
  }
  if (key.length < 8 || key.length > 120) {
    return NextResponse.json({ ok: false, error: 'idempotency_key required' }, { status: 400 })
  }
  return proxyAuthed(req, '/api/stack/agentic/football/wallet/deposit', {
    body: { amount, idempotency_key: key },
    identityFields: ['party_id'],
    limit: 10,
    timeoutMs: 15_000,
  })
}
