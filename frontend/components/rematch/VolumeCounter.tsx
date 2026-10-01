'use client'

import { useEffect, useState } from 'react'

export function VolumeCounter() {
  const [volume, setVolume] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    async function loadMetrics() {
      try {
        const r = await window.fetch('/api/stack/agentic/public/metrics?limit=1')
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
    loadMetrics()
    const id = setInterval(loadMetrics, 30000) // refresh every 30s
    return () => { alive = false; clearInterval(id) }
  }, [])

  return (
    <div style={{
      textAlign: 'center',
      padding: '1.5rem 1rem',
      background: '#f9f6ec',
      borderRadius: '3px',
      border: '1px solid rgba(32,31,26,0.4)',
    }}>
      <p style={{
        fontSize: '0.75rem',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: '#256b48',
        margin: '0 0 0.5rem 0',
        fontWeight: 600,
      }}>
        Total Volume Moved
      </p>
      <p style={{
        fontSize: '2rem',
        fontWeight: 700,
        color: '#201f1a',
        margin: 0,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {loading ? '…' : `$${volume}`}
      </p>
      <p style={{
        fontSize: '0.7rem',
        color: '#8a8478',
        margin: '0.5rem 0 0 0',
      }}>
        USDC settled on-chain · skill + spectator
      </p>
    </div>
  )
}
