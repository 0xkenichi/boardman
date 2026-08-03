import { NextResponse } from 'next/server'
import {
  encodeSession,
  sessionCookieHeader,
  clearSessionCookieHeader,
  readSessionFromRequest,
} from '@/lib/session'
import { verifyTelegramLogin, verifyTelegramWebAppInitData } from '@/lib/telegramAuth'
import { createHash } from 'crypto'

export const dynamic = 'force-dynamic'

/** GET — current session */
export async function GET(req: Request) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, authenticated: false }, { status: 401 })
  }
  return NextResponse.json({
    ok: true,
    authenticated: true,
    profileId: s.profileId,
    tag: s.tag,
    name: s.name,
    telegramId: s.telegramId,
  })
}

/**
 * POST — login
 * body: { mode: 'demo' } | { mode: 'telegram', ...loginWidgetFields } | { mode: 'webapp', initData }
 */
export async function POST(req: Request) {
  let body: any = {}
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid_json' }, { status: 400 })
  }

  const mode = body.mode || 'demo'

  if (mode === 'logout') {
    const res = NextResponse.json({ ok: true, authenticated: false })
    res.headers.set('Set-Cookie', clearSessionCookieHeader())
    return res
  }

  let telegramId = ''
  let name = 'Player'
  let tag = 'player'
  let profileId = ''

  if (mode === 'demo') {
    const allowDemo =
      process.env.REMATCH_ALLOW_DEMO_LOGIN === '1' || process.env.NODE_ENV !== 'production'
    if (!allowDemo) {
      return NextResponse.json(
        { ok: false, error: 'demo_login_disabled' },
        { status: 403 }
      )
    }
    telegramId = String(body.telegramId || '6277067771')
    name = String(body.name || 'Demo Player')
    tag = String(body.tag || 'stillkenichi').replace(/^@/, '')
    // Stable demo profile id from telegram id (not a real UUID lookup in demo)
    profileId =
      body.profileId ||
      process.env.REMATCH_DEMO_PROFILE_ID ||
      // placeholder UUID shape for stack APIs that expect UUID
      '62440a47-f4fc-4249-a627-46aaa2d039ef'
  } else if (mode === 'telegram') {
    const fields: Record<string, string> = {}
    for (const [k, v] of Object.entries(body)) {
      if (k === 'mode') continue
      if (v != null) fields[k] = String(v)
    }
    const user = verifyTelegramLogin(fields)
    if (!user) {
      return NextResponse.json({ ok: false, error: 'invalid_telegram_login' }, { status: 401 })
    }
    telegramId = String(user.id)
    name = [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Player'
    tag = (user.username || `tg${user.id}`).replace(/^@/, '')
    profileId = await resolveProfileId(telegramId, tag, name)
  } else if (mode === 'webapp') {
    const verified = verifyTelegramWebAppInitData(String(body.initData || ''))
    if (!verified) {
      return NextResponse.json({ ok: false, error: 'invalid_webapp_init' }, { status: 401 })
    }
    let userObj: any = {}
    try {
      userObj = JSON.parse(verified.user || '{}')
    } catch {
      return NextResponse.json({ ok: false, error: 'invalid_webapp_user' }, { status: 401 })
    }
    telegramId = String(userObj.id || '')
    name = [userObj.first_name, userObj.last_name].filter(Boolean).join(' ') || 'Player'
    tag = (userObj.username || `tg${telegramId}`).replace(/^@/, '')
    profileId = await resolveProfileId(telegramId, tag, name)
  } else {
    return NextResponse.json({ ok: false, error: 'unknown_mode' }, { status: 400 })
  }

  if (!telegramId || !profileId) {
    return NextResponse.json({ ok: false, error: 'login_failed' }, { status: 400 })
  }

  const token = encodeSession({
    profileId,
    telegramId,
    tag,
    name,
  })
  const res = NextResponse.json({
    ok: true,
    authenticated: true,
    profileId,
    tag,
    name,
    demo: mode === 'demo',
  })
  res.headers.set('Set-Cookie', sessionCookieHeader(token))
  return res
}

/** Map telegram id → profile UUID via Stack/backend if available; else deterministic placeholder. */
async function resolveProfileId(telegramId: string, tag: string, name: string): Promise<string> {
  // Optional: call backend profile lookup when REMATCH_PROFILE_LOOKUP_URL is set
  const lookup = process.env.REMATCH_PROFILE_LOOKUP_URL
  if (lookup) {
    try {
      const res = await fetch(
        `${lookup.replace(/\/$/, '')}?telegram_id=${encodeURIComponent(telegramId)}`,
        {
          headers: {
            'X-Stack-Key': process.env.STACK_API_KEY || '',
          },
          cache: 'no-store',
        }
      )
      if (res.ok) {
        const data = await res.json()
        if (data.profile_id || data.id) return String(data.profile_id || data.id)
      }
    } catch {
      /* fall through */
    }
  }
  // Deterministic pseudo-UUID for session binding until lookup exists
  const h = createHash('sha256').update(`rematch:tg:${telegramId}`).digest('hex')
  return [
    h.slice(0, 8),
    h.slice(8, 12),
    '4' + h.slice(13, 16),
    ((parseInt(h.slice(16, 18), 16) & 0x3f) | 0x80).toString(16) + h.slice(18, 20),
    h.slice(20, 32),
  ].join('')
}
