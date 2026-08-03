'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const BOT = process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL || 'https://t.me/ClawStationOfficialBot'

const LINKS = [
  { href: '/rematch', label: 'Home', exact: true },
  { href: '/rematch/app', label: 'Play' },
  { href: '/rematch/leaderboard', label: 'Board' },
  { href: '/rematch/get-usdc', label: 'Get USDC' },
]

export function RematchNav() {
  const path = usePathname() || ''
  const isApp = path.startsWith('/rematch/app')

  return (
    <header className="sticky top-0 z-50 border-b border-gray-900/90 bg-[#050508]/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
        <Link
          href="/rematch"
          className="flex shrink-0 items-center gap-2 font-black tracking-tight"
        >
          <span className="text-emerald-400">Re</span>
          <span className="text-white">match</span>
        </Link>

        {!isApp ? (
          <nav className="hidden items-center gap-1 sm:flex">
            {LINKS.map((l) => {
              const active = l.exact
                ? path === l.href
                : path === l.href || path.startsWith(l.href + '/')
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                    active
                      ? 'bg-emerald-600/20 text-emerald-400'
                      : 'text-gray-400 hover:bg-gray-900 hover:text-white'
                  }`}
                >
                  {l.label}
                </Link>
              )
            })}
          </nav>
        ) : (
          <span className="text-xs font-medium text-gray-500">Play</span>
        )}

        <div className="flex shrink-0 items-center gap-2">
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 sm:inline-flex"
          >
            Bot
          </a>
          <Link
            href="/"
            className="rounded-full border border-gray-800 bg-gray-950 px-3 py-1.5 text-xs font-semibold text-gray-300 transition hover:border-gray-600 hover:text-white"
          >
            ← sideQuest
          </Link>
        </div>
      </div>
    </header>
  )
}
