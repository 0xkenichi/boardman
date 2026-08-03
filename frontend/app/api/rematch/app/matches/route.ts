import { NextResponse } from 'next/server'
import { randomBytes } from 'crypto'
import { requireSession, rateLimitRequest } from '@/lib/bff'
import { stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

function demoStore(): Map<string, any> {
  const g = globalThis as any
  if (!g.__rematchDemoMatches) g.__rematchDemoMatches = new Map()
  return g.__rematchDemoMatches as Map<string, any>
}

export async function GET(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth.error
  const { session: s } = auth

  const demoMatches = demoStore()
  const url = new URL(req.url)
  const code = url.searchParams.get('code')
  if (code && demoMatches.has(code.toUpperCase())) {
    return NextResponse.json({
      ok: true,
      match: demoMatches.get(code.toUpperCase()),
      demo: true,
    })
  }

  // Live history from Telegram-backed challenges (same as bot /profile)
  if (stackConfigured()) {
    const res = await stackFetch(
      `/api/rematch/web/matches?profile_id=${encodeURIComponent(s.profileId)}&limit=40`
    )
    if (res.ok && Array.isArray(res.data?.matches)) {
      const matches = res.data.matches.map((m: any) => ({
        id: m.id,
        public_code: m.public_code || m.code,
        status: m.status,
        amount_usdc: m.amount_usdc ?? m.stake,
        game_id: m.game_id || m.game,
        game_label: m.game_label || m.game,
        result: m.result,
        settlement_chain: m.settlement_chain || m.chain,
        created_at: m.created_at,
        creator_id: m.creator_id,
        opponent_id: m.opponent_id,
      }))
      return NextResponse.json({ ok: true, matches, demo: false })
    }
  }

  const mine = [...demoMatches.values()].filter(
    (m) =>
      m.creator_id === s.profileId ||
      m.opponent_tag === s.tag ||
      m.opponent_id === s.profileId
  )
  return NextResponse.json({ ok: true, matches: mine, demo: !stackConfigured() })
}

export async function POST(req: Request) {
  const limited = rateLimitRequest(req, 'match-create', 10)
  if (limited) return limited

  const auth = requireSession(req)
  if ('error' in auth) return auth.error
  const { session: s } = auth

  let body: any = {}
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid_json' }, { status: 400 })
  }

  const amount = Number(body.amount_usdc || body.amount || 1)
  const game_id = String(body.game_id || 'mobile.fc_mobile')
  const opponent_tag = String(body.opponent_tag || '').replace(/^@/, '')

  if (amount <= 0 || amount > 25) {
    return NextResponse.json({ ok: false, error: 'invalid_stake' }, { status: 400 })
  }
  if (!opponent_tag) {
    return NextResponse.json({ ok: false, error: 'opponent_required' }, { status: 400 })
  }

  if (stackConfigured()) {
    const res = await stackFetch('/api/stack/v1/matches/by-tag', {
      method: 'POST',
      body: JSON.stringify({
        creator_id: s.profileId,
        opponent_tag,
        amount_usdc: amount,
        game_id,
        chain_id: 'arc',
      }),
    })
    if (res.ok) {
      return NextResponse.json({ ok: true, ...res.data, demo: false })
    }
    return NextResponse.json(
      {
        ok: false,
        error: res.data?.detail || res.data?.error || 'create_failed',
        detail: res.data,
      },
      { status: res.status || 400 }
    )
  }

  const code = randomBytes(3).toString('hex').toUpperCase().slice(0, 6)
  const match = {
    id: randomBytes(16)
      .toString('hex')
      .replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, '$1-$2-$3-$4-$5'),
    public_code: code,
    status: 'open',
    game_id,
    game_label: game_id,
    amount_usdc: amount,
    creator_id: s.profileId,
    creator_tag: s.tag,
    opponent_tag,
    opponent_id: null,
    settlement_chain: 'arc',
    proof_hint: 'Play, then upload the final screen photo.',
    created_at: new Date().toISOString(),
  }
  demoStore().set(code, match)

  return NextResponse.json({
    ok: true,
    success: true,
    match_id: match.id,
    public_code: code,
    game_id,
    status: 'open',
    amount_usdc: amount,
    demo: true,
    message: 'Demo match (Stack offline). Share code with opponent.',
  })
}
