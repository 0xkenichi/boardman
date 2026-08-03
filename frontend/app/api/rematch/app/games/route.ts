import { NextResponse } from 'next/server'
import { requireSession } from '@/lib/bff'
import { DEMO_GAMES, stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth.error

  const url = new URL(req.url)
  const category = url.searchParams.get('category') || ''

  if (stackConfigured()) {
    const path = category
      ? `/api/stack/v1/games?category=${encodeURIComponent(category)}`
      : '/api/stack/v1/games'
    const res = await stackFetch(path)
    if (res.ok) {
      return NextResponse.json({ ok: true, ...res.data, demo: false })
    }
  }

  let games = DEMO_GAMES.games
  if (category) games = games.filter((g) => g.category === category)
  return NextResponse.json({
    ok: true,
    success: true,
    categories: DEMO_GAMES.categories,
    games,
    demo: true,
  })
}
