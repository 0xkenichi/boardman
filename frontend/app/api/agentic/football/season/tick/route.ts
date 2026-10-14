/** BFF: advance the AFM season clock (POST /football/season/tick) — admins
 *  only; the backend accepts it only from the platform itself. */
import { proxyAdmin } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  return proxyAdmin(req, '/api/stack/agentic/football/season/tick', { method: 'POST' })
}
