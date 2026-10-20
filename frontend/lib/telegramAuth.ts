/**
 * Verify Telegram Login Widget / WebApp payloads (server-only).
 * https://core.telegram.org/widgets/login#checking-authorization
 */
import { createHash, createHmac, timingSafeEqual } from 'crypto'

export type TelegramLoginUser = {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

/** Telegram login payloads older than this are refused (replay window). */
export function telegramLoginMaxAgeSec(env: Record<string, string | undefined> = process.env): number {
  const n = Number(env.TELEGRAM_LOGIN_MAX_AGE_SEC || 86400)
  return Number.isFinite(n) && n >= 60 ? Math.min(n, 86400) : 86400
}

/** auth_date must be a positive integer second, not older than the window, not in the future. */
export function authDateFresh(raw: unknown, nowSec = Math.floor(Date.now() / 1000)): boolean {
  const s = String(raw ?? '')
  if (!/^[1-9]\d{0,11}$/.test(s)) return false
  const t = Number(s)
  return t <= nowSec + 60 && t >= nowSec - telegramLoginMaxAgeSec()
}

function botToken(): string {
  // Prefer Boardman bot; legacy ClawStation aliases still work
  return (
    process.env.TELEGRAM_BOT_TOKEN_BOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_MYBOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
    process.env.TELEGRAM_BOT_TOKEN ||
    ''
  )
}

/** Login Widget check */
export function verifyTelegramLogin(data: Record<string, string>): TelegramLoginUser | null {
  const token = botToken()
  // No bot token → no Telegram login. There is no unsigned "demo" hash: it let a
  // client pick any Telegram id (including an admin's). Use { mode: 'demo' } in dev.
  if (!token) return null

  const hash = data.hash
  if (!hash) return null
  const pairs = Object.keys(data)
    .filter((k) => k !== 'hash')
    .sort()
    .map((k) => `${k}=${data[k]}`)
    .join('\n')
  const secret = createHash('sha256').update(token).digest()
  const hmac = createHmac('sha256', secret).update(pairs).digest('hex')
  try {
    const a = Buffer.from(hmac, 'hex')
    const b = Buffer.from(hash, 'hex')
    if (a.length !== b.length || !timingSafeEqual(a, b)) return null
  } catch {
    return null
  }
  if (!authDateFresh(data.auth_date)) return null
  const authDate = Number(data.auth_date)
  if (!/^[1-9]\d{0,15}$/.test(String(data.id || ''))) return null
  return {
    id: Number(data.id),
    first_name: data.first_name,
    last_name: data.last_name,
    username: data.username,
    photo_url: data.photo_url,
    auth_date: authDate,
    hash,
  }
}

/**
 * Verify Telegram WebApp initData query string.
 * https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
 */
export function verifyTelegramWebAppInitData(initData: string): Record<string, string> | null {
  const token = botToken()
  if (!token || !initData) return null
  const params = new URLSearchParams(initData)
  const hash = params.get('hash')
  if (!hash) return null
  params.delete('hash')
  const pairs = [...params.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')
  const secretKey = createHmac('sha256', 'WebAppData').update(token).digest()
  const calc = createHmac('sha256', secretKey).update(pairs).digest('hex')
  try {
    const a = Buffer.from(calc, 'hex')
    const b = Buffer.from(hash, 'hex')
    if (a.length !== b.length || !timingSafeEqual(a, b)) return null
  } catch {
    return null
  }
  const out: Record<string, string> = {}
  params.forEach((v, k) => {
    out[k] = v
  })
  out.hash = hash
  // Freshness: initData older than 24h is stale (mirrors the widget check) —
  // blocks replay of a captured initData string indefinitely.
  if (!authDateFresh(out.auth_date)) return null
  return out
}
