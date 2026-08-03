import { NextResponse } from 'next/server'
import { readSessionFromRequest } from '@/lib/session'
import { stackConfigured, stackFetch } from '@/lib/stackServer'
import { randomBytes } from 'crypto'

export const dynamic = 'force-dynamic'

/** In-memory demo matches (per server process) for scaffold UX */
function demoStore(): Map<string, any> {
  const g = globalThis as any
  if (!g.__rematchDemoMatches) g.__rematchDemoMatches = new Map()
  return g.__rematchDemoMatches as Map<string, any>
}

export async function GET(req: Request) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  const demoMatches = demoStore()
  const url = new URL(req.url)
  const code = url.searchParams.get('code')
  if (code && demoMatches.has(code.toUpperCase())) {
    return NextResponse.json({ ok: true, match: demoMatches.get(code.toUpperCase()), demo: true })
  }
  // list active for user in demo
  const mine = [...demoMatches.values()].filter(
    (m) => m.creator_id === s.profileId || m.opponent_tag === s.tag || m.opponent_id === s.profileId
  )
  return NextResponse.json({ ok: true, matches: mine, demo: !stackConfigured() })
}

export async function POST(req: Request) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

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
    const res = await stackFetch('/api/stack/v1/matches', {
      method: 'POST',
      body: JSON.stringify({
        creator_id: s.profileId,
        amount_usdc: amount,
        game_id,
        chain_id: 'arc',
        visibility: 'private',
        message: `vs @${opponent_tag}`,
        // opponent_id resolved server-side when tag lookup exists
      }),
    })
    if (res.ok) {
      return NextResponse.json({ ok: true, ...res.data, demo: false })
    }
    // fall through to demo if stack rejects unknown profile in scaffold
  }

  const code = randomBytes(3).toString('hex').toUpperCase().slice(0, 6)
  const match = {
    id: cryptoRandomId(),
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
    message: 'Demo match created (Stack offline or tag lookup pending). Share code with opponent.',
  })
}

function cryptoRandomId(): string {
  return randomBytes(16).toString('hex').replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, '$1-$2-$3-$4-$5')
}
