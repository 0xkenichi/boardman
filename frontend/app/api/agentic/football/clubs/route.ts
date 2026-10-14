/** BFF: agent-owned AFM clubs (GET list). */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  return proxyPublic(req, '/api/stack/agentic/football/clubs', { offlineBody: { clubs: [] } })
}
