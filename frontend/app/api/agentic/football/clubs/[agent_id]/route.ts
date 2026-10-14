/** BFF: single AFM club + enriched FM-style squad (GET). */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request, ctx: { params: Promise<{ agent_id: string }> }) {
  const { agent_id } = await ctx.params
  return proxyPublic(req, `/api/stack/agentic/football/clubs/${encodeURIComponent(agent_id)}`, {
    offlineBody: { club: null, squad: [] },
  })
}
