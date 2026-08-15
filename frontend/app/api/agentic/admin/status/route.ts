import { NextRequest, NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/adminAuth'
import { rematchApiFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  const r = await rematchApiFetch('/api/stack/agentic/house/status')
  return NextResponse.json(
    r.ok ? r.data : { ok: false, error: r.data?.detail || r.data?.error || 'status unavailable' },
    { status: r.ok ? 200 : r.status || 502, headers: { 'Cache-Control': 'no-store' } }
  )
}
