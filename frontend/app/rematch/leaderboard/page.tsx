'use client'

/**
 * Public Boardman leaderboard + open challenges — the book's public page.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'
import { LiveRoomsCard } from '@/components/rematch/LiveRoomsCard'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

const BOT = REMATCH_BOT_URL
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
        const data = await res.json().catch(() => ({}))
        if (cancelled) return
        if (!res.ok) {
          setErr(data.error || 'Failed to load')
          return
        }
        setLeaders(data.leaders || [])
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
    <BookShell title="The board">
      <div style={{ maxWidth: '42rem', margin: '0 auto', padding: '0 1rem 3rem' }}>
        <div style={{ marginBottom: '1.75rem' }}>
          <p className="bk-lede" style={{ margin: '0 0 0.5rem', maxWidth: '30rem' }}>
            The <em>public book</em> — PLAY standings and every open challenge.
            Play on Arc via web or Telegram.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            <Link
              href="/app"
              className="rm-btn rm-btn-primary"
              style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
            >
              Open app
            </Link>
            <a
              href={REMATCH_GROUP_URL}
              target="_blank"
              rel="noreferrer"
              className="rm-btn rm-btn-ghost"
              style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
            >
              Live rooms
            </a>
            <a
              href={BOT}
              target="_blank"
              rel="noreferrer"
              className="rm-btn rm-btn-ghost"
              style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
            >
              Open bot
            </a>
            <a
              href={FAUCET}
              target="_blank"
              rel="noreferrer"
              className="rm-btn rm-btn-ghost"
              style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
            >
              Get USDC
            </a>
          </div>
        </div>

        <div style={{ marginBottom: '1.5rem' }}>
          <LiveRoomsCard variant="compact" />
        </div>

        {loading && (
          <div className="rm-stack" style={{ marginBottom: '1.5rem' }}>
            <div className="rm-skeleton" style={{ height: 120, borderRadius: 3 }} />
            <div className="rm-skeleton" style={{ height: 200, borderRadius: 3 }} />
          </div>
        )}

        {err && (
          <div className="rm-card rm-card-warn" style={{ marginBottom: '1.25rem' }}>
            <p className="rm-warn-text" style={{ margin: 0 }}>
              Could not read the book just now. Open the bot, or try again later.
            </p>
          </div>
        )}

        <div className="rm-stack-lg">
          <section className="rm-card">
            <h2 className="rm-section-title">OPEN CHALLENGES</h2>
            {!loading && opens.length === 0 && (
              <p className="rm-muted" style={{ margin: 0 }}>
                Nothing open right now. Create one in the app.
              </p>
            )}
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }} className="rm-stack">
              {opens.map((o) => (
                <li key={o.code} className="bk-ledger-row">
                  <span>
                    <code className="bk-code-ink">{o.code}</code>
                    <span className="bk-dot"> · </span>
                    <strong>${o.stake}</strong>
                    <span className="bk-dot"> · {o.game}</span>
                  </span>
                  <span className="bk-dim">@{o.creator_tag}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rm-card">
            <h2 className="rm-section-title">PLAY LEADERBOARD</h2>
            {!loading && leaders.length === 0 && (
              <p className="rm-muted" style={{ margin: 0 }}>
                No ranked players yet — win a match.
              </p>
            )}
            <div style={{ overflowX: 'auto' }}>
              <table className="bk-ledger-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>PLAYER</th>
                    <th>PLAY</th>
                    <th>REP</th>
                    <th>W/L</th>
                  </tr>
                </thead>
                <tbody>
                  {leaders.map((r) => (
                    <tr key={r.rank + r.tag}>
                      <td className="bk-dim">{r.rank}</td>
                      <td>
                        <strong>@{r.tag}</strong>
                        {r.streak > 0 && (
                          <span className="bk-streak">🔥{r.streak}</span>
                        )}
                      </td>
                      <td className="bk-ink-td">{r.play_points.toLocaleString()}</td>
                      <td>{r.reputation}</td>
                      <td>{r.wins}/{r.losses}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p style={{ textAlign: 'center', margin: 0 }}>
            <Link href="/" className="rm-muted" style={{ fontSize: '0.8rem' }}>
              About the boardman
            </Link>
          </p>
        </div>
      </div>
    </BookShell>
  )
}
