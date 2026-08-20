'use client'

import { useEffect, useState } from 'react'

export function VolumeCounter() {
  const [volume, setVolume] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    async function fetch() {
      try {
        const r = await fetch('/api/stack/agentic/public/metrics?limit=1')
        const d = await r.json()
        if (!alive) return
        const vol = d?.volume || {}
        const total = Number(vol.skill_volume_usdc || 0) + Number(vol.spectator_volume_usdc || 0)
        setVolume(total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
      } catch {
        if (alive) setVolume('—')
      } finally {
        if (alive) setLoading(false)
      }
    }
    fetch()
    const id = setInterval(fetch, 30000) // refresh every 30s
    return () => { alive = false; clearInterval(id) }
  }, [])

  return (
    <div style={{
      textAlign: 'center',
      padding: '1.5rem 1rem',
      background: 'linear-gradient(135deg, rgba(139,92,246,0.1), rgba(59,130,246,0.1))',
      borderRadius: '12px',
      border: '1px solid rgba(139,92,246,0.2)',
    }}>
      <p style={{
        fontSize: '0.75rem',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: '#a78bfa',
        margin: '0 0 0.5rem 0',
        fontWeight: 600,
      }}>
        Total Volume Moved
      </p>
      <p style={{
        fontSize: '2rem',
        fontWeight: 700,
        color: '#fff',
        margin: 0,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {loading ? '…' : `$${volume}`}
      </p>
      <p style={{
        fontSize: '0.7rem',
        color: '#6b7280',
        margin: '0.5rem 0 0 0',
      }}>
        USDC settled on-chain · skill + spectator
      </p>
    </div>
  )
}
