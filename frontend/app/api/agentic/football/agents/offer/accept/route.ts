/** BFF: owner accepts a buyer's offer — the sale settles at the offered price. */
import { NextRequest } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  return proxyAuthed(req, '/api/stack/agentic/football/agents/offer/accept', { body, identityFields: ['decided_by'], timeoutMs: 60_000 })
}
