/** BFF: remove your own AFM marketplace party's wallet binding. */
import { NextRequest } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  return proxyAuthed(req, '/api/stack/agentic/football/agents/wallet/unbind', { body, identityFields: ['party_id'] })
}
