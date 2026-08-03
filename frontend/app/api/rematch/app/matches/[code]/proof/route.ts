import { NextResponse } from 'next/server'
import { readSessionFromRequest } from '@/lib/session'
import { stackConfigured, stackFetch } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function POST(
  req: Request,
  { params }: { params: { code: string } }
) {
  const s = readSessionFromRequest(req)
  if (!s) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  const code = decodeURIComponent(params.code)

  const form = await req.formData()
  const file = form.get('file')
  const score = String(form.get('score') || '')

  if (!(file instanceof Blob)) {
    return NextResponse.json({ ok: false, error: 'file_required' }, { status: 400 })
  }
  if (file.size > 8_000_000) {
    return NextResponse.json({ ok: false, error: 'file_too_large' }, { status: 400 })
  }

  if (stackConfigured()) {
    const fd = new FormData()
    fd.set('profile_id', s.profileId)
    fd.set('score', score)
    fd.set('file', file, 'proof.jpg')
    const res = await stackFetch(`/api/stack/v1/matches/${encodeURIComponent(code)}/proof`, {
      method: 'POST',
      body: fd,
    })
    return NextResponse.json({ ok: res.ok, ...res.data, demo: false }, { status: res.ok ? 200 : res.status })
  }

  // Demo: accept upload and pretend AI ok
  return NextResponse.json({
    ok: true,
    success: true,
    demo: true,
    match_id: code,
    ai: {
      ok: Boolean(score),
      confidence: score ? 0.85 : 0.4,
      score_string: score || null,
      error: score ? null : 'Provide a score caption for demo settle',
    },
    message: 'Proof received (demo mode). Wire STACK_API_URL for live AI settle.',
  })
}
