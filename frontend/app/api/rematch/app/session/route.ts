import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import {
  encodeSession,
  renewSession,
  sessionCookieHeader,
  clearSessionCookieHeader,
  readSessionFromRequest,
  readWalletNonceFromRequest,
  clearWalletNonceCookieHeader,
  isProductionRuntime,
} from '@/lib/session'
import { verifyTelegramLogin, verifyTelegramWebAppInitData } from '@/lib/telegramAuth'
import { parseWalletMessage, walletLoginQuery, walletMessageProblem } from '@/lib/walletMessage'
import { recoverPersonalSignAddress } from '@/lib/walletVerify'
import { telegramBotUrl } from '@/lib/telegramBot'
import { rateLimitRequest } from '@/lib/bff'
import { stackConfigured, stackFetch } from '@/lib/stackServer'
import { supabaseRest } from '@/lib/supabaseAdmin'
import { isBoardmanAdmin } from '@/lib/adminAuth'

export const dynamic = 'force-dynamic'

/** GET — current session (slides the cookie forward while the user is active) */
export async function GET(req: Request) {
  const limited = rateLimitRequest(req, 'session-get', 60)
  if (limited) return limited
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, authenticated: false }, { status: 401 })
  }
  const res = NextResponse.json({
    ok: true,
    authenticated: true,
    profileId: s.profileId,
    tag: s.tag,
    name: s.name,
    telegramId: s.telegramId,
    wallet: s.wallet || '',
    admin: isBoardmanAdmin(s),
  })
  // Sliding renewal: re-issue when more than half the lifetime has passed.
  const now = Math.floor(Date.now() / 1000)
  if (s.exp - now < 60 * 60 * 24 * 3.5) {
    res.headers.set('Set-Cookie', sessionCookieHeader(renewSession(s)))
  }
  return res
}

/** Demo login: dev only. Hard-off in production whatever REMATCH_ALLOW_DEMO_LOGIN says. */
function demoLoginAllowed(): boolean {
  return !isProductionRuntime()
}

