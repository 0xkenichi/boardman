/** BFF: wallet status for an AFM marketplace party (party_id query param). */
import { NextRequest } from 'next/server'
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const party = req.nextUrl.searchParams.get('party_id') ?? ''
  return proxyPublic(req, `/api/stack/agentic/football/agents/wallet?party_id=${encodeURIComponent(party)}`, {
    offlineBody: { wallet: null },
  })
}
