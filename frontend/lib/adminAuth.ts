import type { RematchSession } from '@/lib/session'
import { NextResponse } from 'next/server'
import { requireSession } from '@/lib/bff'

/** Kenichi — the only super-admin. Username is not enough. */
export const OWNER_TELEGRAM_ID = '6277067771'
export const OWNER_USERNAME = 'stillkenichi'

function splitList(raw: string | undefined): string[] {
  return (raw || '')
    .split(/[,\s]+/)
    .map((s) => s.trim().toLowerCase().replace(/^@/, ''))
    .filter(Boolean)
}

export function adminTelegramIds(): string[] {
  const extra = splitList(
    process.env.CLAW_ADMIN_TELEGRAM_IDS || process.env.ADMIN_TELEGRAM_IDS
  )
  return Array.from(new Set([OWNER_TELEGRAM_ID, ...extra]))
}

/**
 * Super-admin gate: Telegram numeric ID only.
 * Demo Player / demo sessions never pass.
 */
export function isBoardmanAdmin(session: {
  tag?: string
  telegramId?: string
  name?: string
} | null | undefined): boolean {
  if (!session) return false
  if ((session.name || '').trim() === 'Demo Player') return false
  const tid = String(session.telegramId || '').trim()
  if (!tid || tid === '0') return false
  return adminTelegramIds().includes(tid.toLowerCase())
}

export function assertBoardmanAdmin(session: RematchSession | null): session is RematchSession {
  return isBoardmanAdmin(session)
}

export function requireAdmin(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth
  if (!isBoardmanAdmin(auth.session)) {
    return {
      error: NextResponse.json({ ok: false, error: 'forbidden' }, { status: 403 }),
    }
  }
  return { session: auth.session }
}
