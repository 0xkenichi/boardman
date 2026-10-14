/** BFF: buy a listed AFM manager as the signed-in buyer (settlement auto | ledger | onchain). */
import { NextRequest } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  return proxyAuthed(req, '/api/stack/agentic/football/agents/purchase', { body, identityFields: ['buyer_id'], timeoutMs: 60_000 })
}
