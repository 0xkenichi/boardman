import type { RematchSession } from '@/lib/session'

const OWNER_USERNAME = 'stillkenichi'

function splitList(raw: string | undefined): string[] {
  return (raw || '')
    .split(/[,\s]+/)
    .map((s) => s.trim().toLowerCase().replace(/^@/, ''))
    .filter(Boolean)
}

export function adminUsernames(): string[] {
  const extra = splitList(
    process.env.BOARDMAN_ADMIN_TELEGRAM_USERNAMES || process.env.ADMIN_TELEGRAM_USERNAMES
  )
  return Array.from(new Set([OWNER_USERNAME, ...extra]))
}

export function adminTelegramIds(): string[] {
  return splitList(
    process.env.CLAW_ADMIN_TELEGRAM_IDS || process.env.ADMIN_TELEGRAM_IDS
  )
}

/** Operator gate: @stillkenichi, plus optional extra IDs / handles from env. */
export function isBoardmanAdmin(session: {
  tag?: string
  telegramId?: string
  name?: string
} | null | undefined): boolean {
  if (!session) return false
  if ((session.name || '').trim() === 'Demo Player') return false
  const tag = (session.tag || '').trim().toLowerCase().replace(/^@/, '')
  const tid = String(session.telegramId || '').trim()
  if (tag && adminUsernames().includes(tag)) return true
  if (tid && adminTelegramIds().includes(tid.toLowerCase())) return true
  return false
}

export function assertBoardmanAdmin(session: RematchSession | null): session is RematchSession {
  return isBoardmanAdmin(session)
}
