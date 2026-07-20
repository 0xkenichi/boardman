'use client'

/**
 * Public Rematch leaderboard + open challenges.
 * Player-facing only — no grants / funding / mult tables.
 */
import { useEffect, useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'

const BOT = 'https://t.me/ClawStationOfficialBot'
const FAUCET = 'https://faucet.circle.com/'

type LeaderRow = {
  rank: number
  tag: string
  name: string
  play_points: number
  reputation: number
  wins: number
  losses: number
  draws: number
  streak: number
  tier_label?: string
}

type OpenChallenge = {
  code: string
  stake: number
  game: string
  chain: string
  creator_tag: string
}

export default function RematchLeaderboardPage() {
  const [leaders, setLeaders] = useState<LeaderRow[]>([])
  const [opens, setOpens] = useState<OpenChallenge[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/rematch/public', { cache: 'no-store' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (cancelled) return
        setLeaders(data.leaderboard || [])
        setOpens(data.open_challenges || [])
      } catch (e: any) {
        if (!cancelled) setErr(e?.message || 'Failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="min-h-screen bg-[#050508] text-white">
      <header className="border-b border-gray-900/80 px-4 py-4 flex items-center justify-between max-w-3xl mx-auto gap-3">
        <Link href="/rematch" className="text-sm text-gray-400 hover:text-white transition-colors">
          ← Rematch
        </Link>
        <div className="flex items-center gap-2">
          <Image
            src="/rematch-logo.jpg"
            alt=""
            width={28}
            height={28}
            className="rounded-lg"
          />
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-semibold px-3 py-1.5 rounded-full bg-emerald-600 hover:bg-emerald-500"
          >
            Open bot
          </a>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
        <div>
          <p className="text-[11px] uppercase tracking-[2px] text-emerald-500/80 font-semibold mb-2">
            Public board
          </p>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight mb-2">
            <span className="text-emerald-400">Leaderboard</span> & open matches
          </h1>
          <p className="text-gray-400 text-sm max-w-xl">
            PLAY standings and open challenges. Play in Telegram on Arc.
          </p>
          <div className="flex flex-wrap gap-2 mt-4">
            <a
              href={BOT}
              target="_blank"
              rel="noreferrer"
              className="text-xs font-semibold px-3 py-1.5 rounded-full bg-emerald-600 hover:bg-emerald-500"
            >
              Open bot
            </a>
            <a
              href={FAUCET}
              target="_blank"
              rel="noreferrer"
              className="text-xs font-semibold px-3 py-1.5 rounded-full bg-gray-900 border border-gray-700 hover:bg-gray-800"
            >
              Get USDC (Arc)
            </a>
          </div>
        </div>

        {loading && <p className="text-gray-500 text-sm">Loading…</p>}
        {err && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
            Could not load live data. Open the bot, or try again later.
          </div>
        )}

        {/* Open challenges */}
        <section className="rounded-2xl border border-gray-800 bg-gray-950/50 p-5">
          <h2 className="text-lg font-bold text-emerald-400 mb-3">Open challenges</h2>
          {!loading && opens.length === 0 && (
            <p className="text-sm text-gray-500">
              No open public challenges right now. Create one in the bot.
            </p>
          )}
          <ul className="space-y-2">
            {opens.map((o) => (
              <li
                key={o.code}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-gray-900/60 border border-gray-800 px-3 py-2.5 text-sm"
              >
                <span>
                  <code className="text-emerald-400">{o.code}</code>
                  <span className="text-gray-500"> · </span>
                  <span className="text-white">${o.stake}</span>
                  <span className="text-gray-500"> · {o.game}</span>
                </span>
                <span className="text-gray-400">@{o.creator_tag}</span>
              </li>
            ))}
          </ul>
          <a
            href={BOT}
            className="inline-block mt-4 text-sm text-emerald-400 underline"
            target="_blank"
            rel="noreferrer"
          >
            Play in Telegram →
          </a>
        </section>

        {/* Leaderboard */}
        <section className="rounded-2xl border border-gray-800 bg-gray-950/50 p-5">
          <h2 className="text-lg font-bold text-emerald-400 mb-3">PLAY leaderboard</h2>
          {!loading && leaders.length === 0 && (
            <p className="text-sm text-gray-500">No ranked players yet — win a match.</p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="py-2 pr-2">#</th>
                  <th className="py-2 pr-2">Player</th>
                  <th className="py-2 pr-2">PLAY</th>
                  <th className="py-2 pr-2">Rep</th>
                  <th className="py-2">W/L</th>
                </tr>
              </thead>
              <tbody>
                {leaders.map((r) => (
                  <tr key={r.rank + r.tag} className="border-b border-gray-900 text-gray-300">
                    <td className="py-2.5 pr-2 text-gray-500">{r.rank}</td>
                    <td className="py-2.5 pr-2">
                      <span className="text-white font-medium">@{r.tag}</span>
                      {r.streak > 0 && (
                        <span className="text-orange-400 text-xs ml-1">🔥{r.streak}</span>
                      )}
                    </td>
                    <td className="py-2.5 pr-2 text-emerald-400 font-semibold">
                      {r.play_points.toLocaleString()}
                    </td>
                    <td className="py-2.5 pr-2">{r.reputation}</td>
                    <td className="py-2.5">
                      {r.wins}/{r.losses}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <p className="text-center text-xs text-gray-600">
          <Link href="/rematch" className="underline text-gray-500">
            About Rematch
          </Link>
        </p>
      </div>
    </div>
  )
}
