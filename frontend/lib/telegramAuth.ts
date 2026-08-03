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

function botToken(): string {
  return (
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
    process.env.TELEGRAM_BOT_TOKEN ||
    ''
  )
}

/** Login Widget check */
export function verifyTelegramLogin(data: Record<string, string>): TelegramLoginUser | null {
  const token = botToken()
  if (!token) {
    // Dev fallback: accept demo payloads only when explicitly allowed
    if (process.env.REMATCH_ALLOW_DEMO_LOGIN === '1' && data.id && data.hash === 'demo') {
      return {
        id: Number(data.id),
        first_name: data.first_name || 'Demo',
        username: data.username || 'demo',
        auth_date: Number(data.auth_date || Math.floor(Date.now() / 1000)),
        hash: 'demo',
      }
    }
    return null
  }

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
  const authDate = Number(data.auth_date || 0)
  if (authDate < Math.floor(Date.now() / 1000) - 86400) return null // 24h
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
  return out
}
