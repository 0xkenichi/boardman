'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { listClubs, type AfmClub } from '@/lib/afm'

export function OwnerClubs() {
  const [clubs, setClubs] = useState<AfmClub[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    listClubs()
      .then((data) => {
        if (alive) setClubs(data)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      alive = false
    }
  }, [])

  if (error) {
    return (
      <div className="fd-err">
        Couldn’t reach the club store — the backend may be offline in this environment. This panel
        shows the real league clubs once the agent services are running.
      </div>
    )
  }

  if (!clubs) {
    return <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>Loading clubs…</p>
  }

  if (clubs.length === 0) {
    return (
      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>
        No clubs registered yet — the first agent-managed clubs will appear here.
      </p>
    )
  }

  return (
    <div className="fd-cards">
      {clubs.map((c) => (
        <div className="fd-card" key={c.agent_id}>
          <div className="fd-club">
            <span className="fd-clubname">{c.club_name}</span>
            <span className="fd-clubmeta">{c.agent_id.slice(0, 10)}…</span>
          </div>
          <p>
            {c.formation} · {(c.tactical_tags ?? []).join(', ') || 'balanced'} · {c.roster_size}{' '}
            players
            <br />
            spend {fmt(c.spend_usdc)} of {fmt(c.budget_usdc)} USDC
          </p>
          <p>
            <Link href={`/football/squad/${encodeURIComponent(c.agent_id)}`}>Squad room (FM) →</Link>
            {' · '}
            <Link href="/football/tactics">Preview their XI on the match board →</Link>
          </p>
        </div>
      ))}
    </div>
  )
}

function fmt(usdc: string): string {
  const n = Number(usdc)
  if (!Number.isFinite(n)) return usdc
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 })
}
