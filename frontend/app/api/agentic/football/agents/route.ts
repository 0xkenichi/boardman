/** BFF: AFM manager marketplace — GET the marketplace, POST build a manager (signed in). */
import { NextRequest } from 'next/server'
import { proxyAuthed, proxyPublic, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  return proxyPublic(req, '/api/stack/agentic/football/agents', { offlineBody: { agents: [] } })
}

export async function POST(req: NextRequest) {
  const body = await readJsonObject(req)
  return proxyAuthed(req, '/api/stack/agentic/football/agents/create', { body, identityFields: ['owner_id'] })
}
