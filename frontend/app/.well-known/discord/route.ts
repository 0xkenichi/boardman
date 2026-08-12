import { NextResponse } from 'next/server'

/** Discord domain verification: https://boardman.playingsidequest.fun/.well-known/discord */
const DISCORD_DOMAIN_HASH = 'dh=b08713de76a908340fb7638feb68ad53113c7c20'

export function GET() {
  return new NextResponse(`${DISCORD_DOMAIN_HASH}\n`, {
    status: 200,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=0, must-revalidate',
    },
  })
}
