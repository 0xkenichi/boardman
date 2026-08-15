/**
 * Boardman waitlist signup.
 * Stores email + optional handle; notifies admins on Telegram when possible.
 */
import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { randomInt } from 'crypto'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Warm welcome pool — one random variant per confirmed signup so no two
 * people get the same first hello. All on-voice: the desk, the lights,
 * walk good. Keep these short and human.
 */
const WELCOME_VARIANTS: string[] = [
  "Your email landed. That's the handshake. Come as you are. Hope you enjoy your games. Hope you eat. We'll write before the lights go up. Walk good.",
  "You're on the list. Pull up a chair — the games run deep and the door stays open. We'll write when it's time.",
  "Landed. Consider yourself seated. We're setting the boards and sharpening the lines — we'll come find you before the first bell.",
  "Got you down. No hurry, no fine print — just a seat saved at the table. Talk soon, when the house lights dim.",
  "Welcome to the desk. You're in the book now — the one with no erasures. We'll be in touch when the room opens.",
  "Your name's on the wall. That's a promise, not a post-it. We'll write before the lights go up. Walk good.",
  "Noted, kept, and welcomed. The boards are warm and the coffee's on. We'll ping you when it's showtime.",
  "You're in. The ledger has your line, clean as a first move. We'll reach out when the house is ready.",
  "Email secured. The rest is timing. Sit tight, play something, and we'll call you when the doors open.",
  "Consider this your seat check. The arena's still humming — you'll hear from us before the main event.",
  "Landed in the good pile. The desk doesn't lose papers and it doesn't forget faces. We'll write soon.",
  "You're on the roster. The games are being tuned, the stakes set, and your spot's held. See you when the lights go up.",
  "Got it — and we mean it. The table's set, your chair's warm, and the first round's on the house. We'll be in touch.",
  "Down on paper, up in spirit. Welcome to the room. We'll knock before the doors open.",
  "You're in the book — the good one. We'll write before the lights go up, so keep your phone close and your game sharp.",
  "Welcome to the desk. No queue, no fuss — you're in. We'll reach out when it's time to play for real.",
  "Your seat's saved. The house is still sweeping the floors, but your name's on the door. We'll write when we flip the sign.",
  "Landed. Consider the handshake done. We'll keep you posted — short notes, real news, no spam.",
  "You're counted. The deck's stacked in your favor: a warm welcome, a seat, and a note when the room opens.",
  "In the system, out of the cold. Welcome to the desk. We'll write before the lights go up — promise.",
  "Done and dusted — in the good way. You're on the list, the games are coming, and we'll find you first.",
  "Your email's home. Come as you are — that's the whole dress code. We'll be in touch when the boards are live.",
  "Seated. The arena's getting ready, and so are we. You'll hear from us before the first whistle.",
  "You're in the book. Sharp game, warm welcome, real people on the other end. Talk soon.",
]

function pickWelcome(): string {
  return WELCOME_VARIANTS[randomInt(WELCOME_VARIANTS.length)]
}

type Entry = {
  email: string
  name?: string
  telegram?: string
  source?: string
  note?: string
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
        note: entry.note || null,
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
    process.env.TELEGRAM_BOT_TOKEN_BOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
    process.env.TELEGRAM_BOT_TOKEN ||
    ''
  const raw =
    process.env.CLAW_ADMIN_TELEGRAM_IDS || process.env.ADMIN_TELEGRAM_IDS || ''
  if (!token || !raw) return
  const ids = raw.split(/[,;]/).map((s) => s.trim()).filter(Boolean)
  const text =
    `📋 <b>Boardman waitlist</b>${duplicate ? ' (already listed)' : ''}\n` +
    `Email: <code>${entry.email}</code>\n` +
    (entry.name ? `Name: ${entry.name}\n` : '') +
    (entry.telegram ? `TG: ${entry.telegram}\n` : '') +
    (entry.note ? `Note: ${entry.note}\n` : '') +
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
  let body: { email?: string; name?: string; telegram?: string; source?: string; note?: string }
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
    note: (body.note || '').trim().slice(0, 400) || undefined,
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
    title: duplicate ? 'Already on the list.' : 'We got you.',
    message: duplicate
      ? "We don't lose people. Same desk, same welcome — sit tight."
      : pickWelcome(),
  })
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    product: 'Boardman by sideQuest',
    launch: '2026-09-16',
    settlement: 'Arc mainnet',
  })
}
