/** BFF: wallet status for an AFM marketplace party (party_id query param). */
import { NextRequest } from 'next/server'
import { proxyAuthed } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

// The party is always the signed-in profile: a party_id from the query used
// to let anyone read any player's bound wallet address and earnings.
export async function GET(req: NextRequest) {
  return proxyAuthed(
    req,
    (caller) => `/api/stack/agentic/football/agents/wallet?party_id=${encodeURIComponent(caller)}`,
    { method: 'GET', offlineBody: { wallet: null }, limit: 60 }
  )
}