/**
 * POST — login
 * body: { mode: 'demo' } | { mode: 'telegram', ...loginWidgetFields } | { mode: 'webapp', initData }
 *     | { mode: 'wallet', intent, message, signature }  (nonce from GET /wallet-nonce)
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

  const mode = String(body?.mode || '')
  const res = await login(req, body, mode)
  // The wallet nonce is single-use: burn it on every attempt, pass or fail.
  if (mode === 'wallet') res.headers.append('Set-Cookie', clearWalletNonceCookieHeader())
  return res
}

async function login(req: Request, body: any, mode: string): Promise<NextResponse> {

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
  let linkedWallet = ''

  if (mode === 'demo') {
    if (!demoLoginAllowed()) {
      return NextResponse.json({ ok: false, error: 'demo_login_disabled' }, { status: 403 })
    }
    // Server-chosen identity only: client profileId / telegramId / name are ignored,
    // and the non-numeric telegramId + demo flag keep it out of every admin gate.
    telegramId = 'demo'
    name = 'Demo Player'
    tag = 'demo'
    profileId = process.env.REMATCH_DEMO_PROFILE_ID || '62440a47-f4fc-4249-a627-46aaa2d039ef'
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
    if (!profileId && resolved.lookupError && resolved.lookupError !== 'profile_not_in_database') {
      return NextResponse.json(
        {
          ok: false,
          error: 'profile_lookup_failed',
          message:
            'Telegram login is valid, but the website could not reach the Boardman database. ' +
            'This is a server config issue (REMATCH_API_URL / REMATCH_API_KEY), not your account.',
          detail: resolved.lookupError,
          status: resolved.lookupStatus,
          telegramId,
        },
        { status: 502 }
      )
    }
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
    if (!profileId && resolved.lookupError && resolved.lookupError !== 'profile_not_in_database') {
      return NextResponse.json(
        {
          ok: false,
          error: 'profile_lookup_failed',
          message:
            'Telegram login is valid, but the website could not reach the Boardman database. ' +
            'This is a server config issue (REMATCH_API_URL / REMATCH_API_KEY), not your account.',
          detail: resolved.lookupError,
          status: resolved.lookupStatus,
          telegramId,
        },
        { status: 502 }
      )
    }
  } else if (mode === 'wallet') {
    const intent = body.intent === 'link' ? 'link' : 'login'
    const parsed = parseWalletMessage(body.message)
    if (!parsed) {
      return NextResponse.json({ ok: false, error: 'invalid_wallet_message' }, { status: 400 })
    }
    const existing = readSessionFromRequest(req)
    const wantProfile = intent === 'link' ? existing?.profileId : undefined
    const problem = walletMessageProblem(parsed, {
      action: intent,
      profileId: wantProfile,
      host: req.headers.get('host') || new URL(req.url).host,
      nonce: readWalletNonceFromRequest(req),
    })
    if (problem) {
      return NextResponse.json(
        {
          ok: false,
          error: 'wallet_message_rejected',
          reason: problem,
          message: 'Sign-in message expired or mismatched — try again.',
        },
        { status: 401 }
      )
    }
    const recovered = recoverPersonalSignAddress(String(body.message || ''), body.signature)
    if (!recovered || recovered !== parsed.address) {
      return NextResponse.json({ ok: false, error: 'invalid_wallet_signature' }, { status: 401 })
    }
    const wallet = recovered

    if (intent === 'link') {
      if (!existing || existing.demo) {
        return NextResponse.json(
          {
            ok: false,
            error: 'unauthorized',
            message: 'Sign in with Telegram first, then link your wallet.',
          },
          { status: 401 }
        )
      }
      // One wallet signs in to one profile: refuse a wallet another profile holds.
      const taken = await supabaseRest<WalletProfileRow[]>(`profiles?${walletLoginQuery(wallet)}`)
      if (!taken.ok || !Array.isArray(taken.data)) {
        return NextResponse.json({ ok: false, error: 'wallet_link_failed' }, { status: 502 })
      }
      if (taken.data.some((r) => r?.id && r.id !== existing.profileId)) {
        return NextResponse.json(
          { ok: false, error: 'wallet_linked_elsewhere', message: 'This wallet is already linked to another Boardman profile.' },
          { status: 409 }
        )
      }
      const upd = await supabaseRest(`profiles?id=eq.${encodeURIComponent(existing.profileId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Prefer: 'return=representation' },
        body: JSON.stringify({ linked_wallet: wallet }),
      })
      if (!upd.ok) {
        return NextResponse.json(
          { ok: false, error: 'wallet_link_failed', detail: upd.error || upd.data },
          { status: 502 }
        )
      }
      const token = renewSession({ ...existing, wallet })
      const res = NextResponse.json({
        ok: true,
        authenticated: true,
        profileId: existing.profileId,
        tag: existing.tag,
        name: existing.name,
        wallet,
      })
      res.headers.set('Set-Cookie', sessionCookieHeader(token))
      return res
    }

    // intent === 'login': resolve the existing profile this wallet is linked to
    const found = await findProfileByWallet(wallet)
    if (!found) {
      return NextResponse.json(
        {
          ok: false,
          error: 'link_wallet_first',
          message:
            'No Boardman profile is linked to this wallet yet. Sign in with Telegram once, then link this wallet from the Wallet tab — after that, wallet sign-in works every time.',
          bot: telegramBotUrl(),
          wallet,
        },
        { status: 403 }
      )
    }
    telegramId = String(found.telegram_id || '')
    tag = found.gaming_tag || tag
    name = found.display_name || name
    profileId = found.id
    // Rows without telegram_id get a non-numeric marker; admin gating keys off
    // numeric telegram ids, so wallet sessions never accidentally pass it.
    if (!telegramId) telegramId = 'wallet'
    linkedWallet = wallet
  } else {
    return NextResponse.json({ ok: false, error: 'unknown_mode' }, { status: 400 })
  }

  // Valid Telegram, DB says no row → open bot /start (or wrong DB)
  if (telegramId && !profileId) {
    return NextResponse.json(
      {
        ok: false,
        error: 'open_bot_first',
        message:
          'Telegram login is valid, but no Boardman profile row was found for your Telegram id. ' +
          'If you already use the bot, the web API may be pointing at a different database — ' +
          'or open @' +
          (process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || 'myboardmanOfficialBot').replace(
            /^@/,
            ''
          ) +
          ' and send /start, then try again.',
        bot: telegramBotUrl(),
        telegramId,
      },
      { status: 403 }
    )
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
    ...(linkedWallet ? { wallet: linkedWallet } : {}),
    ...(mode === 'demo' ? { demo: true } : {}),
  })
  const res = NextResponse.json({
    ok: true,
    authenticated: true,
    profileId,
    tag,
    name,
    wallet: linkedWallet || undefined,
    demo: mode === 'demo',
    needsBotStart,
  })
  res.headers.set('Set-Cookie', sessionCookieHeader(token))
  return res
}

type WalletProfileRow = {
  id: string
  telegram_id?: number | string | null
  gaming_tag?: string | null
  display_name?: string | null
}

/**
 * Find the profile a wallet signs in to. Only linked_wallet counts: this
 * route writes it after a personal_sign proof (intent=link). wallet_address
 * (the custodial play address, or a legacy /link_wallet value typed with no
 * proof) and withdrawal_wallet (a payout address — maybe a friend's or a P2P
 * merchant's) must never open the account to whoever holds that key. Two
 * profiles claiming the same wallet is ambiguous and refused.
 */
