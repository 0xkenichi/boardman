/**
 * Boardman Telegram bot identity (browser + server).
 * Prefer Boardman env names; fall back to legacy ClawStation aliases.
 */

export const DEFAULT_BOT_USERNAME = 'myboardmanOfficialBot'
export const DEFAULT_BOT_URL = `https://t.me/${DEFAULT_BOT_USERNAME}`

/** Public @username without @ — safe for client components. */
export function telegramBotUsername(): string {
  const raw =
    process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ||
    process.env.NEXT_PUBLIC_TELEGRAM_BOT_NAME ||
    DEFAULT_BOT_USERNAME
  return raw.replace(/^@/, '').trim() || DEFAULT_BOT_USERNAME
}

/** https://t.me/... deep link — safe for client components. */
export function telegramBotUrl(): string {
  const explicit = (process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL || '').trim()
  if (explicit) {
    if (explicit.startsWith('http')) return explicit.replace(/\/$/, '')
    return `https://${explicit.replace(/^\//, '')}`
  }
  return `https://t.me/${telegramBotUsername()}`
}

/**
 * Bot API token — server-only. Never import this into client components.
 * Order: Boardman → legacy ClawStation → generic.
 */
export function telegramBotToken(): string {
  return (
    process.env.TELEGRAM_BOT_TOKEN_BOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_MYBOARDMAN ||
    process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
    process.env.TELEGRAM_BOT_TOKEN ||
    ''
  ).trim()
}
