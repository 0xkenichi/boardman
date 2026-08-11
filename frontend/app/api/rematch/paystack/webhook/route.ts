/**
 * Paystack webhook — charge.success
 *
 * Configure in Paystack Dashboard → Settings → Webhooks:
 *   https://boardman.playingsidequest.fun/api/rematch/paystack/webhook
 *
 * Verifies HMAC SHA512 (x-paystack-signature) with PAYSTACK_SECRET_KEY.
 * Notifies admin Telegram IDs so they send USDC from float + /credit_topup.
 *
 * Note: top-up store lives with the bot process; this webhook is a reliable
 * "payment confirmed" ping. Player can also tap "I've paid — check" in the bot
 * (server-side verify) which updates the ledger.
 */
import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function verifySignature(rawBody: string, signature: string | null): boolean {
  const secret = (process.env.PAYSTACK_SECRET_KEY || '').trim()
  if (!secret || !signature) return false
  const hash = crypto.createHmac('sha512', secret).update(rawBody).digest('hex')
  try {
    return crypto.timingSafeEqual(Buffer.from(hash), Buffer.from(signature))
  } catch {
    return false
  }
}

async function notifyTelegram(text: string) {
  const token =
    process.env.TELEGRAM_BOT_TOKEN_BOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
    process.env.TELEGRAM_BOT_TOKEN ||
    ''
  const raw =
    process.env.CLAW_ADMIN_TELEGRAM_IDS || process.env.ADMIN_TELEGRAM_IDS || ''
  if (!token || !raw) return
  const ids = raw
    .split(/[,;]/)
    .map((s) => s.trim())
    .filter(Boolean)
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
            disable_web_page_preview: true,
          }),
        })
      } catch {
        /* ignore per-admin failures */
      }
    })
  )
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text()
  const signature = req.headers.get('x-paystack-signature')
  if (!verifySignature(rawBody, signature)) {
    return NextResponse.json({ error: 'invalid signature' }, { status: 401 })
  }

  let event: {
    event?: string
    data?: {
      reference?: string
      amount?: number
      status?: string
      channel?: string
      paid_at?: string
      metadata?: Record<string, string>
      customer?: { email?: string }
    }
  }
  try {
    event = JSON.parse(rawBody)
  } catch {
    return NextResponse.json({ error: 'bad json' }, { status: 400 })
  }

  if (event.event !== 'charge.success') {
    return NextResponse.json({ ok: true, ignored: event.event || 'unknown' })
  }

  const data = event.data || {}
  const ref = data.reference || '—'
  const amountNgn = ((data.amount || 0) as number) / 100
  const meta = data.metadata || {}
  const boardmanRef = meta.boardman_ref || ref
  const credit = meta.credit_usdc || '?'
  const play = meta.play_address || '—'
  const tg = meta.telegram_id || '—'

  await notifyTelegram(
    `⚡ <b>Paystack charge.success</b>\n` +
      `Ref: <code>${boardmanRef}</code>\n` +
      `Paystack: <code>${ref}</code>\n` +
      `₦${amountNgn.toLocaleString()}\n` +
      `Credit due: <b>$${credit}</b> USDC\n` +
      `Play: <code>${play}</code>\n` +
      `TG: ${tg}\n` +
      `Channel: ${data.channel || '—'}\n\n` +
      `1) Send USDC from float\n` +
      `2) In bot: /credit_topup ${boardmanRef}`
  )

  // Optional: notify the player that payment was seen
  const playerTg = meta.telegram_id
  const token =
    process.env.TELEGRAM_BOT_TOKEN_BOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
    process.env.TELEGRAM_BOT_TOKEN ||
    ''
  if (token && playerTg) {
    try {
      await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: playerTg,
          text:
            `✅ <b>Paystack payment received</b>\n\n` +
            `Ref <code>${boardmanRef}</code>\n` +
            `We're crediting <b>$${credit} USDC</b> to your play wallet shortly.\n` +
            `In the bot you can also tap <b>I've paid — check status</b>.`,
          parse_mode: 'HTML',
        }),
      })
    } catch {
      /* ignore */
    }
  }

  return NextResponse.json({ ok: true })
}

/** Health / docs for dashboard */
export async function GET() {
  return NextResponse.json({
    ok: true,
    service: 'boardman-paystack-webhook',
    hint: 'POST charge.success events from Paystack here',
  })
}
