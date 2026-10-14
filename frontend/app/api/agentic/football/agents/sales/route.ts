/** BFF: owner sales desk — money a party has earned from manager sales and
 *  the listing history (party_id query param). */
import { NextRequest } from 'next/server'
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const party = req.nextUrl.searchParams.get('party_id') ?? ''
  return proxyPublic(req, `/api/stack/agentic/football/agents/sales?party_id=${encodeURIComponent(party)}`, {
    offlineBody: { sales: null },
  })
}
