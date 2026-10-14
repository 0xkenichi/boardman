/** BFF: AFM pre-match board (GET /football/season/prematch?matchday&home&away). */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const qs = new URL(req.url).searchParams.toString()
  return proxyPublic(req, `/api/stack/agentic/football/season/prematch?${qs}`, { offlineBody: { prematch: null } })
}
