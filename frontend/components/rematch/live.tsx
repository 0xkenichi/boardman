'use client'

/**
 * Small live-data helpers shared by the landing slip, the arena and the desk.
 *
 * - `usePolling` — a setTimeout chain (never overlapping requests) that pauses
 *   while the tab is hidden, checks again the moment it comes back, and backs
 *   off exponentially while the house is not answering.
 * - `fetchJson` — GET with a hard client-side timeout, so a hung backend can
 *   never leave a page waiting forever.
 * - `<Countdown>` / `<Ago>` / `<UtcClock>` — each ticks on its own, so a 1s
 *   heartbeat re-renders a few characters instead of the whole page.
 */

import { useEffect, useRef, useState } from 'react'

export type FetchResult<T> = {
  ok: boolean
  status: number
  data: T | null
  /** Network error, abort/timeout, or a 502/503/504 from our own API. */
  offline: boolean
}

const OFFLINE_ERRORS = /offline|unreachable|timeout|timed_out|backend|unavailable/i

export async function fetchJson<T = Record<string, unknown>>(
  url: string,
  timeoutMs = 6000,
): Promise<FetchResult<T>> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const res = await fetch(url, { cache: 'no-store', signal: ctl.signal })
    const data = (await res.json().catch(() => null)) as T | null
    const err = String((data as { error?: unknown } | null)?.error ?? '')
    const offline =
      res.status === 502 ||
      res.status === 503 ||
      res.status === 504 ||
      (!res.ok && OFFLINE_ERRORS.test(err))
    return { ok: res.ok, status: res.status, data, offline }
  } catch {
    return { ok: false, status: 0, data: null, offline: true }
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Run `task` now, then again every `intervalMs` while the tab is visible.
 * `task` returns false (or throws) to report a failure; consecutive failures
 * stretch the gap — interval × 2ⁿ, capped at `maxMs`.
 */
export function usePolling(
  task: () => Promise<boolean | void>,
  {
    intervalMs,
    maxMs = 60_000,
    enabled = true,
    immediate = true,
  }: {
    intervalMs: number
    maxMs?: number
    enabled?: boolean
    /** false: the caller already loaded once — wait a full interval first */
    immediate?: boolean
  },
) {
  const taskRef = useRef(task)
  useEffect(() => {
    taskRef.current = task
  })

  useEffect(() => {
    if (!enabled) return
    let dead = false
    let running = false
    let failures = 0
    let timer: number | undefined

    const schedule = (ms: number) => {
      window.clearTimeout(timer)
      timer = window.setTimeout(run, ms)
    }

    async function run() {
      if (dead || running) return
      // Hidden tab: stop here; the visibility listener restarts us.
      if (typeof document !== 'undefined' && document.hidden) return
      running = true
      let ok = true
      try {
        ok = (await taskRef.current()) !== false
      } catch {
        ok = false
      }
      running = false
      if (dead) return
      failures = ok ? 0 : failures + 1
      schedule(ok ? intervalMs : Math.min(maxMs, intervalMs * 2 ** failures))
    }

    const onVisibility = () => {
      if (document.hidden) window.clearTimeout(timer)
      else schedule(0)
    }

    document.addEventListener('visibilitychange', onVisibility)
    if (immediate) run()
    else schedule(intervalMs)
    return () => {
      dead = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [intervalMs, maxMs, enabled, immediate])
}

/** Current time, refreshed every `everyMs` — only in the component that asks. */
export function useNow(everyMs = 1000, enabled = true): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!enabled) return
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), everyMs)
    return () => window.clearInterval(id)
  }, [everyMs, enabled])
  return now
}

export function fmtCountdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** "23:12" to an epoch-ms target, then `done` once it passes. */
export function Countdown({ to, done = 'any moment' }: { to: number; done?: string }) {
  const now = useNow(1000)
  const left = to - now
  return <>{left > 0 ? fmtCountdown(left) : done}</>
}

export function fmtAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return '—'
  const s = Math.max(0, Math.floor((now - t) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

/** "12s ago", kept fresh by its own heartbeat. */
export function Ago({ iso }: { iso?: string | null }) {
  const now = useNow(1000, Boolean(iso))
  return <>{fmtAgo(iso, now)}</>
}

export function fmtUtcTime(ms: number, seconds = false): string {
  return new Date(ms).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    ...(seconds ? { second: '2-digit' as const } : {}),
    timeZone: 'UTC',
  })
}

/** Wall clock in UTC. Empty on the server so the static HTML never lies. */
export function UtcClock({ className }: { className?: string }) {
  const [mounted, setMounted] = useState(false)
  const now = useNow(1000, mounted)
  useEffect(() => setMounted(true), [])
  return <span className={className}>{mounted ? `${fmtUtcTime(now, true)} UTC` : ''}</span>
}
