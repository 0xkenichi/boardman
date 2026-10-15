/** BFF: your football (ledger) wallet balance + recent bridge transfers (GET).
 *  Signed-in only; the backend reads the caller from X-Boardman-Caller. */
import { proxyAuthed } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  return proxyAuthed(req, '/api/stack/agentic/football/wallet', { method: 'GET' })
}
