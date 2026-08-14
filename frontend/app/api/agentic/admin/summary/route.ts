import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import { requireSession } from '@/lib/bff'
import { isBoardmanAdmin } from '@/lib/adminAuth'

export const dynamic = 'force-dynamic'

function loadMetrics(): Record<string, unknown> {
  const candidates = [
    path.resolve(process.cwd(), 'public/agentic/aggregated_metrics.json'),
    path.resolve(process.cwd(), 'frontend/public/agentic/aggregated_metrics.json'),
  ]
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) {
        return JSON.parse(fs.readFileSync(p, 'utf8'))
      }
    } catch {
      /* next */
    }
  }
  return { players_count: 0, profiles_count: 0, total_arc: '0', profiles: [] }
}

export async function GET(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth.error
  if (!isBoardmanAdmin(auth.session)) {
    return NextResponse.json({ ok: false, error: 'forbidden' }, { status: 403 })
  }
  const metrics = loadMetrics()
  return NextResponse.json({
    ok: true,
    operator: auth.session.tag,
    metrics,
  })
}