async function findProfileByWallet(wallet: string): Promise<WalletProfileRow | null> {
  try {
    const res = await supabaseRest<WalletProfileRow[]>(`profiles?${walletLoginQuery(wallet)}`)
    if (!res.ok || !Array.isArray(res.data)) return null
    if (res.data.length !== 1 || !res.data[0]?.id) {
      if (res.data.length > 1) console.warn('[session] wallet login refused: wallet linked to several profiles')
      return null
    }
    console.info('[session] wallet login hit profile=%s', res.data[0].id)
    return res.data[0]
  } catch (e) {
    console.error('[session] wallet lookup error', e)
    return null
  }
}

type ResolveResult = {
  profileId: string
  needsBotStart: boolean
  tag?: string
  name?: string
  /** Why lookup failed — surfaced to the client so we don't show a vague login_failed */
  lookupError?: string
  lookupStatus?: number
}

/**
 * Direct Supabase lookup — same `profiles` table the Telegram bot writes on /start.
 * Used when REMATCH_API_URL points at the wrong host (e.g. sideQuest social API without
 * /api/rematch/web/*) or when the gaming API is down.
 */
async function resolveProfileFromSupabase(
  telegramId: string,
  tag: string,
  name: string
): Promise<ResolveResult | null> {
  const url = (
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    process.env.SUPABASE_URL ||
    ''
  ).replace(/\/$/, '')
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    ''
  if (!url || !key) return null

  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    Accept: 'application/json',
  }

  // Try int then string match (column type varies across envs)
  for (const tid of [telegramId, String(Number(telegramId) || telegramId)]) {
    try {
      const q = new URLSearchParams()
      q.set('select', 'id,gaming_tag,display_name,telegram_id')
      q.set('telegram_id', `eq.${tid}`)
      q.set('limit', '1')
      const res = await fetch(`${url}/rest/v1/profiles?${q.toString()}`, {
        headers,
        cache: 'no-store',
      })
      if (!res.ok) {
        console.error(
          '[session] supabase profiles HTTP %s telegram_id=%s',
          res.status,
          tid
        )
        continue
      }
      const rows = (await res.json()) as Array<{
        id?: string
        gaming_tag?: string
        display_name?: string
      }>
      if (Array.isArray(rows) && rows[0]?.id) {
        console.info(
          '[session] supabase hit profile=%s tag=%s telegram_id=%s',
          rows[0].id,
          rows[0].gaming_tag,
          tid
        )
        return {
          profileId: String(rows[0].id),
          needsBotStart: false,
          tag: rows[0].gaming_tag || tag,
          name: rows[0].display_name || name,
        }
      }
    } catch (e) {
      console.error('[session] supabase lookup error', e)
    }
  }

  // Explicit miss (API worked, no row)
  return {
    profileId: '',
    needsBotStart: true,
    lookupError: 'profile_not_in_database',
  }
}

async function resolveProfileId(
  telegramId: string,
  tag: string,
  name: string
): Promise<ResolveResult> {
  let stackMissDetail: string | undefined
  let stackMissStatus: number | undefined

  // 1) Preferred: gaming API → /api/rematch/web/profile
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
      // Gaming API says no row — still try Supabase in case of split DBs / wrong API host
      // that implements the endpoint but wrong empty result.
      stackMissDetail = 'profile_not_in_database'
      stackMissStatus = res.status
    } else {
      // 404 / 401 / 502: often REMATCH_API_URL is the sideQuest social API, not Boardman gaming.
      stackMissDetail = String(
        (res.data && (res.data.detail || res.data.error || res.data.message)) ||
          `profile_lookup_http_${res.status}`
      )
      stackMissStatus = res.status
      console.error(
        '[session] gaming API profile lookup failed telegram_id=%s status=%s data=%o — falling back to Supabase',
        telegramId,
        res.status,
        res.data
      )
    }
  }

  // 2) Optional dedicated lookup URL
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
      /* fall through to Supabase */
    }
  }

  // 3) Direct Supabase (same DB the bot uses) — fixes wrong REMATCH_API_URL
  const fromSb = await resolveProfileFromSupabase(telegramId, tag, name)
  if (fromSb && fromSb.profileId) {
    return fromSb
  }
  if (fromSb && fromSb.lookupError === 'profile_not_in_database') {
    return fromSb
  }

  // Dev fallback only — invents a deterministic profile when no API is wired
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

  if (stackMissDetail) {
    return {
      profileId: '',
      needsBotStart: false,
      lookupError: stackMissDetail,
      lookupStatus: stackMissStatus,
    }
  }

  return {
    profileId: '',
    needsBotStart: false,
    lookupError: fromSb?.lookupError || 'rematch_api_not_configured',
  }
}
