/**
 * Public config for arena Telegram login (no secrets).
 */
import { NextResponse } from "next/server";
import { telegramBotUsername, telegramBotUrl } from "@/lib/telegramBot";

export const dynamic = "force-dynamic";

export async function GET() {
  const bot = telegramBotUsername();
  const tokenSet = Boolean(
    process.env.TELEGRAM_BOT_TOKEN_BOARDMAN ||
      process.env.TELEGRAM_BOT_TOKEN_MYBOARDMAN ||
      process.env.TELEGRAM_BOT_TOKEN_CLAWSTATION ||
      process.env.TELEGRAM_BOT_TOKEN
  );
  return NextResponse.json({
    ok: true,
    bot_username: bot,
    bot_url: telegramBotUrl(),
    telegram_login_ready: tokenSet,
    note:
      "Use Telegram Login Widget on this host. BotFather → /setdomain for boardman.playingsidequest.fun",
  });
}
