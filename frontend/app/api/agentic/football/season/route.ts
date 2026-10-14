/** BFF: AFM season state — standings, fixtures, results (GET). */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  return proxyPublic(req, '/api/stack/agentic/football/season', { offlineBody: { season: null } })
}
