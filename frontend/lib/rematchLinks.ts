/** Public Boardman Telegram / funding links (browser-safe). */
import { DEFAULT_BOT_URL, DEFAULT_BOT_USERNAME, telegramBotUrl, telegramBotUsername } from './telegramBot'

export const REMATCH_BOT_URL = telegramBotUrl() || DEFAULT_BOT_URL

export const REMATCH_BOT_USERNAME = telegramBotUsername() || DEFAULT_BOT_USERNAME

/** Default Boardman community invite (live rooms + public challenges). */
export const DEFAULT_GROUP_URL = 'https://t.me/+4YrgJ6vO2h8zMjk0'

/**
 * Main Telegram group for live rooms + public open challenges.
 * Override with NEXT_PUBLIC_TELEGRAM_GROUP_URL if the invite rotates.
 */
export const REMATCH_GROUP_URL =
  process.env.NEXT_PUBLIC_TELEGRAM_GROUP_URL ||
  process.env.NEXT_PUBLIC_REMATCH_TG_GROUP ||
  DEFAULT_GROUP_URL

export const LIVE_ROOMS = [
  { id: 'physical', emoji: '🎲', label: 'Physical', hint: 'Chess, Ludo, Monopoly IRL' },
  { id: 'mobile', emoji: '📲', label: 'Mobile', hint: 'FC Mobile, Free Fire, COD, PUBG…' },
  { id: 'console', emoji: '🎮', label: 'Console', hint: 'EA FC, NBA 2K, console 1v1s' },
  { id: 'pc', emoji: '💻', label: 'PC', hint: 'Valorant, PC ranked duels' },
  { id: 'imessage', emoji: '📱', label: 'iMessage', hint: '8 Ball, Chess, GamePigeon' },
] as const
