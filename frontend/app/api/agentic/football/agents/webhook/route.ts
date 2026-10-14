/** BFF: point a manager you own at the webhook hosting its brain. */
import { NextRequest } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  return proxyAuthed(req, '/api/stack/agentic/football/agents/webhook', { body, identityFields: ['owner_id'] })
}
