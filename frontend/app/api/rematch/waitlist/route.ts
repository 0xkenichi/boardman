/**
 * Boardman waitlist signup.
 * Stores email + optional handle; notifies admins on Telegram when possible.
 */
import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Entry = {
  email: string
  name?: string
  telegram?: string
  source?: string
  created_at: string
  ip?: string
}

function normalizeEmail(raw: string): string {
  return (raw || '').trim().toLowerCase()
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

async function appendLocal(entry: Entry) {
  try {
    const dir = path.join(process.cwd(), 'data')
    await fs.mkdir(dir, { recursive: true })
    const file = path.join(dir, 'waitlist.json')
    let rows: Entry[] = []
    try {
      const raw = await fs.readFile(file, 'utf8')
      rows = JSON.parse(raw)
      if (!Array.isArray(rows)) rows = []
    } catch {
      rows = []
    }
    if (rows.some((r) => r.email === entry.email)) {
      return { duplicate: true as const }
    }
    rows.push(entry)
    await fs.writeFile(file, JSON.stringify(rows, null, 2) + '\n', 'utf8')
    return { duplicate: false as const }
  } catch {
    // Vercel serverless FS is ephemeral / often read-only outside /tmp
    try {
      const file = path.join('/tmp', 'boardman-waitlist.json')
      let rows: Entry[] = []
      try {
        const raw = await fs.readFile(file, 'utf8')
        rows = JSON.parse(raw)
        if (!Array.isArray(rows)) rows = []
      } catch {
        rows = []
      }
      if (rows.some((r) => r.email === entry.email)) {
        return { duplicate: true as const }
      }
      rows.push(entry)
      await fs.writeFile(file, JSON.stringify(rows, null, 2) + '\n', 'utf8')
      return { duplicate: false as const }
    } catch {
      return { duplicate: false as const, ephemeral: true as const }
    }
  }
}

async function trySupabase(entry: Entry): Promise<boolean> {
  const url = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || '').replace(
    /\/$/,
    ''
  )
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_KEY ||
    process.env.SUPABASE_ANON_KEY ||
    ''
  if (!url || !key) return false
  try {
    const res = await fetch(`${url}/rest/v1/boardman_waitlist`, {
      method: 'POST',
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
        Prefer: 'return=minimal',
      },
      body: JSON.stringify({
        email: entry.email,
        name: entry.name || null,
        telegram: entry.telegram || null,
        source: entry.source || 'web',
        created_at: entry.created_at,
      }),
    })
    // 201 created, 409 conflict ok
    return res.ok || res.status === 409
  } catch {
    return false
  }
}

async function notifyTelegram(entry: Entry, duplicate: boolean) {
  const token =
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION || process.env.TELEGRAM_BOT_TOKEN || ''
  const raw =
    process.env.CLAW_ADMIN_TELEGRAM_IDS || process.env.ADMIN_TELEGRAM_IDS || ''
  if (!token || !raw) return
  const ids = raw.split(/[,;]/).map((s) => s.trim()).filter(Boolean)
  const text =
    `📋 <b>Boardman waitlist</b>${duplicate ? ' (already listed)' : ''}\n` +
    `Email: <code>${entry.email}</code>\n` +
    (entry.name ? `Name: ${entry.name}\n` : '') +
    (entry.telegram ? `TG: ${entry.telegram}\n` : '') +
    `Source: ${entry.source || 'web'}`
  await Promise.all(
    ids.map(async (chatId) => {
      try {
        await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: chatId,
            text,
            parse_mode: 'HTML',
          }),
        })
      } catch {
        /* ignore */
      }
    })
  )
}

export async function POST(req: NextRequest) {
  let body: { email?: string; name?: string; telegram?: string; source?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const email = normalizeEmail(body.email || '')
  if (!isValidEmail(email)) {
    return NextResponse.json({ error: 'Enter a valid email' }, { status: 400 })
  }

  const entry: Entry = {
    email,
    name: (body.name || '').trim().slice(0, 80) || undefined,
    telegram: (body.telegram || '').trim().replace(/^@/, '').slice(0, 40) || undefined,
    source: (body.source || 'web').slice(0, 40),
    created_at: new Date().toISOString(),
    ip: req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || undefined,
  }

  // Prefer Supabase if table exists; always try local/tmp backup
  const [local, sb] = await Promise.all([appendLocal(entry), trySupabase(entry)])
  const duplicate = local.duplicate === true

  await notifyTelegram(entry, duplicate)

  return NextResponse.json({
    ok: true,
    duplicate,
    stored: sb || !local.ephemeral,
    message: duplicate
      ? "You're already on the list — see you at launch."
      : "You're on the Boardman waitlist. We'll ping you before Sept 16.",
  })
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    product: 'Boardman by sideQuest',
    formerly: 'Rematch by sideQuest',
    launch: '2026-09-16',
    settlement: 'Arc mainnet',
  })
}
