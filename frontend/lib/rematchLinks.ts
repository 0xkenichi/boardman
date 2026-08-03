/** Public Rematch Telegram / funding links (browser-safe). */

export const REMATCH_BOT_URL =
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL || 'https://t.me/ClawStationOfficialBot'

export const REMATCH_BOT_USERNAME =
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ||
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_NAME ||
  'ClawStationOfficialBot'

/**
 * Main Telegram group for live rooms + public open challenges.
 * Set NEXT_PUBLIC_TELEGRAM_GROUP_URL to your invite (e.g. https://t.me/+xxxx or t.me/YourGroup).
 */
export const REMATCH_GROUP_URL =
  process.env.NEXT_PUBLIC_TELEGRAM_GROUP_URL ||
  process.env.NEXT_PUBLIC_REMATCH_TG_GROUP ||
  // Fallback: bot — ops should set a real group invite in Vercel env
  REMATCH_BOT_URL

export const LIVE_ROOMS = [
  { id: 'mobile', emoji: '📲', label: 'Mobile', hint: 'FC Mobile, Free Fire, COD, PUBG…' },
  { id: 'console', emoji: '🎮', label: 'Console', hint: 'EA FC, NBA 2K, console 1v1s' },
  { id: 'pc', emoji: '💻', label: 'PC', hint: 'Valorant, PC ranked duels' },
  { id: 'imessage', emoji: '📱', label: 'iMessage', hint: '8 Ball, Chess, GamePigeon' },
] as const
