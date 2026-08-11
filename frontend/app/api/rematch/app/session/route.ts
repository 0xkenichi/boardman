import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import {
  encodeSession,
  sessionCookieHeader,
  clearSessionCookieHeader,
  readSessionFromRequest,
} from '@/lib/session'
import { verifyTelegramLogin, verifyTelegramWebAppInitData } from '@/lib/telegramAuth'
import { telegramBotUrl } from '@/lib/telegramBot'
import { rateLimitRequest } from '@/lib/bff'
import { stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

/** GET — current session */
export async function GET(req: Request) {
  const limited = rateLimitRequest(req, 'session-get', 60)
  if (limited) return limited
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
  const limited = rateLimitRequest(req, 'session-post', 15)
  if (limited) return limited

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
  let needsBotStart = false

  if (mode === 'demo') {
    const allowDemo =
      process.env.REMATCH_ALLOW_DEMO_LOGIN === '1' || process.env.NODE_ENV !== 'production'
    if (!allowDemo) {
      return NextResponse.json({ ok: false, error: 'demo_login_disabled' }, { status: 403 })
    }
    telegramId = String(body.telegramId || '6277067771')
    name = String(body.name || 'Demo Player')
    tag = String(body.tag || 'stillkenichi').replace(/^@/, '')
    profileId =
      body.profileId ||
      process.env.REMATCH_DEMO_PROFILE_ID ||
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
    const resolved = await resolveProfileId(telegramId, tag, name)
    profileId = resolved.profileId
    needsBotStart = resolved.needsBotStart
    if (resolved.tag) tag = resolved.tag
    if (resolved.name) name = resolved.name
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
    const resolved = await resolveProfileId(telegramId, tag, name)
    profileId = resolved.profileId
    needsBotStart = resolved.needsBotStart
    if (resolved.tag) tag = resolved.tag
    if (resolved.name) name = resolved.name
  } else {
    return NextResponse.json({ ok: false, error: 'unknown_mode' }, { status: 400 })
  }

  if (!telegramId || !profileId) {
    return NextResponse.json({ ok: false, error: 'login_failed' }, { status: 400 })
  }

  if (needsBotStart && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      {
        ok: false,
        error: 'open_bot_first',
        message: 'Open the Boardman Telegram bot once (/start), then sign in here.',
        bot: telegramBotUrl(),
      },
      { status: 403 }
    )
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
    needsBotStart,
  })
  res.headers.set('Set-Cookie', sessionCookieHeader(token))
  return res
}

async function resolveProfileId(
  telegramId: string,
  tag: string,
  name: string
): Promise<{ profileId: string; needsBotStart: boolean; tag?: string; name?: string }> {
  if (stackConfigured()) {
    const res = await stackFetch(
      `/api/rematch/web/profile?telegram_id=${encodeURIComponent(telegramId)}`
    )
    if (res.ok && res.data?.found && (res.data.profile_id || res.data.id)) {
      return {
        profileId: String(res.data.profile_id || res.data.id),
        needsBotStart: false,
        tag: res.data.gaming_tag || tag,
        name: res.data.display_name || name,
      }
    }
    if (res.ok && res.data && res.data.found === false) {
      return { profileId: '', needsBotStart: true }
    }
  }

  // Optional dedicated lookup URL
  const lookup = process.env.REMATCH_PROFILE_LOOKUP_URL
  if (lookup) {
    try {
      const res = await fetch(
        `${lookup.replace(/\/$/, '')}?telegram_id=${encodeURIComponent(telegramId)}`,
        {
          headers: {
            'X-Rematch-Key':
              process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || '',
            'X-Stack-Key':
              process.env.REMATCH_API_KEY || process.env.STACK_API_KEY || '',
          },
          cache: 'no-store',
        }
      )
      if (res.ok) {
        const data = await res.json()
        if (data.profile_id || data.id) {
          return {
            profileId: String(data.profile_id || data.id),
            needsBotStart: false,
            tag: data.gaming_tag || tag,
            name: data.display_name || name,
          }
        }
      }
    } catch {
      /* fall through */
    }
  }

  // Dev fallback only
  if (process.env.NODE_ENV !== 'production') {
    const h = createHash('sha256').update(`rematch:tg:${telegramId}`).digest('hex')
    const profileId = [
      h.slice(0, 8),
      h.slice(8, 12),
      '4' + h.slice(13, 16),
      ((parseInt(h.slice(16, 18), 16) & 0x3f) | 0x80).toString(16) + h.slice(18, 20),
      h.slice(20, 32),
    ].join('')
    return { profileId, needsBotStart: false }
  }

  return { profileId: '', needsBotStart: true }
}
