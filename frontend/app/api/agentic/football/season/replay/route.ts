/** BFF: recorded AFM fixture replay (GET /football/season/replay?matchday&home&away). */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const qs = new URL(req.url).searchParams.toString()
  return proxyPublic(req, `/api/stack/agentic/football/season/replay?${qs}`, { offlineBody: { replay: null } })
}
