/** BFF: save a club lineup + tactics (afm_set_lineup) — the club's owner only. */
import { NextRequest } from 'next/server'
import { proxyAuthed, readJsonObject } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function PUT(req: NextRequest, ctx: { params: Promise<{ agent_id: string }> }) {
  const { agent_id } = await ctx.params
  const body = await readJsonObject(req)
  return proxyAuthed(req, `/api/stack/agentic/football/clubs/${encodeURIComponent(agent_id)}/lineup`, { method: 'PUT', body })
}
