import { NextResponse } from 'next/server'
import { readSessionFromRequest } from '@/lib/session'
import { stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

// shared with list route via globalThis for demo scaffold
function demoStore(): Map<string, any> {
  const g = globalThis as any
  if (!g.__rematchDemoMatches) g.__rematchDemoMatches = new Map()
  return g.__rematchDemoMatches as Map<string, any>
}

export async function GET(
  req: Request,
  { params }: { params: { code: string } }
) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  const code = decodeURIComponent(params.code)

  if (stackConfigured()) {
    const res = await stackFetch(`/api/stack/v1/matches/${encodeURIComponent(code)}`)
    if (res.ok) {
      return NextResponse.json({ ok: true, match: res.data?.match || res.data, demo: false })
    }
  }

  const store = demoStore()
  const m = store.get(code.toUpperCase()) || store.get(code)
  if (!m) {
    // friendly empty shell so UI works when opened by deep link
    return NextResponse.json({
      ok: true,
      match: {
        public_code: code.toUpperCase(),
        status: 'unknown',
        game_label: '—',
        amount_usdc: 0,
        proof_hint: 'Open from your challenge list or create a new one.',
      },
      demo: true,
      not_found: true,
    })
  }
  return NextResponse.json({ ok: true, match: m, demo: true })
}

export async function POST(
  req: Request,
  { params }: { params: { code: string } }
) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  const code = decodeURIComponent(params.code)
  let body: any = {}
  try {
    body = await req.json()
  } catch {
    body = {}
  }
  const action = body.action || 'accept'

  if (stackConfigured()) {
    if (action === 'accept') {
      const res = await stackFetch(`/api/stack/v1/matches/${encodeURIComponent(code)}/accept`, {
        method: 'POST',
        body: JSON.stringify({ opponent_id: s.profileId }),
      })
      return NextResponse.json({ ok: res.ok, ...res.data, demo: false }, { status: res.status })
    }
    if (action === 'lock') {
      const res = await stackFetch(`/api/stack/v1/matches/${encodeURIComponent(code)}/lock`, {
        method: 'POST',
        body: JSON.stringify({ profile_id: s.profileId }),
      })
      return NextResponse.json({ ok: res.ok, ...res.data, demo: false }, { status: res.status })
    }
  }

  const store = demoStore()
  let m = store.get(code.toUpperCase()) || store.get(code)
  if (!m) {
    return NextResponse.json({ ok: false, error: 'not_found' }, { status: 404 })
  }
  if (action === 'accept') {
    m = { ...m, status: 'accepted', opponent_id: s.profileId, opponent_tag: s.tag }
  } else if (action === 'lock') {
    const next =
      m.status === 'open' || m.status === 'accepted'
        ? 'creator_locked'
        : m.status === 'creator_locked'
          ? 'locked'
          : m.status
    m = { ...m, status: next === 'creator_locked' && m.creator_id !== s.profileId ? 'locked' : next }
    if (m.status === 'creator_locked' && m.creator_id === s.profileId) {
      /* creator locked */
    } else if (m.creator_id !== s.profileId) {
      m.status = 'locked'
    }
  }
  store.set((m.public_code || code).toUpperCase(), m)
  return NextResponse.json({ ok: true, match: m, demo: true })
}
