/** BFF: AFM parimutuel odds boards (GET). */
import { proxyPublic } from '@/lib/proxyAuthed'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const url = new URL(req.url)
  const season = url.searchParams.get('season_no') ?? ''
  const md = url.searchParams.get('matchday') ?? ''
  const qs = `?${season ? `season_no=${encodeURIComponent(season)}&` : ''}${md ? `matchday=${encodeURIComponent(md)}` : ''}`
  return proxyPublic(req, `/api/stack/agentic/football/betting/odds${qs}`, { offlineBody: { boards: [] } })
}
