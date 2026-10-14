/** BFF: adopt a developer-built AFM manager from the marketplace (as the signed-in owner). */
import { NextRequest } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  return proxyAuthed(req, '/api/stack/agentic/football/agents/acquire', { body, identityFields: ['owner_id'] })
}
