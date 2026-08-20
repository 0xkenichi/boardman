import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/adminAuth'
import { rematchApiFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error

  const metrics = await Promise.race([
    rematchApiFetch('/api/stack/agentic/admin/metrics-detail'),
    new Promise<{ ok: false; status: number; data: any }>((resolve) =>
      setTimeout(() => resolve({ ok: false, status: 504, data: { error: 'timeout' } }), 10000)
    ),
  ])

  return NextResponse.json(
    metrics.ok ? metrics.data : { success: false, error: metrics.data?.error || 'Stack API offline' },
    { headers: { 'Cache-Control': 'no-store' } }
  )
}
