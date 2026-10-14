/** BFF: AFM owner dashboard for one club (GET /football/owner/{agent_id}).
 *  Step 5 of the owner seat: results, the agent's decisions, spending log,
 *  and suspension/injury news. */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request, ctx: { params: Promise<{ agent_id: string }> }) {
  const { agent_id } = await ctx.params
  return proxyPublic(req, `/api/stack/agentic/football/owner/${encodeURIComponent(agent_id)}`)
}
