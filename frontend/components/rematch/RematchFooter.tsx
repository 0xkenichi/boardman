'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

/**
 * Minimal Rematch footer — replaces the global sideQuest footer under /rematch/*
 */
export function RematchFooter() {
  const path = usePathname() || ''
  // Mini-app has a fixed bottom tab bar — keep footer compact and out of the way
  const isApp = path.startsWith('/rematch/app')

  return (
    <footer
      className={`border-t border-gray-900/80 bg-[#050508] ${
        isApp ? 'pb-24' : ''
      }`}
    >
      <div className="mx-auto flex max-w-3xl flex-col items-center justify-between gap-2 px-4 py-5 sm:flex-row">
        <p className="text-xs text-gray-500">
          <span className="font-semibold text-gray-400">
            <span className="text-emerald-500">Re</span>match
          </span>{' '}
          by sideQuest
        </p>
        <div className="flex items-center gap-3 text-xs">
          <Link href="/rematch" className="text-gray-500 hover:text-emerald-400">
            Home
          </Link>
          <Link href="/rematch/leaderboard" className="text-gray-500 hover:text-emerald-400">
            Board
          </Link>
          <Link
            href="/"
            className="rounded-full border border-gray-800 px-2.5 py-1 font-medium text-gray-400 hover:border-gray-600 hover:text-white"
          >
            Go back to sideQuest
          </Link>
        </div>
      </div>
    </footer>
  )
}
